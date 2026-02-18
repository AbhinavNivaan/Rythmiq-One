/**
 * Job Detail Screen
 * 
 * Shows detailed job information, download options, and portal export.
 */

import React, { useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  ActivityIndicator,
  Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router, useLocalSearchParams } from 'expo-router';
import { 
  ArrowLeft, 
  RefreshCw, 
  Download, 
  Share2, 
  FileOutput,
  Clock,
  CheckCircle,
  XCircle,
  Loader,
  Camera,
} from 'lucide-react-native';
import { useQuery } from '@tanstack/react-query';
import Colors from '../../constants/Colors';
import { documentsApi } from '../../services/api';
import { downloadJobOutput, shareFile, formatFileSize } from '../../services/download';

type JobStatusType = 'pending' | 'processing' | 'completed' | 'failed';

interface StatusConfig {
  icon: React.ComponentType<{ size: number; color: string }>;
  color: string;
  label: string;
}

const STATUS_CONFIG: Record<JobStatusType, StatusConfig> = {
  pending: { 
    icon: Clock, 
    color: '#FF9500', 
    label: 'Pending',
  },
  processing: { 
    icon: Loader, 
    color: Colors.palette.mayaBlue, 
    label: 'Processing',
  },
  completed: { 
    icon: CheckCircle, 
    color: '#34C759', 
    label: 'Completed',
  },
  failed: { 
    icon: XCircle, 
    color: '#FF3B30', 
    label: 'Failed',
  },
};

