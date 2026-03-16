/**
 * Download Service
 * 
 * Handles file downloads with progress tracking, caching, and sharing.
 */

import * as FileSystem from 'expo-file-system/legacy';
import * as Sharing from 'expo-sharing';
import { Alert, Platform } from 'react-native';

export interface DownloadProgress {
  totalBytes: number;
  downloadedBytes: number;
  progress: number; // 0-1
}

export interface DownloadResult {
  success: boolean;
  localPath: string;
  size: number;
  error?: string;
}

// Cache directory for downloads
// Using app's document directory which is guaranteed to be writable
const DOWNLOAD_CACHE_DIR = `${FileSystem.documentDirectory}downloads/`;

/**
 * Ensure download directory exists
 */
async function ensureDownloadDir(): Promise<void> {
  try {
    const dirInfo = await FileSystem.getInfoAsync(DOWNLOAD_CACHE_DIR);
    if (!dirInfo.exists) {
      await FileSystem.makeDirectoryAsync(DOWNLOAD_CACHE_DIR, { intermediates: true });
    }
  } catch (error) {
    console.error('Error creating download directory:', error);
  }
}

/**
 * Generate local filename for download
 */
function getLocalFilename(jobId: string, extension: string = 'zip'): string {
  const shortId = jobId.substring(0, 8);
  const timestamp = Date.now();
  return `rythmiq_${shortId}_${timestamp}.${extension}`;
}

/**
 * Download file with progress tracking
 */
export async function downloadFile(
  url: string,
  filename: string,
  onProgress?: (progress: DownloadProgress) => void,
  extension?: string,
): Promise<DownloadResult> {
  try {
    await ensureDownloadDir();
    
    const localPath = `${DOWNLOAD_CACHE_DIR}${filename}`;
    
    // Check if file already exists
    const existingFile = await FileSystem.getInfoAsync(localPath);
    if (existingFile.exists && existingFile.size && existingFile.size > 0) {
      // File exists, return cached version
      return {
        success: true,
        localPath,
        size: existingFile.size,
      };
    }
    
    // Create download resumable with progress callback
    const downloadResumable = FileSystem.createDownloadResumable(
      url,
      localPath,
      {},
      (downloadProgress) => {
        if (onProgress) {
          onProgress({
            totalBytes: downloadProgress.totalBytesExpectedToWrite,
            downloadedBytes: downloadProgress.totalBytesWritten,
            progress: downloadProgress.totalBytesExpectedToWrite > 0
              ? downloadProgress.totalBytesWritten / downloadProgress.totalBytesExpectedToWrite
              : 0,
          });
        }
      }
    );
    
    const result = await downloadResumable.downloadAsync();
    
    if (!result || result.status !== 200) {
      return {
        success: false,
        localPath: '',
        size: 0,
        error: `Download failed with status ${result?.status || 'unknown'}`,
      };
    }
    
    // Get file size
    const fileInfo = await FileSystem.getInfoAsync(localPath);
    
    return {
      success: true,
      localPath,
      size: fileInfo.exists && 'size' in fileInfo ? fileInfo.size ?? 0 : 0,
    };
    
  } catch (error) {
    console.error('Download error:', error);
    return {
      success: false,
      localPath: '',
      size: 0,
      error: error instanceof Error ? error.message : 'Download failed',
    };
  }
}

/**
 * Download job output and return local path
 */
export async function downloadJobOutput(
  jobId: string,
  downloadUrl: string,
  onProgress?: (progress: DownloadProgress) => void,
  extension: string = 'zip',
): Promise<DownloadResult> {
  const filename = getLocalFilename(jobId, extension);
  return downloadFile(downloadUrl, filename, onProgress, extension);
}

/**
 * Map MIME type to iOS Universal Type Identifier (UTI).
 * Ensures the share sheet presents the file correctly and routes to appropriate apps.
 */
function getIOSUTI(mimeType?: string): string {
  switch (mimeType) {
    case 'application/pdf': return 'com.adobe.pdf';
    case 'image/jpeg':      return 'public.jpeg';
    case 'image/png':       return 'public.png';
    case 'application/zip': return 'public.zip-archive';
    default:                return 'public.data';
  }
}

/**
 * Map output_format string to MIME type and file extension.
 */
export function outputFormatToMime(outputFormat?: string): { mimeType: string; ext: string } {
  switch ((outputFormat || '').toLowerCase()) {
    case 'pdf':  return { mimeType: 'application/pdf', ext: 'pdf' };
    case 'png':  return { mimeType: 'image/png',       ext: 'png' };
    case 'jpeg':
    case 'jpg':
    default:     return { mimeType: 'image/jpeg',      ext: 'jpg' };
  }
}

/**
 * Share a downloaded file
 */
export async function shareFile(
  localPath: string,
  options?: {
    mimeType?: string;
    dialogTitle?: string;
  }
): Promise<boolean> {
  try {
    const canShare = await Sharing.isAvailableAsync();

    if (!canShare) {
      Alert.alert(
        'Sharing Not Available',
        'File sharing is not available on this device.',
        [{ text: 'OK' }]
      );
      return false;
    }

    const mimeType = options?.mimeType || 'application/zip';

    await Sharing.shareAsync(localPath, {
      mimeType,
      dialogTitle: options?.dialogTitle || 'Save Document',
      UTI: Platform.OS === 'ios' ? getIOSUTI(mimeType) : undefined,
    });

    return true;
  } catch (error) {
    console.error('Share error:', error);
    return false;
  }
}

/**
 * Clear download cache
 */
export async function clearDownloadCache(): Promise<void> {
  try {
    const dirInfo = await FileSystem.getInfoAsync(DOWNLOAD_CACHE_DIR);
    if (dirInfo.exists) {
      await FileSystem.deleteAsync(DOWNLOAD_CACHE_DIR, { idempotent: true });
    }
  } catch (error) {
    console.error('Failed to clear download cache:', error);
  }
}

/**
 * Get cache size
 */
export async function getDownloadCacheSize(): Promise<number> {
  try {
    const dirInfo = await FileSystem.getInfoAsync(DOWNLOAD_CACHE_DIR);
    if (!dirInfo.exists) return 0;
    
    const files = await FileSystem.readDirectoryAsync(DOWNLOAD_CACHE_DIR);
    let totalSize = 0;
    
    for (const file of files) {
      const fileInfo = await FileSystem.getInfoAsync(`${DOWNLOAD_CACHE_DIR}${file}`);
      if (fileInfo.exists && fileInfo.size) {
        totalSize += fileInfo.size;
      }
    }
    
    return totalSize;
  } catch (error) {
    console.error('Failed to get cache size:', error);
    return 0;
  }
}

/**
 * Format file size for display
 */
export function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 B';
  
  const units = ['B', 'KB', 'MB', 'GB'];
  const k = 1024;
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${units[i]}`;
}

export default {
  downloadFile,
  downloadJobOutput,
  shareFile,
  clearDownloadCache,
  getDownloadCacheSize,
  formatFileSize,
};
