/**
 * Adapt Status Screen
 *
 * Shows adaptation job progress and provides download when complete.
 * Handles one or more adapt jobs (e.g. photo + signature for a single portal export).
 */

import React, { useState, useCallback, useEffect, useMemo } from 'react';
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
import { useQueries } from '@tanstack/react-query';
import Colors from '../../constants/Colors';
import { documentsApi, JobStatus } from '../../services/api';
import { downloadJobOutput, shareFile } from '../../services/download';

type AdaptStatus = 'pending' | 'processing' | 'completed' | 'failed';

const STATUS_CONFIG: Record<AdaptStatus, {
  color: string;
  title: (count: number) => string;
  subtitle: string;
}> = {
  pending: {
    color: '#FF9500',
    title: (n) => n === 1 ? 'Queued' : `Queued (0 of ${n})`,
    subtitle: 'Waiting to start...',
  },
  processing: {
    color: '#89C7FE',
    title: (n) => n === 1 ? 'Adapting' : `Adapting documents...`,
    subtitle: 'Preparing your documents...',
  },
  completed: {
    color: '#34C759',
    title: (n) => n === 1 ? 'Ready!' : `${n} Documents Ready!`,
    subtitle: 'Your export is ready to download',
  },
  failed: {
    color: '#FF3B30',
    title: (n) => n === 1 ? 'Failed' : 'Export Failed',
    subtitle: 'Something went wrong',
  },
};

