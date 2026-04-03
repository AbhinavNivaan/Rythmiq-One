/**
 * Document Viewer Screen
 *
 * Shows the actual processed document image with download and export actions.
 * Navigated to from search results, job lists, or anywhere a jobId is available.
 */

import React, { useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Image,
  ActivityIndicator,
  Alert,
  ScrollView,
  Dimensions,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router, useLocalSearchParams } from 'expo-router';
import {
  ArrowLeft,
  Download,
  Share2,
  Calendar,
  FileText,
  ImageIcon,
  PenLine,
} from 'lucide-react-native';
import { useQuery } from '@tanstack/react-query';
import Colors from '../../constants/Colors';
import { documentsApi, JobStatus } from '../../services/api';
import { downloadJobOutput, shareFile, outputFormatToMime } from '../../services/download';

const { height: SCREEN_HEIGHT } = Dimensions.get('window');
const IMAGE_AREA_HEIGHT = SCREEN_HEIGHT * 0.42;

// ── Helpers ──────────────────────────────────────────────────────────────────

function formatDate(iso?: string): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleDateString('en-IN', {
      day: 'numeric',
      month: 'long',
      year: 'numeric',
    });
  } catch {
    return '—';
  }
}

function documentTitle(job: JobStatus): string {
  return job.document_subtype || job.document_category || job.document_type || 'Document';
}

function typeIcon(job: JobStatus) {
  switch (job.document_type) {
    case 'signature': return PenLine;
    case 'photo':     return ImageIcon;
    default:          return FileText;
  }
}

const STATUS_COLOR: Record<string, string> = {
  completed:  Colors.palette.green,
  processing: '#89C7FE',
  pending:    Colors.palette.amber,
  failed:     Colors.palette.red,
};

const STATUS_LABEL: Record<string, string> = {
  completed:  'Done',
  processing: 'Processing',
  pending:    'Pending',
  failed:     'Failed',
};

// ── Main screen ───────────────────────────────────────────────────────────────