export default function JobDetailScreen() {
  const params = useLocalSearchParams<{ jobId: string }>();
  const jobId = params.jobId;
  
  const [isDownloading, setIsDownloading] = useState(false);
  const [downloadProgress, setDownloadProgress] = useState(0);

  // Fetch job status
  const { data: jobStatus, isLoading, refetch } = useQuery({
    queryKey: ['job', jobId],
    queryFn: () => documentsApi.getJobStatus(jobId!),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === 'processing' || status === 'pending' ? 5000 : false;
    },
  });

  const handleDownload = useCallback(async () => {
    if (!jobId || jobStatus?.status !== 'completed') return;

    setIsDownloading(true);
    setDownloadProgress(0);

    try {
      const { download_url } = await documentsApi.getJobOutput(jobId);
      
      if (!download_url) {
        throw new Error('Download URL not available');
      }

      const result = await downloadJobOutput(
        jobId,
        download_url,
        (progress) => setDownloadProgress(progress.progress)
      );

      if (!result.success) {
        throw new Error(result.error || 'Download failed');
      }

      setDownloadProgress(1);

      const shared = await shareFile(result.localPath, {
        mimeType: 'application/zip',
        dialogTitle: 'Save Processed Documents',
      });

      if (!shared) {
        Alert.alert(
          'Download Complete',
          `File saved (${formatFileSize(result.size)})`,
          [{ text: 'OK' }]
        );
      }
    } catch (error) {
      console.error('Download error:', error);
      Alert.alert(
        'Download Failed',
        'Could not download the file. Please try again.',
        [{ text: 'OK' }]
      );
    } finally {
      setIsDownloading(false);
      setDownloadProgress(0);
    }
  }, [jobId, jobStatus]);

  const handleShare = useCallback(async () => {
    await handleDownload();
  }, [handleDownload]);

  const handleExportForPortal = useCallback(() => {
    if (!jobId) return;
    router.push({
      pathname: '/(tabs)/portal-selector',
      params: { documentId: jobId },
    });
  }, [jobId]);

  if (!jobId) {
    return (
      <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
        <View style={styles.errorContainer}>
          <Text style={styles.errorText}>Job not found</Text>
          <TouchableOpacity style={styles.backButtonAlt} onPress={() => router.back()}>
            <Text style={styles.backButtonAltText}>Go Back</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  if (isLoading) {
    return (
      <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={Colors.palette.mayaBlue} />
          <Text style={styles.loadingText}>Loading job details...</Text>
        </View>
      </SafeAreaView>
    );
  }

  const status = (jobStatus?.status || 'pending') as JobStatusType;
  const statusConfig = STATUS_CONFIG[status];
  const StatusIcon = statusConfig.icon;
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
        <Text style={styles.headerTitle}>Job Details</Text>
        <TouchableOpacity onPress={() => refetch()} style={styles.headerButton}>
          <RefreshCw size={24} color={Colors.palette.white} />
        </TouchableOpacity>
      </View>

      <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
        {/* Status Card */}
        <View style={[styles.statusCard, { borderColor: statusConfig.color }]}>
          <View style={[styles.statusIconContainer, { backgroundColor: statusConfig.color + '20' }]}>
            {isProcessing ? (
              <ActivityIndicator size="large" color={statusConfig.color} />
            ) : (
              <StatusIcon size={48} color={statusConfig.color} />
            )}
          </View>
          <Text style={[styles.statusLabel, { color: statusConfig.color }]}>
            {statusConfig.label}
          </Text>
          {isProcessing && (
            <Text style={styles.processingHint}>
              This usually takes 10-30 seconds
            </Text>
          )}
        </View>

        {/* Job Info */}
        <View style={styles.infoSection}>
          <Text style={styles.sectionTitle}>Job Information</Text>
          
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>Job ID</Text>
            <Text style={styles.infoValue}>{jobId.substring(0, 8)}...</Text>
          </View>

          {jobStatus?.quality_score !== undefined && (
            <View style={styles.infoRow}>
              <Text style={styles.infoLabel}>Quality Score</Text>
              <View style={[
                styles.qualityBadge,
                { backgroundColor: jobStatus.quality_score >= 0.8 ? '#34C759' : '#FF9500' }
              ]}>
                <Text style={styles.qualityText}>
                  {Math.round(jobStatus.quality_score * 100)}%
                </Text>
              </View>
            </View>
          )}
        </View>

        {/* Error Details */}
        {isFailed && jobStatus?.error && (
          <View style={styles.errorSection}>
            <Text style={styles.sectionTitle}>Error Details</Text>
            <View style={styles.errorBox}>
              <XCircle size={20} color="#FF3B30" />
              <View style={styles.errorContent}>
                <Text style={styles.errorCode}>{jobStatus.error.code}</Text>
                <Text style={styles.errorMessage}>{jobStatus.error.message}</Text>
              </View>
            </View>
          </View>
        )}

        {/* Download Section */}
        {isComplete && (
          <View style={styles.actionSection}>
            <Text style={styles.sectionTitle}>Download</Text>
            
            <TouchableOpacity
              style={[styles.primaryButton, isDownloading && styles.buttonDisabled]}
              onPress={handleDownload}
              disabled={isDownloading}
              activeOpacity={0.8}
            >
              {isDownloading ? (
                <>
                  <ActivityIndicator color={Colors.palette.white} />
                  <Text style={styles.primaryButtonText}>
                    Downloading... {Math.round(downloadProgress * 100)}%
                  </Text>
                </>
              ) : (
                <>
                  <Download size={20} color={Colors.palette.white} />
                  <Text style={styles.primaryButtonText}>Download ZIP</Text>
                </>
              )}
            </TouchableOpacity>

            {isDownloading && (
              <View style={styles.progressBar}>
                <View 
                  style={[styles.progressFill, { width: `${downloadProgress * 100}%` }]} 
                />
              </View>
            )}

            <TouchableOpacity
              style={styles.secondaryButton}
              onPress={handleShare}
              disabled={isDownloading}
              activeOpacity={0.8}
            >
              <Share2 size={20} color={Colors.palette.mayaBlue} />
              <Text style={styles.secondaryButtonText}>Share</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* Export for Portal Section */}
        {isComplete && (
          <View style={styles.actionSection}>
            <Text style={styles.sectionTitle}>Export for Portal</Text>
            <Text style={styles.sectionDescription}>
              Adapt this document for a specific portal's requirements
            </Text>
            
            <TouchableOpacity
              style={styles.exportButton}
              onPress={handleExportForPortal}
              activeOpacity={0.8}
            >
              <FileOutput size={20} color={Colors.palette.white} />
              <Text style={styles.exportButtonText}>Select Portal</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* Retry Button for Failed Jobs */}
        {isFailed && (
          <View style={styles.actionSection}>
            <TouchableOpacity
              style={styles.retryButton}
              onPress={() => router.push('/(tabs)/capture')}
              activeOpacity={0.8}
            >
              <Camera size={20} color={Colors.palette.white} />
              <Text style={styles.retryButtonText}>Try Again</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* Spacer for bottom */}
        <View style={{ height: 32 }} />
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.palette.inkBlack,
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    gap: 16,
  },
  loadingText: {
    fontSize: 14,
    color: '#999',
  },
  errorContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    gap: 16,
  },
  errorText: {
    fontSize: 16,
    color: '#999',
  },
  backButtonAlt: {
    paddingHorizontal: 24,
    paddingVertical: 12,
    backgroundColor: Colors.palette.shadowGrey,
    borderRadius: 12,
  },
  backButtonAltText: {
    fontSize: 14,
    fontWeight: '600',
    color: Colors.palette.white,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
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
    paddingHorizontal: 16,
  },
  statusCard: {
    borderRadius: 20,
    padding: 32,
    alignItems: 'center',
    marginBottom: 24,
    backgroundColor: Colors.palette.shadowGrey,
    borderWidth: 2,
  },
  statusIconContainer: {
    width: 80,
    height: 80,
    borderRadius: 40,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 16,
  },
  statusLabel: {
    fontSize: 24,
    fontWeight: '700',
  },
  processingHint: {
    marginTop: 8,
    fontSize: 14,
    color: '#999',
  },
  infoSection: {
    backgroundColor: Colors.palette.shadowGrey,
    borderRadius: 16,
    padding: 16,
    marginBottom: 16,
  },
  sectionTitle: {
    fontSize: 12,
    fontWeight: '600',
    color: '#999',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: 12,
  },
  sectionDescription: {
    fontSize: 14,
    color: '#999',
    marginBottom: 16,
  },
  infoRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255, 255, 255, 0.05)',
  },
  infoLabel: {
    fontSize: 16,
    color: Colors.palette.white,
  },
  infoValue: {
    fontSize: 14,
    color: '#999',
    fontFamily: 'monospace',
  },
  qualityBadge: {
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 12,
  },
  qualityText: {
    color: Colors.palette.white,
    fontWeight: '600',
    fontSize: 14,
  },
  errorSection: {
    marginBottom: 16,
  },
  errorBox: {
    flexDirection: 'row',
    backgroundColor: 'rgba(255, 59, 48, 0.1)',
    borderRadius: 12,
    padding: 16,
    gap: 12,
  },
  errorContent: {
    flex: 1,
  },
  errorCode: {
    fontSize: 14,
    fontWeight: '600',
    color: '#FF3B30',
    marginBottom: 4,
  },
  errorMessage: {
    fontSize: 14,
    color: '#999',
  },
  actionSection: {
    backgroundColor: Colors.palette.shadowGrey,
    borderRadius: 16,
    padding: 16,
    marginBottom: 16,
  },
  primaryButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#34C759',
    padding: 16,
    borderRadius: 12,
    gap: 8,
    marginBottom: 12,
  },
  buttonDisabled: {
    opacity: 0.6,
  },
  primaryButtonText: {
    color: Colors.palette.white,
    fontSize: 16,
    fontWeight: '600',
  },
  progressBar: {
    height: 4,
    backgroundColor: 'rgba(255, 255, 255, 0.1)',
    borderRadius: 2,
    overflow: 'hidden',
    marginBottom: 12,
  },
  progressFill: {
    height: '100%',
    backgroundColor: '#34C759',
  },
  secondaryButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'transparent',
    padding: 12,
    borderRadius: 12,
    gap: 8,
    borderWidth: 1,
    borderColor: Colors.palette.mayaBlue,
  },
  secondaryButtonText: {
    color: Colors.palette.mayaBlue,
    fontSize: 16,
    fontWeight: '500',
  },
  exportButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: Colors.palette.trueCobalt,
    padding: 16,
    borderRadius: 12,
    gap: 8,
  },
  exportButtonText: {
    color: Colors.palette.white,
    fontSize: 16,
    fontWeight: '600',
  },
  retryButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: Colors.palette.trueCobalt,
    padding: 16,
    borderRadius: 12,
    gap: 8,
  },
  retryButtonText: {
    color: Colors.palette.white,
    fontSize: 16,
    fontWeight: '600',
  },
});
