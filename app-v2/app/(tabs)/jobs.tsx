/**
 * Jobs Screen
 * 
 * Lists all user jobs with status and allows downloading results.
 */

import React, { useCallback, useMemo } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  FlatList,
  ActivityIndicator,
  RefreshControl,
  Alert,
} from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useQuery } from '@tanstack/react-query';
import * as Sharing from 'expo-sharing';
import * as FileSystem from 'expo-file-system';
import { documentsApi, JobStatus } from '../../services/api';

type JobStatusType = 'pending' | 'processing' | 'completed' | 'failed';

interface StatusConfig {
  icon: keyof typeof Ionicons.glyphMap;
  color: string;
  label: string;
}

const STATUS_CONFIG: Record<JobStatusType, StatusConfig> = {
  pending: { icon: 'time-outline', color: '#FF9500', label: 'Pending' },
  processing: { icon: 'sync-outline', color: '#007AFF', label: 'Processing' },
  completed: { icon: 'checkmark-circle', color: '#34C759', label: 'Completed' },
  failed: { icon: 'close-circle', color: '#FF3B30', label: 'Failed' },
};

export default function JobsScreen() {
  const params = useLocalSearchParams<{ newJobIds?: string }>();
  
  // Fetch jobs
  const { 
    data, 
    isLoading, 
    refetch, 
    isRefetching 
  } = useQuery({
    queryKey: ['jobs'],
    queryFn: documentsApi.listJobs,
    refetchInterval: 10000, // Poll every 10 seconds for status updates
  });

  const jobs = useMemo(() => {
    return data?.jobs || [];
  }, [data]);

  // Highlight newly created jobs
  const newJobIds = useMemo(() => {
    if (params.newJobIds) {
      try {
        return JSON.parse(params.newJobIds) as string[];
      } catch {
        return [];
      }
    }
    return [];
  }, [params.newJobIds]);

  const handleDownload = useCallback(async (job: JobStatus) => {
    if (job.status !== 'completed') {
      Alert.alert('Not Ready', 'This job is not yet complete.');
      return;
    }

    try {
      // Get download URL
      const { download_url } = await documentsApi.getJobOutput(job.job_id);
      
      // Download the file
      const filename = `rythmiq_${job.job_id.substring(0, 8)}.zip`;
      // Use type assertion for FileSystem properties that may vary by version
      const fs = FileSystem as any;
      const cacheDir = fs.cacheDirectory || fs.documentDirectory || '';
      const downloadPath = `${cacheDir}${filename}`;
      
      const downloadResult = await FileSystem.downloadAsync(
        download_url,
        downloadPath
      );

      if (downloadResult.status !== 200) {
        throw new Error('Download failed');
      }

      // Share the file
      if (await Sharing.isAvailableAsync()) {
        await Sharing.shareAsync(downloadPath, {
          mimeType: 'application/zip',
          dialogTitle: 'Save Processed Documents',
        });
      } else {
        Alert.alert('Success', 'File downloaded to: ' + downloadPath);
      }
    } catch (error) {
      console.error('Download error:', error);
      Alert.alert('Download Failed', 'Could not download the file. Please try again.');
    }
  }, []);

  const handleJobPress = useCallback((job: JobStatus) => {
    router.push({
      pathname: '/(tabs)/job-detail',
      params: { jobId: job.job_id },
    });
  }, []);

  const renderJob = useCallback(({ item }: { item: JobStatus }) => {
    const statusConfig = STATUS_CONFIG[item.status] || STATUS_CONFIG.pending;
    const isNew = newJobIds.includes(item.job_id);
    const isProcessing = item.status === 'processing';

    return (
      <TouchableOpacity
        style={[styles.jobItem, isNew && styles.jobItemNew]}
        onPress={() => handleJobPress(item)}
      >
        <View style={styles.jobIcon}>
          {isProcessing ? (
            <ActivityIndicator size="small" color={statusConfig.color} />
          ) : (
            <Ionicons name={statusConfig.icon} size={24} color={statusConfig.color} />
          )}
        </View>
        
        <View style={styles.jobInfo}>
          <Text style={styles.jobId}>
            Job #{item.job_id.substring(0, 8)}
          </Text>
          <View style={styles.statusRow}>
            <Text style={[styles.statusText, { color: statusConfig.color }]}>
              {statusConfig.label}
            </Text>
            {item.quality_score !== undefined && item.status === 'completed' && (
              <Text style={styles.qualityScore}>
                Quality: {Math.round(item.quality_score * 100)}%
              </Text>
            )}
          </View>
          {item.error && (
            <Text style={styles.errorText} numberOfLines={2}>
              {item.error.message}
            </Text>
          )}
        </View>

        <Ionicons 
          name={item.status === 'completed' ? 'chevron-forward' : 'chevron-forward-outline'} 
          size={20} 
          color={item.status === 'completed' ? '#007AFF' : '#C7C7CC'} 
        />
      </TouchableOpacity>
    );
  }, [newJobIds, handleJobPress]);

  const ListEmptyComponent = useCallback(() => (
    <View style={styles.emptyContainer}>
      <Ionicons name="document-text-outline" size={64} color="#C7C7CC" />
      <Text style={styles.emptyTitle}>No Documents Yet</Text>
      <Text style={styles.emptyMessage}>
        Capture or upload documents to get started
      </Text>
      <TouchableOpacity
        style={styles.emptyButton}
        onPress={() => router.push('/(tabs)/capture')}
      >
        <Ionicons name="camera" size={20} color="white" />
        <Text style={styles.emptyButtonText}>Scan Document</Text>
      </TouchableOpacity>
    </View>
  ), []);

  if (isLoading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color="#007AFF" />
        <Text style={styles.loadingText}>Loading jobs...</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>My Documents</Text>
        <TouchableOpacity onPress={() => refetch()}>
          <Ionicons name="refresh" size={24} color="#007AFF" />
        </TouchableOpacity>
      </View>

      {/* Stats */}
      {jobs.length > 0 && (
        <View style={styles.statsContainer}>
          <View style={styles.statItem}>
            <Text style={styles.statValue}>
              {jobs.filter(j => j.status === 'completed').length}
            </Text>
            <Text style={styles.statLabel}>Completed</Text>
          </View>
          <View style={styles.statDivider} />
          <View style={styles.statItem}>
            <Text style={styles.statValue}>
              {jobs.filter(j => j.status === 'processing').length}
            </Text>
            <Text style={styles.statLabel}>Processing</Text>
          </View>
          <View style={styles.statDivider} />
          <View style={styles.statItem}>
            <Text style={styles.statValue}>
              {jobs.filter(j => j.status === 'pending').length}
            </Text>
            <Text style={styles.statLabel}>Pending</Text>
          </View>
        </View>
      )}

      {/* Jobs List */}
      <FlatList
        data={jobs}
        keyExtractor={(item) => item.job_id}
        renderItem={renderJob}
        ListEmptyComponent={ListEmptyComponent}
        contentContainerStyle={jobs.length === 0 ? styles.emptyList : styles.list}
        refreshControl={
          <RefreshControl
            refreshing={isRefetching}
            onRefresh={refetch}
            tintColor="#007AFF"
          />
        }
        showsVerticalScrollIndicator={false}
      />

      {/* FAB */}
      <TouchableOpacity
        style={styles.fab}
        onPress={() => router.push('/(tabs)/capture')}
      >
        <Ionicons name="add" size={28} color="white" />
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#F2F2F7',
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#F2F2F7',
  },
  loadingText: {
    marginTop: 12,
    fontSize: 16,
    color: '#8E8E93',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingTop: 60,
    paddingHorizontal: 16,
    paddingBottom: 16,
    backgroundColor: 'white',
  },
  headerTitle: {
    fontSize: 28,
    fontWeight: '700',
  },
  statsContainer: {
    flexDirection: 'row',
    backgroundColor: 'white',
    paddingVertical: 16,
    paddingHorizontal: 24,
    marginBottom: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#E5E5EA',
  },
  statItem: {
    flex: 1,
    alignItems: 'center',
  },
  statValue: {
    fontSize: 24,
    fontWeight: '700',
    color: '#000',
  },
  statLabel: {
    fontSize: 12,
    color: '#8E8E93',
    marginTop: 2,
  },
  statDivider: {
    width: 1,
    backgroundColor: '#E5E5EA',
    marginHorizontal: 16,
  },
  list: {
    padding: 16,
  },
  emptyList: {
    flex: 1,
    justifyContent: 'center',
    padding: 16,
  },
  jobItem: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'white',
    padding: 16,
    borderRadius: 12,
    marginBottom: 12,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
  },
  jobItemNew: {
    borderWidth: 2,
    borderColor: '#34C759',
  },
  jobIcon: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: '#F2F2F7',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
  },
  jobInfo: {
    flex: 1,
  },
  jobId: {
    fontSize: 16,
    fontWeight: '600',
    color: '#000',
  },
  statusRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 4,
    gap: 12,
  },
  statusText: {
    fontSize: 14,
    fontWeight: '500',
  },
  qualityScore: {
    fontSize: 12,
    color: '#8E8E93',
  },
  errorText: {
    fontSize: 12,
    color: '#FF3B30',
    marginTop: 4,
  },
  emptyContainer: {
    alignItems: 'center',
    padding: 32,
  },
  emptyTitle: {
    fontSize: 20,
    fontWeight: '600',
    color: '#000',
    marginTop: 16,
  },
  emptyMessage: {
    fontSize: 16,
    color: '#8E8E93',
    marginTop: 8,
    textAlign: 'center',
  },
  emptyButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#007AFF',
    paddingHorizontal: 24,
    paddingVertical: 14,
    borderRadius: 12,
    marginTop: 24,
    gap: 8,
  },
  emptyButtonText: {
    color: 'white',
    fontSize: 16,
    fontWeight: '600',
  },
  fab: {
    position: 'absolute',
    right: 20,
    bottom: 100,
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: '#007AFF',
    justifyContent: 'center',
    alignItems: 'center',
    shadowColor: '#007AFF',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 8,
  },
});
