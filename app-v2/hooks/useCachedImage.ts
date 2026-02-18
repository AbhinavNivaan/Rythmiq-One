/**
 * useCachedImage Hook
 * 
 * Provides automatic image caching with loading states.
 */

import { useState, useEffect } from 'react';
import { cacheImage, getCachedImage } from '../services/imageCache';

interface UseCachedImageResult {
  uri: string | null;
  isLoading: boolean;
  error: Error | null;
}

/**
 * Hook for loading cached images
 */
export function useCachedImage(url: string | null | undefined): UseCachedImageResult {
  const [uri, setUri] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    if (!url) {
      setUri(null);
      setIsLoading(false);
      return;
    }

    let mounted = true;
    setIsLoading(true);
    setError(null);

    const loadImage = async () => {
      try {
        // First check cache
        const cached = await getCachedImage(url);
        
        if (cached && mounted) {
          setUri(cached);
          setIsLoading(false);
          return;
        }

        // Not cached, download and cache
        const cachedUri = await cacheImage(url);
        
        if (mounted) {
          setUri(cachedUri);
          setIsLoading(false);
        }
      } catch (err) {
        if (mounted) {
          setError(err instanceof Error ? err : new Error('Failed to load image'));
          // Fallback to original URL
          setUri(url);
          setIsLoading(false);
        }
      }
    };

    loadImage();

    return () => {
      mounted = false;
    };
  }, [url]);

  return { uri, isLoading, error };
}

export default useCachedImage;
