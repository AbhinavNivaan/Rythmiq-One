/**
 * Job Detail Screen
 *
 * Shows detailed job information, download options, and portal export.
 * On completion, shows a one-time preview of the processed document.
 */

import React, { useState, useCallback, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  ActivityIndicator,
  Alert,
  Modal,
  Image,
} from 'react-native';
import * as SecureStore from 'expo-secure-store';
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
  X,
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
  hint?: string;
}

const STATUS_CONFIG: Record<JobStatusType, StatusConfig> = {
  pending: {
    icon: Clock,
    color: Colors.palette.amber,
    label: 'Pending',
    hint: 'Queued for processing',
  },
  processing: {
    icon: Loader,
    color: '#89C7FE',
    label: 'Processing',
    hint: 'This usually takes 10–30 seconds',
  },
  completed: {
    icon: CheckCircle,
    color: Colors.palette.green,
    label: 'Completed',
  },
  failed: {
    icon: XCircle,
    color: Colors.palette.red,
    label: 'Failed',
  },
};

export default function JobDetailScreen() {
  const params = useLocalSearchParams<{ jobId: string }>();
  const jobId = params.jobId;

  const [isDownloading, setIsDownloading] = useState(false);
  const [downloadProgress, setDownloadProgress] = useState(0);
  const [showPreviewModal, setShowPreviewModal] = useState(false);
  const [hasViewedPreview, setHasViewedPreview] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewLoadError, setPreviewLoadError] = useState(false);

  const { data: jobStatus, isLoading, refetch } = useQuery({
    queryKey: ['job', jobId],
    queryFn: () => documentsApi.getJobStatus(jobId!),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === 'processing' || status === 'pending' ? 5000 : false;
    },
  });

  const getPreviewSeenKey = (id: string) => `job_preview_seen_${id}`;

  useEffect(() => {
    const maybeShowOneTimePreview = async () => {
      if (!jobId || jobStatus?.status !== 'completed' || hasViewedPreview) return;
      try {
        const seen = await SecureStore.getItemAsync(getPreviewSeenKey(jobId));
        if (seen === '1') {
          setHasViewedPreview(true);
          return;
        }
        await loadPreviewImage();
      } catch (error) {
        console.error('Failed to check preview seen state:', error);
      }
    };
    maybeShowOneTimePreview();
  }, [jobStatus?.status, jobId, hasViewedPreview]);

  const loadPreviewImage = async () => {
    try {
      setPreviewLoadError(false);
      setPreviewUrl(jobStatus?.preview_url ?? null);
      setShowPreviewModal(true);
    } catch (error) {
      console.error('Failed to load preview:', error);
      setPreviewLoadError(true);
      setShowPreviewModal(true);
    }
  };

  const handleClosePreview = async () => {
    if (jobId) {
      try {
        await SecureStore.setItemAsync(getPreviewSeenKey(jobId), '1');
      } catch (error) {
        console.error('Failed to persist preview seen state:', error);
      }
    }
    setHasViewedPreview(true);
    setShowPreviewModal(false);
  };

  const handleDownload = useCallback(async () => {
    if (!jobId || jobStatus?.status !== 'completed' || !jobStatus?.preview_url) return;
    setIsDownloading(true);
    setDownloadProgress(0);
    try {
      const result = await downloadJobOutput(
        jobId,
        jobStatus.preview_url,
        (progress) => setDownloadProgress(progress.progress),
        'jpg'
      );
      if (!result.success) throw new Error(result.error || 'Download failed');
      setDownloadProgress(1);
      const shared = await shareFile(result.localPath, {
        mimeType: 'image/jpeg',
        dialogTitle: 'Save Processed Document',
      });
      if (!shared) {
        Alert.alert(
          'Download Complete',
          `Document saved (${formatFileSize(result.size)})\n\nYou can also find it in your device's Files app or Downloads.`,
          [{ text: 'OK' }]
        );
      }
    } catch (error) {
      console.error('Download error:', error);
      Alert.alert('Download Failed', 'Could not download the document. Please try again.', [{ text: 'OK' }]);
    } finally {
      setIsDownloading(false);
      setDownloadProgress(0);
    }
  }, [jobId, jobStatus]);

  const handleShare = useCallback(async () => {
    if (!jobId || jobStatus?.status !== 'completed' || !jobStatus?.download_url) return;
    setIsDownloading(true);
    setDownloadProgress(0);
    try {
      const result = await downloadJobOutput(
        jobId,
        jobStatus.download_url,
        (progress) => setDownloadProgress(progress.progress),
        'zip'
      );
      if (!result.success) throw new Error(result.error || 'Download failed');
      setDownloadProgress(1);
      const shared = await shareFile(result.localPath, {
        mimeType: 'application/zip',
        dialogTitle: 'Share Full Archive',
      });
      if (!shared) {
        Alert.alert('Archive Ready', `Full archive saved (${formatFileSize(result.size)})`, [{ text: 'OK' }]);
      }
    } catch (error) {
      console.error('Share error:', error);
      Alert.alert('Share Failed', 'Could not share the file. Please try again.', [{ text: 'OK' }]);
    } finally {
      setIsDownloading(false);
      setDownloadProgress(0);
    }
  }, [jobId, jobStatus]);

  const handleExportForPortal = useCallback(() => {
    if (!jobId) return;
    router.push({ pathname: '/(tabs)/portal-selector', params: { documentId: jobId } });
  }, [jobId]);

  if (!jobId) {
    return (
      <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
        <View style={styles.centeredContainer}>
          <Text style={styles.emptyText}>Job not found</Text>
          <TouchableOpacity style={styles.pill} onPress={() => router.back()}>
            <Text style={styles.pillText}>Go Back</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  if (isLoading) {
    return (
      <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
        <View style={styles.centeredContainer}>
          <ActivityIndicator size="large" color="#89C7FE" />
          <Text style={styles.emptyText}>Loading job details...</Text>
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
          <RefreshCw size={20} color="#999" />
        </TouchableOpacity>
      </View>

      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        {/* Status Card */}
        <View style={styles.card}>
          <View style={[styles.statusIconWrap, { backgroundColor: statusConfig.color + '18' }]}>
            {isProcessing ? (
              <ActivityIndicator size="large" color={statusConfig.color} />
            ) : (
              <StatusIcon size={36} color={statusConfig.color} />
            )}
          </View>
          <View style={styles.statusTextWrap}>
            <Text style={[styles.statusLabel, { color: statusConfig.color }]}>
              {statusConfig.label}
            </Text>
            {statusConfig.hint && (
              <Text style={styles.statusHint}>{statusConfig.hint}</Text>
            )}
          </View>
          {jobStatus?.quality_score !== undefined && isComplete && (
            <View style={[
              styles.qualityBadge,
              { backgroundColor: jobStatus.quality_score >= 0.8 ? Colors.palette.green + '20' : Colors.palette.amber + '20' }
            ]}>
              <Text style={[
                styles.qualityText,
                { color: jobStatus.quality_score >= 0.8 ? Colors.palette.green : Colors.palette.amber }
              ]}>
                {Math.round(jobStatus.quality_score * 100)}% quality
              </Text>
            </View>
          )}
        </View>

        {/* Job Information */}
        <View style={styles.card}>
          <Text style={styles.sectionLabel}>Job Information</Text>

          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>Job ID</Text>
            <Text style={styles.infoValue}>{jobId?.substring(0, 8)}…</Text>
          </View>

          {jobStatus?.created_at && (
            <View style={styles.infoRow}>
              <Text style={styles.infoLabel}>Created</Text>
              <Text style={styles.infoValue}>{new Date(jobStatus.created_at).toLocaleTimeString()}</Text>
            </View>
          )}

          {jobStatus?.started_at && (
            <View style={styles.infoRow}>
              <Text style={styles.infoLabel}>Started</Text>
              <Text style={styles.infoValue}>{new Date(jobStatus.started_at).toLocaleTimeString()}</Text>
            </View>
          )}

          {jobStatus?.completed_at && (
            <View style={styles.infoRow}>
              <Text style={styles.infoLabel}>Completed</Text>
              <Text style={styles.infoValue}>{new Date(jobStatus.completed_at).toLocaleTimeString()}</Text>
            </View>
          )}

          {jobStatus?.started_at && jobStatus?.completed_at && (
            <View style={[styles.infoRow, styles.infoRowLast]}>
              <Text style={styles.infoLabel}>Processing Time</Text>
              <Text style={styles.infoValue}>
                {Math.round(
                  (new Date(jobStatus.completed_at).getTime() - new Date(jobStatus.started_at).getTime()) / 1000
                )}s
              </Text>
            </View>
          )}
        </View>

        {/* Error Details */}
        {isFailed && (jobStatus?.error || jobStatus?.error_details) && (
          <View style={[styles.card, styles.errorCard]}>
            <View style={styles.errorRow}>
              <XCircle size={18} color={Colors.palette.red} />
              <View style={styles.errorTextWrap}>
                <Text style={styles.errorCode}>
                  {jobStatus.error?.code || jobStatus.error_details?.code || 'ERROR'}
                </Text>
                <Text style={styles.errorMessage}>
                  {jobStatus.error?.message || jobStatus.error_details?.message || 'An unknown error occurred'}
                </Text>
              </View>
            </View>
          </View>
        )}

        {/* Actions — Completed */}
        {isComplete && (
          <>
            {/* Download */}
            <TouchableOpacity
              style={[styles.pillButton, styles.pillPrimary, isDownloading && styles.pillDisabled]}
              onPress={handleDownload}
              disabled={isDownloading}
              activeOpacity={0.8}
            >
              {isDownloading ? (
                <>
                  <ActivityIndicator color={Colors.palette.inkBlack} />
                  <Text style={[styles.pillButtonText, styles.pillPrimaryText]}>
                    Downloading… {Math.round(downloadProgress * 100)}%
                  </Text>
                </>
              ) : (
                <>
                  <Download size={20} color={Colors.palette.inkBlack} />
                  <Text style={[styles.pillButtonText, styles.pillPrimaryText]}>Download File</Text>
                </>
              )}
            </TouchableOpacity>

            {isDownloading && (
              <View style={styles.progressBar}>
                <View style={[styles.progressFill, { width: `${downloadProgress * 100}%` as any }]} />
              </View>
            )}

            {/* Secondary action row */}
            <View style={styles.actionRow}>
              <TouchableOpacity
                style={styles.actionCard}
                onPress={handleShare}
                disabled={isDownloading}
                activeOpacity={0.8}
              >
                <View style={styles.actionCardIcon}>
                  <Share2 size={22} color={Colors.palette.white} />
                </View>
                <Text style={styles.actionCardTitle}>Archive</Text>
                <Text style={styles.actionCardDesc}>Download full ZIP</Text>
              </TouchableOpacity>

              <TouchableOpacity
                style={styles.actionCard}
                onPress={handleExportForPortal}
                activeOpacity={0.8}
              >
                <View style={styles.actionCardIcon}>
                  <FileOutput size={22} color={Colors.palette.white} />
                </View>
                <Text style={styles.actionCardTitle}>Export</Text>
                <Text style={styles.actionCardDesc}>Send to portal</Text>
              </TouchableOpacity>
            </View>
          </>
        )}

        {/* Retry — Failed */}
        {isFailed && (
          <TouchableOpacity
            style={[styles.pillButton, styles.pillSecondary]}
            onPress={() => router.push('/(tabs)/capture')}
            activeOpacity={0.8}
          >
            <Camera size={20} color={Colors.palette.white} />
            <Text style={styles.pillButtonText}>Try Again</Text>
          </TouchableOpacity>
        )}

        <View style={{ height: 32 }} />
      </ScrollView>

      {/* Completion Preview Modal */}
      <Modal
        visible={showPreviewModal}
        transparent={true}
        animationType="fade"
        onRequestClose={handleClosePreview}
      >
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Document Preview</Text>
              <TouchableOpacity onPress={handleClosePreview} style={styles.modalCloseButton}>
                <X size={22} color="#999" />
              </TouchableOpacity>
            </View>

            <ScrollView style={styles.modalBody} showsVerticalScrollIndicator={false}>
              <View style={styles.previewHero}>
                <View style={[styles.statusIconWrap, { backgroundColor: Colors.palette.green + '18' }]}>
                  <CheckCircle size={36} color={Colors.palette.green} />
                </View>
                <Text style={styles.previewHeroTitle}>Processing Complete!</Text>
                <Text style={styles.previewHeroSubtitle}>
                  Your document has been successfully processed and saved.
                </Text>
              </View>

              <View style={styles.card}>
                <Text style={styles.sectionLabel}>One-Time Preview</Text>
                {previewUrl && !previewLoadError ? (
                  <Image
                    source={{ uri: previewUrl }}
                    style={styles.previewImage}
                    resizeMode="contain"
                    onError={() => setPreviewLoadError(true)}
                  />
                ) : (
                  <View style={styles.previewUnavailable}>
                    <Text style={[styles.errorCode, { color: Colors.palette.amber }]}>Preview unavailable</Text>
                    <Text style={styles.errorMessage}>
                      The preview image couldn't be loaded. You can still download the output below.
                    </Text>
                  </View>
                )}
              </View>

              <Text style={[styles.sectionLabel, { marginBottom: 12 }]}>What's Next?</Text>

              {[
                { n: '1', title: 'Download your file', desc: 'Save the processed document to your device.' },
                { n: '2', title: 'Export for a portal', desc: 'Adapt the document for specific portal requirements.' },
                { n: '3', title: 'Find it on the dashboard', desc: 'Use the search bar to access your documents anytime.' },
              ].map((step) => (
                <View key={step.n} style={styles.stepCard}>
                  <View style={styles.stepNumber}>
                    <Text style={styles.stepNumberText}>{step.n}</Text>
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.stepTitle}>{step.title}</Text>
                    <Text style={styles.stepDesc}>{step.desc}</Text>
                  </View>
                </View>
              ))}

              <Text style={styles.previewNote}>
                This preview only shows once. Find completed documents via Dashboard search.
              </Text>
            </ScrollView>

            <TouchableOpacity style={[styles.pillButton, styles.pillPrimary, styles.modalConfirm]} onPress={handleClosePreview}>
              <Text style={[styles.pillButtonText, styles.pillPrimaryText]}>Got it</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.palette.inkBlack,
  },

  // ── Header ─────────────────────────────────────────────
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 24,
    paddingTop: 8,
    paddingBottom: 16,
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

  // ── Scroll ─────────────────────────────────────────────
  scroll: {
    flex: 1,
  },
  scrollContent: {
    paddingHorizontal: 24,
    paddingTop: 4,
  },

  // ── Card (matches ActionCard visual DNA) ───────────────
  card: {
    backgroundColor: Colors.palette.shadowGrey,
    borderRadius: 24,
    padding: 20,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.05)',
  },
  errorCard: {
    borderColor: Colors.palette.red + '30',
    backgroundColor: 'rgba(255, 59, 48, 0.06)',
  },

  // ── Status card internals ──────────────────────────────
  statusIconWrap: {
    width: 64,
    height: 64,
    borderRadius: 18,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 14,
  },
  statusTextWrap: {
    gap: 4,
  },
  statusLabel: {
    fontSize: 22,
    fontWeight: '700',
  },
  statusHint: {
    fontSize: 13,
    color: '#999',
  },
  qualityBadge: {
    alignSelf: 'flex-start',
    marginTop: 12,
    paddingHorizontal: 12,
    paddingVertical: 5,
    borderRadius: 20,
  },
  qualityText: {
    fontSize: 13,
    fontWeight: '600',
  },

  // ── Info rows ──────────────────────────────────────────
  sectionLabel: {
    fontSize: 11,
    fontWeight: '600',
    color: '#666',
    textTransform: 'uppercase',
    letterSpacing: 0.8,
    marginBottom: 14,
  },
  infoRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 11,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255, 255, 255, 0.05)',
  },
  infoRowLast: {
    borderBottomWidth: 0,
    paddingBottom: 0,
  },
  infoLabel: {
    fontSize: 15,
    color: Colors.palette.white,
  },
  infoValue: {
    fontSize: 14,
    color: '#999',
    fontFamily: 'monospace',
  },

  // ── Error box ──────────────────────────────────────────
  errorRow: {
    flexDirection: 'row',
    gap: 10,
    alignItems: 'flex-start',
  },
  errorTextWrap: {
    flex: 1,
  },
  errorCode: {
    fontSize: 13,
    fontWeight: '600',
    color: Colors.palette.red,
    marginBottom: 3,
  },
  errorMessage: {
    fontSize: 13,
    color: '#999',
    lineHeight: 19,
  },

  // ── Pill buttons ───────────────────────────────────────
  pillButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    height: 56,
    borderRadius: 28,
    gap: 10,
    marginBottom: 12,
  },
  pillPrimary: {
    backgroundColor: Colors.palette.green,
  },
  pillSecondary: {
    backgroundColor: Colors.palette.shadowGrey,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.1)',
  },
  pillDisabled: {
    opacity: 0.55,
  },
  pillButtonText: {
    fontSize: 16,
    fontWeight: '600',
    color: Colors.palette.white,
  },
  pillPrimaryText: {
    color: Colors.palette.inkBlack,
  },

  // ── Progress bar ───────────────────────────────────────
  progressBar: {
    height: 3,
    backgroundColor: 'rgba(255, 255, 255, 0.08)',
    borderRadius: 2,
    overflow: 'hidden',
    marginBottom: 12,
    marginHorizontal: 4,
  },
  progressFill: {
    height: '100%',
    backgroundColor: Colors.palette.green,
    borderRadius: 2,
  },

  // ── Action card row (matches dashboard grid) ───────────
  actionRow: {
    flexDirection: 'row',
    gap: 12,
    marginBottom: 12,
  },
  actionCard: {
    flex: 1,
    backgroundColor: Colors.palette.shadowGrey,
    borderRadius: 24,
    padding: 16,
    minHeight: 120,
    justifyContent: 'space-between',
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.05)',
  },
  actionCardIcon: {
    width: 44,
    height: 44,
    borderRadius: 13,
    backgroundColor: 'rgba(255, 255, 255, 0.1)',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 10,
  },
  actionCardTitle: {
    fontSize: 16,
    fontWeight: 'bold',
    color: Colors.palette.white,
    marginBottom: 2,
  },
  actionCardDesc: {
    fontSize: 11,
    color: '#999',
    lineHeight: 15,
  },

  // ── Empty / loading states ─────────────────────────────
  centeredContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    gap: 16,
    paddingHorizontal: 24,
  },
  emptyText: {
    fontSize: 15,
    color: '#999',
  },
  pill: {
    paddingHorizontal: 28,
    paddingVertical: 14,
    backgroundColor: Colors.palette.shadowGrey,
    borderRadius: 28,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.08)',
  },
  pillText: {
    fontSize: 15,
    fontWeight: '600',
    color: Colors.palette.white,
  },

  // ── Modal ──────────────────────────────────────────────
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.8)',
    justifyContent: 'flex-end',
  },
  modalContent: {
    backgroundColor: Colors.palette.inkBlack,
    borderTopLeftRadius: 32,
    borderTopRightRadius: 32,
    maxHeight: '92%',
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.07)',
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 24,
    paddingTop: 24,
    paddingBottom: 16,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255, 255, 255, 0.05)',
  },
  modalTitle: {
    fontSize: 17,
    fontWeight: '600',
    color: Colors.palette.white,
  },
  modalCloseButton: {
    width: 36,
    height: 36,
    alignItems: 'center',
    justifyContent: 'center',
  },
  modalBody: {
    paddingHorizontal: 24,
    paddingTop: 24,
  },
  modalConfirm: {
    marginHorizontal: 24,
    marginBottom: 24,
    marginTop: 8,
  },

  // ── Preview modal content ──────────────────────────────
  previewHero: {
    alignItems: 'center',
    marginBottom: 24,
  },
  previewHeroTitle: {
    fontSize: 20,
    fontWeight: '700',
    color: Colors.palette.white,
    marginTop: 4,
    marginBottom: 6,
  },
  previewHeroSubtitle: {
    fontSize: 14,
    color: '#999',
    textAlign: 'center',
    lineHeight: 20,
  },
  previewImage: {
    width: '100%',
    height: 240,
    borderRadius: 14,
    backgroundColor: Colors.palette.shadowGrey,
    marginTop: 4,
  },
  previewUnavailable: {
    backgroundColor: Colors.palette.amber + '12',
    borderRadius: 14,
    padding: 14,
    marginTop: 4,
  },

  // ── Step cards ─────────────────────────────────────────
  stepCard: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    backgroundColor: Colors.palette.shadowGrey,
    borderRadius: 18,
    padding: 16,
    marginBottom: 10,
    gap: 14,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.05)',
  },
  stepNumber: {
    width: 34,
    height: 34,
    borderRadius: 17,
    backgroundColor: 'rgba(255, 255, 255, 0.1)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  stepNumberText: {
    fontSize: 14,
    fontWeight: '700',
    color: Colors.palette.white,
  },
  stepTitle: {
    fontSize: 14,
    fontWeight: '600',
    color: Colors.palette.white,
    marginBottom: 3,
  },
  stepDesc: {
    fontSize: 12,
    color: '#999',
    lineHeight: 17,
  },
  previewNote: {
    fontSize: 11,
    color: '#555',
    textAlign: 'center',
    marginTop: 8,
    marginBottom: 20,
    lineHeight: 16,
  },
});
