/**
 * Adapt Status Screen
 * 
 * Shows adaptation job progress and provides download when complete.
 * Polls for status updates and shows animated progress.
 */

import React, { useState, useCallback, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ActivityIndicator,
  Alert,
  Animated,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router, useLocalSearchParams } from 'expo-router';
import { 
  CheckCircle, 
  XCircle, 
  Download, 
  Share2, 
  ArrowLeft,
  RefreshCw,
  FileArchive,
} from 'lucide-react-native';
import { useQuery } from '@tanstack/react-query';
import Colors from '../../constants/Colors';
import { schemasApi } from '../../services/api';
import { downloadJobOutput, shareFile, formatFileSize } from '../../services/download';

type AdaptStatus = 'pending' | 'processing' | 'completed' | 'failed';

const STATUS_CONFIG: Record<AdaptStatus, {
  icon: React.ComponentType<{ size: number; color: string }>;
  color: string;
  title: string;
  subtitle: string;
}> = {
  pending: {
    icon: RefreshCw,
    color: '#FF9500',
    title: 'Queued',
    subtitle: 'Waiting to start...',
  },
  processing: {
    icon: RefreshCw,
    color: '#89C7FE',
    title: 'Adapting',
    subtitle: 'Preparing your documents...',
  },
  completed: {
    icon: CheckCircle,
    color: '#34C759',
    title: 'Ready!',
    subtitle: 'Your export is ready to download',
  },
  failed: {
    icon: XCircle,
    color: '#FF3B30',
    title: 'Failed',
    subtitle: 'Something went wrong',
  },
};

