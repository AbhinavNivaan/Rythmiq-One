/**
 * Image Cache Service
 * 
 * Provides caching for document thumbnails and images.
 * Uses expo-file-system for persistent storage.
 */

import * as FileSystem from 'expo-file-system';

// Simple hash function for cache keys
function simpleHash(str: string): string {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash;
  }
  return Math.abs(hash).toString(16).padStart(16, '0');
}

// Cache configuration - use documentDirectory with type assertion
const CACHE_DIR = `${(FileSystem as any).documentDirectory || ''}image-cache/`;
const MAX_CACHE_SIZE_MB = 100; // Maximum cache size in MB
const MAX_CACHE_AGE_DAYS = 7; // Maximum age of cached files

interface CacheEntry {
  uri: string;
  timestamp: number;
  size: number;
}

interface CacheIndex {
  entries: Record<string, CacheEntry>;
  totalSize: number;
  lastCleanup: number;
}

let cacheIndex: CacheIndex | null = null;

/**
 * Initialize the image cache
 */
export async function initializeCache(): Promise<void> {
  try {
    // Ensure cache directory exists
    const dirInfo = await FileSystem.getInfoAsync(CACHE_DIR);
    if (!dirInfo.exists) {
      await FileSystem.makeDirectoryAsync(CACHE_DIR, { intermediates: true });
    }

    // Load or create cache index
    await loadCacheIndex();

    // Run cleanup if needed (every 24 hours)
    const dayInMs = 24 * 60 * 60 * 1000;
    if (!cacheIndex || Date.now() - cacheIndex.lastCleanup > dayInMs) {
      await cleanupCache();
    }
  } catch (error) {
    console.error('Failed to initialize image cache:', error);
  }
}

/**
 * Load cache index from disk
 */
async function loadCacheIndex(): Promise<void> {
  try {
    const indexPath = `${CACHE_DIR}index.json`;
    const indexInfo = await FileSystem.getInfoAsync(indexPath);
    
    if (indexInfo.exists) {
      const content = await FileSystem.readAsStringAsync(indexPath);
      cacheIndex = JSON.parse(content);
    } else {
      cacheIndex = {
        entries: {},
        totalSize: 0,
        lastCleanup: Date.now(),
      };
    }
  } catch (error) {
    console.error('Failed to load cache index:', error);
    cacheIndex = {
      entries: {},
      totalSize: 0,
      lastCleanup: Date.now(),
    };
  }
}

/**
 * Save cache index to disk
 */
async function saveCacheIndex(): Promise<void> {
  if (!cacheIndex) return;
  
  try {
    const indexPath = `${CACHE_DIR}index.json`;
    await FileSystem.writeAsStringAsync(indexPath, JSON.stringify(cacheIndex));
  } catch (error) {
    console.error('Failed to save cache index:', error);
  }
}

/**
 * Generate cache key from URL
 */
async function getCacheKey(url: string): Promise<string> {
  return simpleHash(url);
}

/**
 * Get cached image path or null if not cached
 */
export async function getCachedImage(url: string): Promise<string | null> {
  if (!cacheIndex) await initializeCache();
  
  try {
    const key = await getCacheKey(url);
    const entry = cacheIndex?.entries[key];
    
    if (!entry) return null;
    
    // Check if file still exists
    const fileInfo = await FileSystem.getInfoAsync(entry.uri);
    if (!fileInfo.exists) {
      // Remove stale entry
      delete cacheIndex!.entries[key];
      await saveCacheIndex();
      return null;
    }
    
    // Check if expired
    const maxAge = MAX_CACHE_AGE_DAYS * 24 * 60 * 60 * 1000;
    if (Date.now() - entry.timestamp > maxAge) {
      await removeCachedImage(url);
      return null;
    }
    
    return entry.uri;
  } catch (error) {
    console.error('Error getting cached image:', error);
    return null;
  }
}

/**
 * Cache an image from URL
 */
