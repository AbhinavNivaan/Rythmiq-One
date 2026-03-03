/**
 * Jobs Screen
 *
 * Lists all user jobs with status and allows viewing results.
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  FlatList,
  ActivityIndicator,
  Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router, useLocalSearchParams } from 'expo-router';
import {
  RefreshCw,
  CheckCircle,
  Clock,
  XCircle,
  FileText,
  Camera,
  Trash2,
} from 'lucide-react-native';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import * as Sharing from 'expo-sharing';
import * as FileSystem from 'expo-file-system';
import Colors from '../../constants/Colors';
import { documentsApi, JobStatus } from '../../services/api';
import { subscribeUploadStatus, UploadStatus } from '../../services/backgroundUpload';

type JobStatusType = 'pending' | 'processing' | 'completed' | 'failed';

interface StatusConfig {
  color: string;
  label: string;
}

const STATUS_CONFIG: Record<JobStatusType, StatusConfig> = {
  pending:    { color: Colors.palette.amber,  label: 'Pending'    },
  processing: { color: '#89C7FE',             label: 'Processing' },
  completed:  { color: Colors.palette.green,  label: 'Completed'  },
  failed:     { color: Colors.palette.red,    label: 'Failed'     },
};

export default function JobsScreen() {
  const params = useLocalSearchParams<{ newJobIds?: string }>();

  const queryClient = useQueryClient();
  const [deletingJobId, setDeletingJobId] = useState<string | null>(null);
  const [uploadStatus, setUploadStatus] = useState<UploadStatus>({ total: 0, current: 0, done: true });

  // Subscribe to background upload progress
  useEffect(() => {
    return subscribeUploadStatus(setUploadStatus);
  }, []);

  const isUploading = !uploadStatus.done;

  const { data, isLoading, refetch, isRefetching } = useQuery({
    queryKey: ['jobs'],
    queryFn: documentsApi.listJobs,
    // Poll more frequently while an upload is in flight
    refetchInterval: isUploading ? 3000 : 10000,
  });

  const jobs = useMemo(() => data?.jobs || [], [data]);

  const newJobIds = useMemo(() => {
    if (params.newJobIds) {
      try { return JSON.parse(params.newJobIds) as string[]; }
      catch { return []; }
    }
    return [];
  }, [params.newJobIds]);

  const deleteMutation = useMutation({
    mutationFn: (jobId: string) => documentsApi.deleteJob(jobId),
    onMutate: (jobId) => setDeletingJobId(jobId),
    onSettled: () => setDeletingJobId(null),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['jobs'] }),
    onError: () => Alert.alert('Delete Failed', 'Could not delete the document. Please try again.'),
  });

  const handleDelete = useCallback((job: JobStatus) => {
    Alert.alert(
      'Delete Document',
      'This will permanently remove this document from your vault.',
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Delete', style: 'destructive', onPress: () => deleteMutation.mutate(job.job_id) },
      ],
    );
  }, [deleteMutation]);

  const handleDownload = useCallback(async (job: JobStatus) => {
    if (job.status !== 'completed') {
      Alert.alert('Not Ready', 'This job is not yet complete.');
      return;
    }
    try {
      const { download_url } = await documentsApi.getJobOutput(job.job_id);
      const filename = `rythmiq_${job.job_id.substring(0, 8)}.zip`;
      const fs = FileSystem as any;
      const cacheDir = fs.cacheDirectory || fs.documentDirectory || '';
      const result = await FileSystem.downloadAsync(download_url, `${cacheDir}${filename}`);
      if (result.status !== 200) throw new Error('Download failed');
      if (await Sharing.isAvailableAsync()) {
        await Sharing.shareAsync(result.uri, { mimeType: 'application/zip', dialogTitle: 'Save Processed Documents' });
      } else {
        Alert.alert('Success', 'File downloaded to: ' + result.uri);
      }
    } catch (error) {
      Alert.alert('Download Failed', 'Could not download the file. Please try again.');
    }
  }, []);

  const handleJobPress = useCallback((job: JobStatus) => {
    router.push({ pathname: '/(tabs)/job-detail', params: { jobId: job.job_id } });
  }, []);

  const completed  = jobs.filter(j => j.status === 'completed').length;
  const processing = jobs.filter(j => j.status === 'processing').length;
  const pending    = jobs.filter(j => j.status === 'pending').length;

  const renderJob = useCallback(({ item }: { item: JobStatus }) => {
    const cfg = STATUS_CONFIG[item.status as JobStatusType] || STATUS_CONFIG.pending;
    const isNew = newJobIds.includes(item.job_id);
    const isActive = item.status === 'processing' || item.status === 'pending';

    const hasQuality = item.quality_score !== undefined && item.status === 'completed';
    const qualityColor = (item.quality_score ?? 0) >= 0.8 ? Colors.palette.green : Colors.palette.amber;

    return (
      <TouchableOpacity
        style={[styles.jobCard, { borderColor: isNew ? cfg.color + '40' : 'rgba(255,255,255,0.05)' }]}
        onPress={() => handleJobPress(item)}
        activeOpacity={0.75}
      >
        {/* Status icon */}
        <View style={[styles.jobIconWrap, { backgroundColor: cfg.color + '18' }]}>
          {isActive
            ? <ActivityIndicator size="small" color={cfg.color} />
            : item.status === 'completed'
              ? <CheckCircle size={22} color={cfg.color} />
              : item.status === 'failed'
                ? <XCircle size={22} color={cfg.color} />
                : <Clock size={22} color={cfg.color} />
          }
        </View>

        {/* Info */}
        <View style={styles.jobInfo}>
          <Text style={styles.jobId}>#{item.job_id.substring(0, 8)}</Text>
          <View style={styles.jobMeta}>
            <Text style={[styles.statusChip, { color: cfg.color }]}>{cfg.label}</Text>
            {hasQuality && (
              <View style={[styles.qualityBadge, { backgroundColor: qualityColor + '18' }]}>
                <Text style={[styles.qualityText, { color: qualityColor }]}>
                  {Math.round((item.quality_score ?? 0) * 100)}%
                </Text>
              </View>
            )}
          </View>
          {item.error && (
            <Text style={styles.errorSnippet} numberOfLines={1}>{item.error.message}</Text>
          )}
        </View>

        <TouchableOpacity
          style={styles.deleteButton}
          onPress={() => handleDelete(item)}
          hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
        >
          {deletingJobId === item.job_id
            ? <ActivityIndicator size="small" color="#FF3B30" />
            : <Trash2 size={16} color="#FF3B30" />}
        </TouchableOpacity>
      </TouchableOpacity>
    );
  }, [newJobIds, handleJobPress, deletingJobId, handleDelete]);

  if (isLoading) {
    return (
      <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
        <View style={styles.centered}>
          <ActivityIndicator size="large" color="#89C7FE" />
          <Text style={styles.hint}>Loading documents…</Text>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
      {/* Header */}
      <View style={styles.header}>
        <View style={styles.headerTop}>
          <Text style={styles.titleSub}>
            {jobs.length === 0 ? 'Nothing here yet' : `${jobs.length} job${jobs.length !== 1 ? 's' : ''}`}
          </Text>
          <TouchableOpacity
            onPress={() => refetch()}
            style={styles.iconButton}
            activeOpacity={0.7}
          >
            {isRefetching
              ? <ActivityIndicator size="small" color="#555" />
              : <RefreshCw size={20} color="#555" />}
          </TouchableOpacity>
        </View>
        <Text style={styles.titleMain}>Processing Jobs</Text>
      </View>

      {/* Upload-in-progress banner */}
      {isUploading && (
        <View style={styles.uploadBanner}>
          <ActivityIndicator size="small" color="#89C7FE" style={{ marginRight: 10 }} />
          <View style={{ flex: 1 }}>
            <Text style={styles.uploadBannerText}>
              Uploading {uploadStatus.current} of {uploadStatus.total} document{uploadStatus.total !== 1 ? 's' : ''}…
            </Text>
            <View style={styles.uploadBannerTrack}>
              <View
                style={[
                  styles.uploadBannerFill,
                  { width: uploadStatus.total > 0 ? `${(uploadStatus.current / uploadStatus.total) * 100}%` : '0%' },
                ]}
              />
            </View>
          </View>
        </View>
      )}

      <FlatList
        data={jobs}
        keyExtractor={(item) => item.job_id}
        renderItem={renderJob}
        onRefresh={refetch}
        refreshing={isRefetching}
        showsVerticalScrollIndicator={false}
        contentContainerStyle={jobs.length === 0 ? styles.emptyContent : styles.listContent}
        ListHeaderComponent={jobs.length > 0 ? (
          <>
            {/* Stats strip */}
            <View style={styles.statsCard}>
              <View style={styles.statCol}>
                <Text style={[styles.statNum, { color: Colors.palette.green }]}>{completed}</Text>
                <Text style={styles.statLbl}>Done</Text>
              </View>
              <View style={styles.divider} />
              <View style={styles.statCol}>
                <Text style={[styles.statNum, { color: '#89C7FE' }]}>{processing}</Text>
                <Text style={styles.statLbl}>Active</Text>
              </View>
              <View style={styles.divider} />
              <View style={styles.statCol}>
                <Text style={[styles.statNum, { color: Colors.palette.amber }]}>{pending}</Text>
                <Text style={styles.statLbl}>Queued</Text>
              </View>
            </View>

            <Text style={styles.sectionLabel}>Recent</Text>
          </>
        ) : null}
        ListEmptyComponent={(
          <View style={styles.emptyBox}>
            <View style={styles.emptyIconWrap}>
              <FileText size={36} color="#333" />
            </View>
            <Text style={styles.emptyTitle}>No documents yet</Text>
            <Text style={styles.emptyHint}>Capture or upload documents to get started.</Text>
            <TouchableOpacity
              style={styles.emptyButton}
              onPress={() => router.push('/(tabs)/capture')}
              activeOpacity={0.85}
            >
              <Camera size={18} color={Colors.palette.inkBlack} />
              <Text style={styles.emptyButtonText}>Scan Document</Text>
            </TouchableOpacity>
          </View>
        )}
      />
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
    paddingHorizontal: 24,
    paddingTop: 8,
    paddingBottom: 28,
  },
  headerTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 2,
  },
  iconButton: {
    width: 40,
    height: 40,
    alignItems: 'center',
    justifyContent: 'center',
  },
  titleSub: {
    fontSize: 16,
    fontWeight: '500',
    color: '#666',
  },
  titleMain: {
    fontSize: 32,
    fontWeight: '700',
    color: Colors.palette.white,
    lineHeight: 38,
  },

  // ── List / empty content ───────────────────────────────
  listContent: {
    paddingHorizontal: 24,
    paddingBottom: 40,
  },
  emptyContent: {
    flexGrow: 1,
    paddingHorizontal: 24,
  },

  // ── Stats card ─────────────────────────────────────────
  statsCard: {
    flexDirection: 'row',
    backgroundColor: Colors.palette.shadowGrey,
    borderRadius: 22,
    marginBottom: 12,
    paddingVertical: 18,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.05)',
  },
  statCol: {
    flex: 1,
    alignItems: 'center',
  },
  statNum: {
    fontSize: 26,
    fontWeight: '700',
  },
  statLbl: {
    fontSize: 11,
    color: '#555',
    marginTop: 3,
    letterSpacing: 0.4,
  },
  divider: {
    width: 1,
    backgroundColor: 'rgba(255,255,255,0.06)',
    marginVertical: 4,
  },

  // ── Section label ──────────────────────────────────────
  sectionLabel: {
    fontSize: 11,
    fontWeight: '600',
    color: '#555',
    textTransform: 'uppercase',
    letterSpacing: 0.8,
    marginBottom: 10,
  },

  // ── Job card ───────────────────────────────────────────
  jobCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.palette.shadowGrey,
    borderRadius: 20,
    padding: 16,
    marginBottom: 10,
    borderWidth: 1,
    gap: 14,
  },
  jobIconWrap: {
    width: 46,
    height: 46,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
  },
  jobInfo: {
    flex: 1,
  },
  jobId: {
    fontSize: 15,
    fontWeight: '600',
    color: Colors.palette.white,
    marginBottom: 5,
    fontFamily: 'monospace',
  },
  jobMeta: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  statusChip: {
    fontSize: 13,
    fontWeight: '500',
  },
  qualityBadge: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 8,
  },
  qualityText: {
    fontSize: 12,
    fontWeight: '600',
  },
  errorSnippet: {
    fontSize: 12,
    color: Colors.palette.red,
    marginTop: 4,
  },
  deleteButton: {
    width: 36,
    height: 36,
    alignItems: 'center',
    justifyContent: 'center',
  },

  // ── Empty state ────────────────────────────────────────
  emptyBox: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingBottom: 80,
  },
  emptyIconWrap: {
    width: 88,
    height: 88,
    borderRadius: 28,
    backgroundColor: Colors.palette.shadowGrey,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 20,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.05)',
  },
  emptyTitle: {
    fontSize: 20,
    fontWeight: '700',
    color: Colors.palette.white,
    marginBottom: 8,
  },
  emptyHint: {
    fontSize: 14,
    color: '#555',
    textAlign: 'center',
    lineHeight: 20,
    marginBottom: 28,
  },
  emptyButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: Colors.palette.green,
    paddingHorizontal: 28,
    height: 52,
    borderRadius: 26,
  },
  emptyButtonText: {
    fontSize: 15,
    fontWeight: '600',
    color: Colors.palette.inkBlack,
  },

  // ── Upload banner ──────────────────────────────────────
  uploadBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1A2595',
    marginHorizontal: 24,
    marginBottom: 12,
    borderRadius: 14,
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  uploadBannerText: {
    fontSize: 13,
    fontWeight: '500',
    color: '#89C7FE',
    marginBottom: 6,
  },
  uploadBannerTrack: {
    height: 4,
    backgroundColor: 'rgba(255,255,255,0.1)',
    borderRadius: 2,
    overflow: 'hidden',
  },
  uploadBannerFill: {
    height: '100%',
    backgroundColor: '#89C7FE',
    borderRadius: 2,
  },

  // ── Loading ────────────────────────────────────────────
  centered: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    gap: 14,
  },
  hint: {
    fontSize: 14,
    color: '#555',
  },
});
