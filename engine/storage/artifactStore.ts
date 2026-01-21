/**
 * Artifact Storage
 *
 * Opaque storage layer for processing outputs.
 * - No content inspection
 * - No schema awareness
 * - Size limit enforcement only
 * - Binary-safe operations
 */

import { randomUUID } from 'crypto';

// Type aliases for opaque data handling
export type ArtifactData = Buffer | Uint8Array;
export type ArtifactId = string & { readonly __brand: 'ArtifactId' };

export interface ArtifactMetadata {
  contentLength: number;
  storedAt: number; // Unix timestamp
  expiresAt?: number;
  [key: string]: unknown; // Additional opaque metadata
}

export interface StoredArtifact {
  id: ArtifactId;
  data: ArtifactData;
  metadata: ArtifactMetadata;
}

export interface ArtifactStoreError extends Error {
  code: 'SIZE_LIMIT_EXCEEDED' | 'NOT_FOUND' | 'INVALID_ID' | 'STORAGE_ERROR';
}

// Configuration
const DEFAULT_MAX_ARTIFACT_SIZE = 1024 * 1024 * 100; // 100 MB
const DEFAULT_MAX_METADATA_SIZE = 1024 * 10; // 10 KB

export interface ArtifactStoreConfig {
  maxArtifactSize?: number;
  maxMetadataSize?: number;
}

/**
 * In-memory artifact storage
 *
 * Production implementations would use:
 * - S3/blob storage
 * - Cassandra/DynamoDB
 * - Distributed file system
 */
class ArtifactStore {
  private artifacts: Map<ArtifactId, StoredArtifact> = new Map();
  private maxArtifactSize: number;
  private maxMetadataSize: number;

  constructor(config: ArtifactStoreConfig = {}) {
    this.maxArtifactSize = config.maxArtifactSize ?? DEFAULT_MAX_ARTIFACT_SIZE;
    this.maxMetadataSize = config.maxMetadataSize ?? DEFAULT_MAX_METADATA_SIZE;
  }

  /**
   * Store an artifact
   *
   * @param data - Opaque binary data (no inspection)
   * @param metadata - Artifact metadata (size limits enforced)
   * @returns Artifact ID for retrieval
   * @throws ArtifactStoreError on validation failure
   */
  putArtifact(
    data: ArtifactData,
    metadata: Partial<ArtifactMetadata> = {}
  ): ArtifactId {
    // Validate size
    const dataSize = Buffer.byteLength(data);
    if (dataSize > this.maxArtifactSize) {
      const error = new Error(
        `Artifact exceeds size limit: ${dataSize} > ${this.maxArtifactSize}`
      ) as ArtifactStoreError;
      error.code = 'SIZE_LIMIT_EXCEEDED';
      throw error;
    }

    // Validate metadata size
    const metadataSize = Buffer.byteLength(JSON.stringify(metadata));
    if (metadataSize > this.maxMetadataSize) {
      const error = new Error(
        `Metadata exceeds size limit: ${metadataSize} > ${this.maxMetadataSize}`
      ) as ArtifactStoreError;
      error.code = 'SIZE_LIMIT_EXCEEDED';
      throw error;
    }

    // Generate ID
    const id = randomUUID() as ArtifactId;

    // Prepare metadata
    const storedMetadata: ArtifactMetadata = {
      contentLength: dataSize,
      storedAt: Date.now(),
      ...metadata,
    };

    // Store (opaque - no content inspection)
    const artifact: StoredArtifact = {
      id,
      data: Buffer.isBuffer(data) ? data : Buffer.from(data),
      metadata: storedMetadata,
    };

    this.artifacts.set(id, artifact);

    // Log only metadata, never log data or size-related details that could leak content info
    return id;
  }

  /**
   * Retrieve an artifact
   *
   * @param artifactId - ID returned from putArtifact
   * @returns Stored artifact (data is opaque)
   * @throws ArtifactStoreError if not found or invalid ID
   */
  getArtifact(artifactId: ArtifactId): StoredArtifact {
    if (!artifactId || typeof artifactId !== 'string') {
      const error = new Error('Invalid artifact ID') as ArtifactStoreError;
      error.code = 'INVALID_ID';
      throw error;
    }

    const artifact = this.artifacts.get(artifactId);
    if (!artifact) {
      const error = new Error('Artifact not found') as ArtifactStoreError;
      error.code = 'NOT_FOUND';
      throw error;
    }

    // Check expiration
    if (artifact.metadata.expiresAt && artifact.metadata.expiresAt < Date.now()) {
      this.artifacts.delete(artifactId);
      const error = new Error('Artifact has expired') as ArtifactStoreError;
      error.code = 'NOT_FOUND';
      throw error;
    }

    return artifact;
  }

  /**
   * Delete an artifact
   *
   * @param artifactId - ID to delete
   */
  deleteArtifact(artifactId: ArtifactId): boolean {
    return this.artifacts.delete(artifactId);
  }

  /**
   * Check if artifact exists without retrieving data
   *
   * @param artifactId - ID to check
   */
  hasArtifact(artifactId: ArtifactId): boolean {
    const artifact = this.artifacts.get(artifactId);
    if (!artifact) return false;

    // Check expiration
    if (artifact.metadata.expiresAt && artifact.metadata.expiresAt < Date.now()) {
      this.artifacts.delete(artifactId);
      return false;
    }

    return true;
  }

  /**
   * Get artifact metadata only (no data)
   *
   * @param artifactId - ID to query
   * @returns Metadata only
   */
  getMetadata(artifactId: ArtifactId): ArtifactMetadata {
    const artifact = this.getArtifact(artifactId);
    return artifact.metadata;
  }
}

// Export singleton instance
export const artifactStore = new ArtifactStore();

// Export class for dependency injection
export { ArtifactStore };