export async function cacheImage(url: string): Promise<string> {
  if (!cacheIndex) await initializeCache();
  
  try {
    // Check if already cached
    const existing = await getCachedImage(url);
    if (existing) return existing;
    
    // Generate cache path
    const key = await getCacheKey(url);
    const extension = url.split('.').pop()?.split('?')[0] || 'jpg';
    const localPath = `${CACHE_DIR}${key}.${extension}`;
    
    // Download image
    const downloadResult = await FileSystem.downloadAsync(url, localPath);
    
    if (downloadResult.status !== 200) {
      throw new Error(`Download failed with status ${downloadResult.status}`);
    }
    
    // Get file size
    const fileInfo = await FileSystem.getInfoAsync(localPath);
    const size = (fileInfo as any).size || 0;
    
    // Add to index
    cacheIndex!.entries[key] = {
      uri: localPath,
      timestamp: Date.now(),
      size,
    };
    cacheIndex!.totalSize += size;
    
    await saveCacheIndex();
    
    // Check if cleanup needed
    const maxSizeBytes = MAX_CACHE_SIZE_MB * 1024 * 1024;
    if (cacheIndex!.totalSize > maxSizeBytes) {
      await cleanupCache();
    }
    
    return localPath;
  } catch (error) {
    console.error('Error caching image:', error);
    // Return original URL as fallback
    return url;
  }
}

/**
 * Remove a cached image
 */
export async function removeCachedImage(url: string): Promise<void> {
  if (!cacheIndex) return;
  
  try {
    const key = await getCacheKey(url);
    const entry = cacheIndex.entries[key];
    
    if (entry) {
      await FileSystem.deleteAsync(entry.uri, { idempotent: true });
      cacheIndex.totalSize -= entry.size;
      delete cacheIndex.entries[key];
      await saveCacheIndex();
    }
  } catch (error) {
    console.error('Error removing cached image:', error);
  }
}

/**
 * Clean up old and excess cache entries
 */
export async function cleanupCache(): Promise<void> {
  if (!cacheIndex) return;
  
  try {
    const maxAge = MAX_CACHE_AGE_DAYS * 24 * 60 * 60 * 1000;
    const maxSizeBytes = MAX_CACHE_SIZE_MB * 1024 * 1024;
    const now = Date.now();
    
    // Get entries sorted by age (oldest first)
    const entries = Object.entries(cacheIndex.entries)
      .map(([key, entry]) => ({ key, ...entry }))
      .sort((a, b) => a.timestamp - b.timestamp);
    
    // Remove expired entries
    for (const entry of entries) {
      if (now - entry.timestamp > maxAge) {
        await FileSystem.deleteAsync(entry.uri, { idempotent: true });
        cacheIndex.totalSize -= entry.size;
        delete cacheIndex.entries[entry.key];
      }
    }
    
    // Remove oldest entries if still over size limit
    const remainingEntries = Object.entries(cacheIndex.entries)
      .map(([key, entry]) => ({ key, ...entry }))
      .sort((a, b) => a.timestamp - b.timestamp);
    
    while (cacheIndex.totalSize > maxSizeBytes && remainingEntries.length > 0) {
      const oldest = remainingEntries.shift()!;
      await FileSystem.deleteAsync(oldest.uri, { idempotent: true });
      cacheIndex.totalSize -= oldest.size;
      delete cacheIndex.entries[oldest.key];
    }
    
    cacheIndex.lastCleanup = now;
    await saveCacheIndex();
    
    console.log(`Cache cleanup complete. Size: ${(cacheIndex.totalSize / 1024 / 1024).toFixed(2)}MB`);
  } catch (error) {
    console.error('Error during cache cleanup:', error);
  }
}

/**
 * Clear entire cache
 */
export async function clearCache(): Promise<void> {
  try {
    await FileSystem.deleteAsync(CACHE_DIR, { idempotent: true });
    await FileSystem.makeDirectoryAsync(CACHE_DIR, { intermediates: true });
    
    cacheIndex = {
      entries: {},
      totalSize: 0,
      lastCleanup: Date.now(),
    };
    await saveCacheIndex();
    
    console.log('Image cache cleared');
  } catch (error) {
    console.error('Error clearing cache:', error);
  }
}

/**
 * Get cache statistics
 */
export async function getCacheStats(): Promise<{
  entryCount: number;
  totalSizeMB: number;
  oldestEntry: Date | null;
  newestEntry: Date | null;
}> {
  if (!cacheIndex) await initializeCache();
  
  const entries = Object.values(cacheIndex?.entries || {});
  const timestamps = entries.map(e => e.timestamp);
  
  return {
    entryCount: entries.length,
    totalSizeMB: (cacheIndex?.totalSize || 0) / 1024 / 1024,
    oldestEntry: timestamps.length > 0 ? new Date(Math.min(...timestamps)) : null,
    newestEntry: timestamps.length > 0 ? new Date(Math.max(...timestamps)) : null,
  };
}

export default {
  initializeCache,
  getCachedImage,
  cacheImage,
  removeCachedImage,
  cleanupCache,
  clearCache,
  getCacheStats,
};