export default function DocumentViewerScreen() {
  const { jobId } = useLocalSearchParams<{ jobId: string }>();

  const [imageLoading, setImageLoading] = useState(true);
  const [imageError, setImageError]     = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);
  const [downloadProgress, setDownloadProgress] = useState(0);

  const { data: job, isLoading } = useQuery({
    queryKey: ['job', jobId],
    queryFn: () => documentsApi.getJobStatus(jobId!),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const s = query.state.data?.status;
      return s === 'processing' || s === 'pending' ? 5000 : false;
    },
  });

  const handleDownload = useCallback(async () => {
    if (!job || job.status !== 'completed') return;

    const isEncrypted = job.output_encrypted === true;
    const downloadTarget =
      (!isEncrypted && job.output_url) ? job.output_url
      : job.preview_url                ? job.preview_url
      : null;

    if (!downloadTarget) {
      Alert.alert('File Not Ready', 'The processed file is not yet available.');
      return;
    }

    setIsDownloading(true);
    setDownloadProgress(0);
    try {
      const usingPreview = !(!isEncrypted && job.output_url) && !!job.preview_url;
      const { mimeType, ext } = outputFormatToMime(job.output_format);
      const fileExt  = usingPreview ? 'jpg' : ext;
      const fileMime = usingPreview ? 'image/jpeg' : mimeType;

      const result = await downloadJobOutput(
        jobId!,
        downloadTarget,
        (p) => setDownloadProgress(p.progress),
        fileExt,
      );
      if (!result.success) throw new Error(result.error || 'Download failed');
      await shareFile(result.localPath, { mimeType: fileMime, dialogTitle: 'Save Document' });
    } catch {
      Alert.alert('Download Failed', 'Could not download the file. Please try again.');
    } finally {
      setIsDownloading(false);
      setDownloadProgress(0);
    }
  }, [job, jobId]);

  const handleExport = useCallback(() => {
    if (!jobId) return;
    router.push({ pathname: '/(tabs)/portal-selector', params: { documentId: jobId } } as any);
  }, [jobId]);

  // ── Loading state ────────────────────────────────────────────────────────

  if (!jobId || (isLoading && !job)) {
    return (
      <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
        <Header />
        <View style={styles.centered}>
          <ActivityIndicator size="large" color="#89C7FE" />
        </View>
      </SafeAreaView>
    );
  }

  if (!job) {
    return (
      <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
        <Header />
        <View style={styles.centered}>
          <Text style={styles.errorText}>Document not found</Text>
          <TouchableOpacity onPress={() => router.back()} style={styles.goBackBtn}>
            <Text style={styles.goBackText}>Go Back</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  const isCompleted   = job.status === 'completed';
  const statusColor   = STATUS_COLOR[job.status] ?? Colors.palette.amber;
  const statusLabel   = STATUS_LABEL[job.status] ?? job.status;
  const title         = documentTitle(job);
  const TypeIcon      = typeIcon(job);
  const typeLabel     = job.document_type
    ? job.document_type.charAt(0).toUpperCase() + job.document_type.slice(1)
    : 'Document';

  const canDownload = isCompleted && !isDownloading;
  const canExport   = isCompleted;

  return (
    <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
      <Header title={title} />

      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
        bounces={false}
      >
        {/* ── Document image area ─────────────────────────────────────────── */}
        <View style={styles.imageArea}>
          {isCompleted && job.preview_url ? (
            <>
              {imageLoading && (
                <View style={StyleSheet.absoluteFill}>
                  <ActivityIndicator
                    style={styles.centered}
                    size="large"
                    color="#aaa"
                  />
                </View>
              )}
              {imageError ? (
                <View style={styles.imagePlaceholder}>
                  <FileText size={48} color="#bbb" />
                  <Text style={styles.imagePlaceholderText}>Preview unavailable</Text>
                </View>
              ) : (
                <Image
                  source={{ uri: job.preview_url }}
                  style={styles.docImage}
                  resizeMode="contain"
                  onLoad={() => setImageLoading(false)}
                  onError={() => { setImageLoading(false); setImageError(true); }}
                />
              )}
            </>
          ) : (
            <View style={styles.imagePlaceholder}>
              {job.status === 'processing' || job.status === 'pending' ? (
                <>
                  <ActivityIndicator size="large" color="#89C7FE" />
                  <Text style={[styles.imagePlaceholderText, { color: '#89C7FE', marginTop: 16 }]}>
                    {job.status === 'processing' ? 'Processing document…' : 'Queued for processing'}
                  </Text>
                </>
              ) : (
                <>
                  <FileText size={48} color="#bbb" />
                  <Text style={styles.imagePlaceholderText}>No preview available</Text>
                </>
              )}
            </View>
          )}
        </View>

        {/* ── Metadata + actions ──────────────────────────────────────────── */}
        <View style={styles.infoCard}>
          {/* Title */}
          <Text style={styles.docTitle} numberOfLines={2}>{title}</Text>

          {/* Type + status badges */}
          <View style={styles.badgeRow}>
            <View style={styles.typeBadge}>
              <TypeIcon size={13} color="#aaa" />
              <Text style={styles.typeBadgeText}>{typeLabel}</Text>
            </View>
            <View style={[styles.statusBadge, { backgroundColor: statusColor + '22', borderColor: statusColor + '55' }]}>
              <View style={[styles.statusDot, { backgroundColor: statusColor }]} />
              <Text style={[styles.statusBadgeText, { color: statusColor }]}>{statusLabel}</Text>
            </View>
          </View>

          {/* Date */}
          {job.created_at && (
            <View style={styles.metaRow}>
              <Calendar size={15} color="#555" />
              <Text style={styles.metaText}>{formatDate(job.created_at)}</Text>
            </View>
          )}

          {/* Job ID */}
          <View style={styles.metaRow}>
            <Text style={styles.metaLabel}>Job ID</Text>
            <Text style={styles.metaMono}>#{job.job_id.substring(0, 8)}</Text>
          </View>

          {/* Actions */}
          <View style={styles.actionRow}>
            <TouchableOpacity
              style={[styles.actionBtn, styles.downloadBtn, !canDownload && styles.actionBtnDisabled]}
              onPress={handleDownload}
              activeOpacity={0.8}
              disabled={!canDownload}
            >
              {isDownloading ? (
                <ActivityIndicator size="small" color={Colors.palette.white} />
              ) : (
                <>
                  <Download size={18} color={Colors.palette.white} />
                  <Text style={styles.downloadBtnText}>
                    {downloadProgress > 0 ? `${Math.round(downloadProgress * 100)}%` : 'Download'}
                  </Text>
                </>
              )}
            </TouchableOpacity>

            <TouchableOpacity
              style={[styles.actionBtn, styles.exportBtn, !canExport && styles.actionBtnDisabled]}
              onPress={handleExport}
              activeOpacity={0.8}
              disabled={!canExport}
            >
              <Share2 size={18} color={canExport ? Colors.palette.white : '#555'} />
              <Text style={[styles.exportBtnText, !canExport && { color: '#555' }]}>Export</Text>
            </TouchableOpacity>
          </View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

// ── Header component ─────────────────────────────────────────────────────────

function Header({ title }: { title?: string }) {
  return (
    <View style={styles.header}>
      <TouchableOpacity onPress={() => router.back()} style={styles.backBtn} activeOpacity={0.7}>
        <ArrowLeft size={22} color={Colors.palette.white} />
      </TouchableOpacity>
      <Text style={styles.headerTitle} numberOfLines={1}>
        {title ?? 'Document'}
      </Text>
      <View style={styles.backBtn} />
    </View>
  );
}

// ── Styles ───────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.palette.inkBlack,
  },
  scroll: {
    flex: 1,
  },
  scrollContent: {
    flexGrow: 1,
  },
  centered: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 16,
  },

  // Header
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 14,
  },
  backBtn: {
    width: 40,
    height: 40,
    alignItems: 'center',
    justifyContent: 'center',
  },
  headerTitle: {
    flex: 1,
    fontSize: 17,
    fontWeight: '600',
    color: Colors.palette.white,
    textAlign: 'center',
  },

  // Image area
  imageArea: {
    height: IMAGE_AREA_HEIGHT,
    backgroundColor: '#F2F2F2',
    justifyContent: 'center',
    alignItems: 'center',
    overflow: 'hidden',
  },
  docImage: {
    width: '100%',
    height: '100%',
  },
  imagePlaceholder: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 12,
  },
  imagePlaceholderText: {
    fontSize: 14,
    color: '#aaa',
    textAlign: 'center',
  },

  // Info card
  infoCard: {
    flex: 1,
    backgroundColor: Colors.palette.inkBlack,
    paddingHorizontal: 24,
    paddingTop: 28,
    paddingBottom: 32,
    gap: 16,
  },
  docTitle: {
    fontSize: 24,
    fontWeight: '700',
    color: Colors.palette.white,
    lineHeight: 30,
  },

  // Badges
  badgeRow: {
    flexDirection: 'row',
    gap: 10,
    alignItems: 'center',
  },
  typeBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.12)',
  },
  typeBadgeText: {
    fontSize: 13,
    color: '#aaa',
    fontWeight: '500',
  },
  statusBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 20,
    borderWidth: 1,
  },
  statusDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
  },
  statusBadgeText: {
    fontSize: 13,
    fontWeight: '600',
  },

  // Meta rows
  metaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  metaText: {
    fontSize: 14,
    color: '#666',
  },
  metaLabel: {
    fontSize: 14,
    color: '#444',
    fontWeight: '500',
  },
  metaMono: {
    fontSize: 14,
    color: '#555',
    fontFamily: 'monospace',
  },

  // Action buttons
  actionRow: {
    flexDirection: 'row',
    gap: 12,
    marginTop: 8,
  },
  actionBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    height: 56,
    borderRadius: 28,
  },
  actionBtnDisabled: {
    opacity: 0.4,
  },
  downloadBtn: {
    backgroundColor: '#1C1C1E',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.12)',
  },
  downloadBtnText: {
    fontSize: 16,
    fontWeight: '600',
    color: Colors.palette.white,
  },
  exportBtn: {
    backgroundColor: '#2A2A2C',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.18)',
  },
  exportBtnText: {
    fontSize: 16,
    fontWeight: '600',
    color: Colors.palette.white,
  },

  // Error
  errorText: {
    fontSize: 16,
    color: '#555',
  },
  goBackBtn: {
    paddingHorizontal: 28,
    paddingVertical: 14,
    backgroundColor: Colors.palette.shadowGrey,
    borderRadius: 24,
  },
  goBackText: {
    fontSize: 15,
    fontWeight: '600',
    color: Colors.palette.white,
  },
});