export default function AdaptStatusScreen() {
  const params = useLocalSearchParams<{ jobId: string; portalName?: string }>();
  const { jobId, portalName } = params;
  
  const [isDownloading, setIsDownloading] = useState(false);
  const [downloadProgress, setDownloadProgress] = useState(0);
  const [downloadedPath, setDownloadedPath] = useState<string | null>(null);
  
  // Animated spinner rotation
  const spinValue = React.useRef(new Animated.Value(0)).current;
  
  // Fetch adaptation status
  const { data: adaptStatus, refetch } = useQuery({
    queryKey: ['adapt', jobId],
    queryFn: () => schemasApi.getAdaptStatus(jobId!),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === 'processing' || status === 'pending' ? 2000 : false;
    },
  });

  // Animate spinner for processing state
  useEffect(() => {
    if (adaptStatus?.status === 'processing' || adaptStatus?.status === 'pending') {
      const animation = Animated.loop(
        Animated.timing(spinValue, {
          toValue: 1,
          duration: 1500,
          useNativeDriver: true,
        })
      );
      animation.start();
      return () => animation.stop();
    }
  }, [adaptStatus?.status, spinValue]);

  const spin = spinValue.interpolate({
    inputRange: [0, 1],
    outputRange: ['0deg', '360deg'],
  });

  const handleDownload = useCallback(async () => {
    if (!adaptStatus?.zip_url || !jobId) return;

    setIsDownloading(true);
    setDownloadProgress(0);

    try {
      const result = await downloadJobOutput(
        jobId,
        adaptStatus.zip_url,
        (progress) => setDownloadProgress(progress.progress)
      );

      if (!result.success) {
        throw new Error(result.error || 'Download failed');
      }

      setDownloadedPath(result.localPath);
      setDownloadProgress(1);

      // Auto-share after download
      await shareFile(result.localPath, {
        mimeType: 'application/zip',
        dialogTitle: `Save ${portalName || 'Portal'} Export`,
      });
    } catch (error) {
      console.error('Download error:', error);
      Alert.alert(
        'Download Failed',
        'Could not download the file. Please try again.',
        [{ text: 'OK' }]
      );
    } finally {
      setIsDownloading(false);
    }
  }, [jobId, adaptStatus?.zip_url, portalName]);

  const handleShare = useCallback(async () => {
    if (downloadedPath) {
      await shareFile(downloadedPath, {
        mimeType: 'application/zip',
        dialogTitle: `Share ${portalName || 'Portal'} Export`,
      });
    } else {
      // Download first, then share
      await handleDownload();
    }
  }, [downloadedPath, handleDownload, portalName]);

  const handleRetry = useCallback(() => {
    refetch();
  }, [refetch]);

  if (!jobId) {
    return (
      <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
        <View style={styles.errorContainer}>
          <Text style={styles.errorText}>No job specified</Text>
          <TouchableOpacity style={styles.backButton} onPress={() => router.back()}>
            <Text style={styles.backButtonText}>Go Back</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  const status = (adaptStatus?.status || 'pending') as AdaptStatus;
  const config = STATUS_CONFIG[status];
  const StatusIcon = config.icon;
  const isComplete = status === 'completed';
  const isFailed = status === 'failed';
  const isProcessing = status === 'processing' || status === 'pending';

  return (
    <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.headerButton}>
          <ArrowLeft size={24} color={Colors.palette.white} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>
          {portalName ? `${portalName} Export` : 'Exporting'}
        </Text>
        <View style={styles.headerButton} />
      </View>

      {/* Main Content */}
      <View style={styles.content}>
        {/* Status Icon */}
        <View style={[styles.iconContainer, { backgroundColor: config.color + '20' }]}>
          {isProcessing ? (
            <Animated.View style={{ transform: [{ rotate: spin }] }}>
              <StatusIcon size={64} color={config.color} />
            </Animated.View>
          ) : (
            <StatusIcon size={64} color={config.color} />
          )}
        </View>

        {/* Status Text */}
        <Text style={[styles.statusTitle, { color: config.color }]}>
          {config.title}
        </Text>
        <Text style={styles.statusSubtitle}>
          {isFailed && adaptStatus?.error 
            ? adaptStatus.error.message 
            : config.subtitle}
        </Text>

        {/* Progress Bar (during processing) */}
        {isProcessing && (
          <View style={styles.progressContainer}>
            <View style={styles.progressTrack}>
              <Animated.View 
                style={[
                  styles.progressBar, 
                  { backgroundColor: config.color }
                ]} 
              />
            </View>
            <Text style={styles.progressText}>This usually takes 5-10 seconds</Text>
          </View>
        )}

        {/* Download Progress (when downloading) */}
        {isDownloading && (
          <View style={styles.progressContainer}>
            <View style={styles.progressTrack}>
              <View 
                style={[
                  styles.progressBarStatic, 
                  { width: `${downloadProgress * 100}%` }
                ]} 
              />
            </View>
            <Text style={styles.progressText}>
              Downloading... {Math.round(downloadProgress * 100)}%
            </Text>
          </View>
        )}

        {/* File Info (when complete) */}
        {isComplete && adaptStatus?.zip_url && (
          <View style={styles.fileInfo}>
            <View style={styles.fileIcon}>
              <FileArchive size={24} color='#89C7FE' />
            </View>
            <View>
              <Text style={styles.fileName}>{portalName || 'Portal'}_export.zip</Text>
              <Text style={styles.fileSize}>Ready for download</Text>
            </View>
          </View>
        )}
      </View>

      {/* Action Buttons */}
      <View style={styles.bottomContainer}>
        {isComplete && (
          <>
            <TouchableOpacity
              style={styles.primaryButton}
              onPress={handleDownload}
              disabled={isDownloading}
              activeOpacity={0.8}
            >
              {isDownloading ? (
                <ActivityIndicator size="small" color={Colors.palette.white} />
              ) : (
                <>
                  <Download size={20} color={Colors.palette.white} />
                  <Text style={styles.primaryButtonText}>Download ZIP</Text>
                </>
              )}
            </TouchableOpacity>
            
            <TouchableOpacity
              style={styles.secondaryButton}
              onPress={handleShare}
              activeOpacity={0.8}
            >
              <Share2 size={20} color='#89C7FE' />
              <Text style={styles.secondaryButtonText}>Share</Text>
            </TouchableOpacity>
          </>
        )}

        {isFailed && (
          <TouchableOpacity
            style={styles.primaryButton}
            onPress={handleRetry}
            activeOpacity={0.8}
          >
            <RefreshCw size={20} color={Colors.palette.white} />
            <Text style={styles.primaryButtonText}>Retry</Text>
          </TouchableOpacity>
        )}

        <TouchableOpacity
          style={styles.linkButton}
          onPress={() => router.replace('/(tabs)/jobs')}
        >
          <Text style={styles.linkButtonText}>View All Jobs</Text>
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.palette.inkBlack,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  headerButton: {
    width: 40,
    height: 40,
    alignItems: 'center',
    justifyContent: 'center',
  },
  headerTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: Colors.palette.white,
  },
  content: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 32,
  },
  iconContainer: {
    width: 120,
    height: 120,
    borderRadius: 60,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 24,
  },
  statusTitle: {
    fontSize: 28,
    fontWeight: '700',
    marginBottom: 8,
  },
  statusSubtitle: {
    fontSize: 16,
    color: '#999',
    textAlign: 'center',
  },
  progressContainer: {
    width: '100%',
    marginTop: 32,
    alignItems: 'center',
  },
  progressTrack: {
    width: '100%',
    height: 6,
    backgroundColor: Colors.palette.shadowGrey,
    borderRadius: 3,
    overflow: 'hidden',
  },
  progressBar: {
    height: '100%',
    width: '30%',
    borderRadius: 3,
  },
  progressBarStatic: {
    height: '100%',
    backgroundColor: '#89C7FE',
    borderRadius: 3,
  },
  progressText: {
    fontSize: 12,
    color: '#666',
    marginTop: 12,
  },
  fileInfo: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.palette.shadowGrey,
    borderRadius: 16,
    padding: 16,
    marginTop: 32,
    gap: 16,
  },
  fileIcon: {
    width: 48,
    height: 48,
    borderRadius: 12,
    backgroundColor: '#89C7FE20',
    alignItems: 'center',
    justifyContent: 'center',
  },
  fileName: {
    fontSize: 14,
    fontWeight: '600',
    color: Colors.palette.white,
    marginBottom: 4,
  },
  fileSize: {
    fontSize: 12,
    color: '#999',
  },
  bottomContainer: {
    padding: 16,
    paddingBottom: 32,
    gap: 12,
  },
  primaryButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#1A2595',
    borderRadius: 16,
    height: 56,
    gap: 8,
  },
  primaryButtonText: {
    fontSize: 16,
    fontWeight: '600',
    color: Colors.palette.white,
  },
  secondaryButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: Colors.palette.shadowGrey,
    borderRadius: 16,
    height: 56,
    gap: 8,
  },
  secondaryButtonText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#89C7FE',
  },
  linkButton: {
    alignItems: 'center',
    paddingVertical: 12,
  },
  linkButtonText: {
    fontSize: 14,
    color: '#999',
  },
  errorContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 16,
  },
  errorText: {
    fontSize: 16,
    color: '#999',
  },
  backButton: {
    paddingHorizontal: 24,
    paddingVertical: 12,
    backgroundColor: Colors.palette.shadowGrey,
    borderRadius: 12,
  },
  backButtonText: {
    fontSize: 14,
    fontWeight: '600',
    color: Colors.palette.white,
  },
});
