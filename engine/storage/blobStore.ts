
import { randomUUID } from 'crypto';
import { IBlobStore, BlobMetadata } from './types';
import { S3BlobStore } from './s3BlobStore';

/**
 * In-memory storage implementation
 */
class InMemoryBlobStore implements IBlobStore {
  private store: Map<string, { bytes: Buffer; metadata: BlobMetadata }> = new Map();

  async put(bytes: Buffer, metadata: BlobMetadata, blobId?: string): Promise<string> {
    const id = blobId || randomUUID();
    this.store.set(id, {
      bytes: Buffer.from(bytes),
      metadata: { ...metadata },
    });
    return id;
  }

  async get(blobId: string): Promise<Buffer | null> {
    const record = this.store.get(blobId);
    return record ? Buffer.from(record.bytes) : null;
  }

  async getMetadata(blobId: string): Promise<BlobMetadata | null> {
    const record = this.store.get(blobId);
    return record ? { ...record.metadata } : null;
  }

  async delete(blobId: string): Promise<boolean> {
    return this.store.delete(blobId);
  }

  async exists(blobId: string): Promise<boolean> {
    return this.store.has(blobId);
  }
}

/**
 * Factory to create the appropriate blob store
 */
function createBlobStore(): IBlobStore {
  const type = process.env.ARTIFACT_STORE_TYPE || 'local';

  if (type === 's3') {
    const endpoint = process.env.SPACES_ENDPOINT;
    const bucket = process.env.SPACES_BUCKET;
    const accessKey = process.env.SPACES_ACCESS_KEY;
    const secretKey = process.env.SPACES_SECRET_KEY;

    if (!endpoint || !bucket || !accessKey || !secretKey) {
      console.warn('Missing S3/Spaces configuration, falling back to in-memory storage');
      return new InMemoryBlobStore();
    }

    return new S3BlobStore(endpoint, bucket, accessKey, secretKey);
  }

  return new InMemoryBlobStore();
}

function createSecureBlobStore(): IBlobStore {
  const baseStore = createBlobStore();
  const encryptionKey = process.env.BLOB_ENCRYPTION_KEY;

  if (encryptionKey) {
    // Validate key length just in case
    if (encryptionKey.length !== 64) {
      console.error('BLOB_ENCRYPTION_KEY must be 64 hex characters (32 bytes). Encryption disabled.');
      return baseStore;
    }
    console.log('Initializing EncryptedBlobStore');
    const { EncryptedBlobStore } = require('./encryptedBlobStore');
    return new EncryptedBlobStore(baseStore, encryptionKey);
  }

  return baseStore;
}

// Export singleton instance
export const blobStore = createSecureBlobStore();
export { IBlobStore, BlobMetadata };
