/**
 * useOptimisticUpdate Hook
 * 
 * Provides optimistic UI updates with automatic rollback on failure.
 */

import { useState, useCallback, useRef } from 'react';

interface OptimisticState<T> {
  data: T | null;
  isOptimistic: boolean;
  error: Error | null;
}

interface UseOptimisticUpdateOptions<T> {
  initialData?: T | null;
  onError?: (error: Error, previousData: T | null) => void;
}

interface UseOptimisticUpdateResult<T> {
  data: T | null;
  isOptimistic: boolean;
  error: Error | null;
  update: (
    optimisticData: T,
    asyncOperation: () => Promise<T>
  ) => Promise<T | null>;
  reset: () => void;
}

/**
 * Hook for optimistic UI updates
 * 
 * @example
 * const { data, isOptimistic, update } = useOptimisticUpdate<Job>({ initialData: job });
 * 
 * const handleStatusChange = async () => {
 *   await update(
 *     { ...job, status: 'completed' }, // Optimistic data
 *     () => api.updateJobStatus(job.id, 'completed') // Actual API call
 *   );
 * };
 */
export function useOptimisticUpdate<T>(
  options: UseOptimisticUpdateOptions<T> = {}
): UseOptimisticUpdateResult<T> {
  const { initialData = null, onError } = options;

  const [state, setState] = useState<OptimisticState<T>>({
    data: initialData,
    isOptimistic: false,
    error: null,
  });

  const previousDataRef = useRef<T | null>(null);

  const update = useCallback(
    async (optimisticData: T, asyncOperation: () => Promise<T>): Promise<T | null> => {
      // Store previous data for rollback
      previousDataRef.current = state.data;

      // Apply optimistic update immediately
      setState({
        data: optimisticData,
        isOptimistic: true,
        error: null,
      });

      try {
        // Perform the actual async operation
        const result = await asyncOperation();

        // Update with real data
        setState({
          data: result,
          isOptimistic: false,
          error: null,
        });

        return result;
      } catch (err) {
        const error = err instanceof Error ? err : new Error('Operation failed');

        // Rollback to previous data
        setState({
          data: previousDataRef.current,
          isOptimistic: false,
          error,
        });

        // Call error handler
        onError?.(error, previousDataRef.current);

        return null;
      }
    },
    [state.data, onError]
  );

  const reset = useCallback(() => {
    setState({
      data: initialData,
      isOptimistic: false,
      error: null,
    });
  }, [initialData]);

  return {
    data: state.data,
    isOptimistic: state.isOptimistic,
    error: state.error,
    update,
    reset,
  };
}

/**
 * Hook for optimistic list updates (add, remove, update items)
 */
export function useOptimisticList<T extends { id: string }>(
  initialItems: T[] = []
) {
  const [items, setItems] = useState<T[]>(initialItems);
  const [pendingIds, setPendingIds] = useState<Set<string>>(new Set());
  const previousItemsRef = useRef<T[]>([]);

  const addItem = useCallback(
    async (
      optimisticItem: T,
      asyncOperation: () => Promise<T>
    ): Promise<T | null> => {
      previousItemsRef.current = items;

      // Optimistically add item
      setItems((prev) => [optimisticItem, ...prev]);
      setPendingIds((prev) => new Set(prev).add(optimisticItem.id));

      try {
        const result = await asyncOperation();

        // Replace optimistic item with real one
        setItems((prev) =>
          prev.map((item) => (item.id === optimisticItem.id ? result : item))
        );
        setPendingIds((prev) => {
          const next = new Set(prev);
          next.delete(optimisticItem.id);
          return next;
        });

        return result;
      } catch (err) {
        // Rollback
        setItems(previousItemsRef.current);
        setPendingIds((prev) => {
          const next = new Set(prev);
          next.delete(optimisticItem.id);
          return next;
        });
        return null;
      }
    },
    [items]
  );

  const removeItem = useCallback(
    async (
      itemId: string,
      asyncOperation: () => Promise<void>
    ): Promise<boolean> => {
      previousItemsRef.current = items;

      // Optimistically remove item
      setItems((prev) => prev.filter((item) => item.id !== itemId));
      setPendingIds((prev) => new Set(prev).add(itemId));

      try {
        await asyncOperation();
        setPendingIds((prev) => {
          const next = new Set(prev);
          next.delete(itemId);
          return next;
        });
        return true;
      } catch (err) {
        // Rollback
        setItems(previousItemsRef.current);
        setPendingIds((prev) => {
          const next = new Set(prev);
          next.delete(itemId);
          return next;
        });
        return false;
      }
    },
    [items]
  );

  const updateItem = useCallback(
    async (
      itemId: string,
      optimisticUpdate: Partial<T>,
      asyncOperation: () => Promise<T>
    ): Promise<T | null> => {
      previousItemsRef.current = items;

      // Optimistically update item
      setItems((prev) =>
        prev.map((item) =>
          item.id === itemId ? { ...item, ...optimisticUpdate } : item
        )
      );
      setPendingIds((prev) => new Set(prev).add(itemId));

      try {
        const result = await asyncOperation();

        // Replace with real data
        setItems((prev) =>
          prev.map((item) => (item.id === itemId ? result : item))
        );
        setPendingIds((prev) => {
          const next = new Set(prev);
          next.delete(itemId);
          return next;
        });

        return result;
      } catch (err) {
        // Rollback
        setItems(previousItemsRef.current);
        setPendingIds((prev) => {
          const next = new Set(prev);
          next.delete(itemId);
          return next;
        });
        return null;
      }
    },
    [items]
  );

  const isPending = useCallback(
    (itemId: string): boolean => pendingIds.has(itemId),
    [pendingIds]
  );

  return {
    items,
    setItems,
    addItem,
    removeItem,
    updateItem,
    isPending,
    hasPending: pendingIds.size > 0,
  };
}

export default {
  useOptimisticUpdate,
  useOptimisticList,
};
