/**
 * Background Upload Service
 *
 * Runs uploads as plain Promises, completely independent of React component
 * lifecycle. Components can navigate away freely while uploads continue.
 */

import { Alert } from 'react-native';
import { documentsApi } from './api';
import type { QueryClient } from '@tanstack/react-query';

export type UploadStatus = {
  total: number;
  current: number;
  done: boolean;
  error?: string;
};

// Module-level state so any component can observe progress
let _status: UploadStatus = { total: 0, current: 0, done: true };
const _listeners = new Set<(s: UploadStatus) => void>();

function notify(patch: Partial<UploadStatus>) {
  _status = { ..._status, ...patch };
  _listeners.forEach(fn => fn(_status));
}

export function subscribeUploadStatus(fn: (s: UploadStatus) => void) {
  _listeners.add(fn);
  fn(_status); // emit current state immediately
  return () => _listeners.delete(fn);
}

export function getUploadStatus(): UploadStatus {
  return _status;
}

export function startBackgroundUpload(
  imageUris: string[],
  documentName: string,
  selectedCategory: string,
  selectedType: string,
  apiDocumentType: 'photo' | 'signature' | 'document',
  queryClient: QueryClient,
  outputFormat: string = 'jpeg',
) {
  notify({ total: imageUris.length, current: 0, done: false, error: undefined });

  (async () => {
    try {
      for (let i = 0; i < imageUris.length; i++) {
        const uri = imageUris[i];
        const name = documentName || `${selectedType}_${Date.now()}`;
        const filename = `${name}_${i + 1}.jpg`;

        const response = await fetch(uri);
        const blob = await response.blob();

        const { job_id, upload_url } = await documentsApi.createMasterJob(
          apiDocumentType,
          filename,
          'image/jpeg',
          blob.size,
          selectedCategory,
          selectedType,
        );

        await documentsApi.uploadToPresignedUrl(upload_url, uri, 'image/jpeg');
        await documentsApi.submitJob(job_id, outputFormat);

        notify({ current: i + 1 });

        // Refresh jobs list after each file so the card appears quickly
        queryClient.invalidateQueries({ queryKey: ['jobs'] });
      }

      notify({ done: true });
    } catch (err: any) {
      const msg = err?.message ?? 'Upload failed';
      notify({ done: true, error: msg });
      Alert.alert('Upload Failed', msg);
      queryClient.invalidateQueries({ queryKey: ['jobs'] });
    }
  })();
}