export default function AdaptStatusScreen() {
  const params = useLocalSearchParams<{ jobIds: string; portalName?: string }>();
  const { jobIds: jobIdsParam, portalName } = params;

  const jobIdList = useMemo(() => {
    try { return JSON.parse(jobIdsParam || '[]') as string[]; }
    catch { return []; }
  }, [jobIdsParam]);

  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  // Animated spinner rotation
  const spinValue = React.useRef(new Animated.Value(0)).current;

  const queries = useQueries({
    queries: jobIdList.map(id => ({
      queryKey: ['adapt-job', id],
      queryFn: () => documentsApi.getJobStatus(id),
      enabled: !!id,
      refetchInterval: (query: any) => {
        const s = query.state.data?.status;
        return s === 'pending' || s === 'processing' ? 2000 : false;
      },
    })),
  });

  const statuses = queries.map(q => q.data).filter(Boolean) as JobStatus[];
  const allComplete = jobIdList.length > 0 && statuses.length === jobIdList.length && statuses.every(s => s.status === 'completed');
  const anyFailed   = statuses.some(s => s.status === 'failed');
  const anyProcessing = statuses.some(s => s.status === 'pending' || s.status === 'processing');

  const aggregateStatus: AdaptStatus = anyFailed ? 'failed' : allComplete ? 'completed' : 'processing';
  const config = STATUS_CONFIG[aggregateStatus];
  const isProcessing = aggregateStatus === 'processing';

  // Animate spinner while any job is processing
  useEffect(() => {
    if (isProcessing) {
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
  }, [isProcessing, spinValue]);

  const spin = spinValue.interpolate({
    inputRange: [0, 1],
    outputRange: ['0deg', '360deg'],
  });

  const handleDownload = useCallback(async (job: JobStatus) => {
    if (!job.download_url) return;
    setDownloadingId(job.job_id);
    try {
      const result = await downloadJobOutput(
        job.job_id,
        job.download_url,
        () => {},
      );
      if (!result.success) throw new Error(result.error || 'Download failed');
      await shareFile(result.localPath, {
        mimeType: 'application/zip',
        dialogTitle: `Save ${portalName || 'Portal'} Export`,
      });
    } catch (error) {
      Alert.alert('Download Failed', 'Could not download the file. Please try again.');
    } finally {
      setDownloadingId(null);
    }
  }, [portalName]);

  const handleRetryAll = useCallback(() => {
    queries.forEach(q => q.refetch());
  }, [queries]);

  if (!jobIdList.length) {
    return (
      <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
        <View style={styles.errorContainer}>
          <Text style={styles.errorText}>No jobs specified</Text>
          <TouchableOpacity style={styles.backButton} onPress={() => router.back()}>
            <Text style={styles.backButtonText}>Go Back</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  const StatusIcon = anyFailed ? XCircle : allComplete ? CheckCircle : RefreshCw;

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
          {config.title(jobIdList.length)}
        </Text>
        <Text style={styles.statusSubtitle}>
          {anyFailed && statuses.find(s => s.status === 'failed')?.error_details?.message
            ? statuses.find(s => s.status === 'failed')!.error_details!.message
            : config.subtitle}
        </Text>

        {/* Progress indicator while processing */}
        {isProcessing && (
          <View style={styles.progressContainer}>
            <View style={styles.progressTrack}>
              <Animated.View style={[styles.progressBar, { backgroundColor: config.color }]} />
            </View>
            <Text style={styles.progressText}>This usually takes 5–10 seconds</Text>
          </View>
        )}

        {/* Per-job download items when complete */}
        {allComplete && (
          <View style={styles.fileList}>
            {statuses.map((job) => (
              <View key={job.job_id} style={styles.fileItem}>
                <View style={styles.fileIcon}>
                  <FileArchive size={20} color="#89C7FE" />
                </View>
                <Text style={styles.fileName} numberOfLines={1}>
                  {portalName || 'Portal'}_{job.document_type || 'export'}.zip
                </Text>
                <TouchableOpacity
                  style={[styles.downloadButton, downloadingId === job.job_id && styles.downloadButtonDisabled]}
                  onPress={() => handleDownload(job)}
                  disabled={downloadingId === job.job_id}
                >
                  {downloadingId === job.job_id
                    ? <ActivityIndicator size="small" color={Colors.palette.white} />
                    : <Download size={16} color={Colors.palette.white} />}
                </TouchableOpacity>
              </View>
            ))}
          </View>
        )}
      </View>

      {/* Bottom actions */}
      <View style={styles.bottomContainer}>
        {anyFailed && (
          <TouchableOpacity style={styles.primaryButton} onPress={handleRetryAll} activeOpacity={0.8}>
            <RefreshCw size={20} color={Colors.palette.white} />
            <Text style={styles.primaryButtonText}>Retry</Text>
          </TouchableOpacity>
        )}

        {allComplete && jobIdList.length > 1 && (
          <TouchableOpacity
            style={styles.primaryButton}
            onPress={() => statuses.forEach(j => j.download_url && handleDownload(j))}
            disabled={!!downloadingId}
            activeOpacity={0.8}
          >
            {downloadingId
              ? <ActivityIndicator size="small" color={Colors.palette.white} />
              : <>
                  <Download size={20} color={Colors.palette.white} />
                  <Text style={styles.primaryButtonText}>Download All</Text>
                </>}
          </TouchableOpacity>
        )}

        {allComplete && jobIdList.length === 1 && (
          <TouchableOpacity
            style={styles.primaryButton}
            onPress={() => statuses[0]?.download_url && handleDownload(statuses[0])}
            disabled={!!downloadingId}
            activeOpacity={0.8}
          >
            {downloadingId
              ? <ActivityIndicator size="small" color={Colors.palette.white} />
              : <>
                  <Download size={20} color={Colors.palette.white} />
                  <Text style={styles.primaryButtonText}>Download ZIP</Text>
                </>}
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
  progressText: {
    fontSize: 12,
    color: '#666',
    marginTop: 12,
  },
  fileList: {
    width: '100%',
    marginTop: 32,
    gap: 10,
  },
  fileItem: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.palette.shadowGrey,
    borderRadius: 14,
    padding: 14,
    gap: 12,
  },
  fileIcon: {
    width: 40,
    height: 40,
    borderRadius: 10,
    backgroundColor: '#89C7FE20',
    alignItems: 'center',
    justifyContent: 'center',
  },
  fileName: {
    flex: 1,
    fontSize: 14,
    fontWeight: '500',
    color: Colors.palette.white,
  },
  downloadButton: {
    width: 36,
    height: 36,
    borderRadius: 10,
    backgroundColor: '#1A2595',
    alignItems: 'center',
    justifyContent: 'center',
  },
  downloadButtonDisabled: {
    opacity: 0.5,
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
