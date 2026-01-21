/**
 * Storage layer interface for the API gateway.
 * Handles idempotent upload storage using (userId, clientRequestId) mapping.
 */

import { blobStore } from '../engine/storage/blobStore';

interface StoreRequest {
  blobId: string;
  clientRequestId: string;
  payloadBytes: Buffer;
  userId: string;
}

interface StoreResult {
  blobId: string;
  isNewUpload: boolean;
}

/**
 * In-memory storage for idempotent upload tracking.
 * Production: Replace with persistent database.
 */
class IdempotentStorageLayer {
  // Map: userId:clientRequestId → blobId
  private idempotencyMap: Map<string, string> = new Map();

  /**
   * Generate idempotency key
   */
  private getIdempotencyKey(userId: string, clientRequestId: string): string {
    return `${userId}:${clientRequestId}`;
  }

  /**
   * Store blob with idempotent behavior.
   * If (userId, clientRequestId) already exists, return existing blobId.
   * Otherwise, store new blob and create mapping.
   */
  async store(request: StoreRequest): Promise<StoreResult> {
    const idempotencyKey = this.getIdempotencyKey(
      request.userId,
      request.clientRequestId
    );

    // Check if this request was already processed
    const existingBlobId = this.idempotencyMap.get(idempotencyKey);

    if (existingBlobId !== undefined) {
      // Idempotent retry: Return existing blobId
      return {
        blobId: existingBlobId,
        isNewUpload: false,
      };
    }

    // New upload: Store blob and create mapping
    await blobStore.put(request.payloadBytes, {
      size: request.payloadBytes.length,
      userId: request.userId,
      timestamp: Date.now()
    }, request.blobId);

    this.idempotencyMap.set(idempotencyKey, request.blobId);

    return {
      blobId: request.blobId,
      isNewUpload: true,
    };
  }

  /**
   * Retrieve blob by blobId
   */
  async get(blobId: string): Promise<Buffer | null> {
    return blobStore.get(blobId);
  }

  /**
   * Clear all storage (for testing)
   */
  clear(): void {
    this.idempotencyMap.clear();
    // blobStore clearing would be global, so we don't do it here for now
  }
}

export const storageLayer = new IdempotentStorageLayer();
