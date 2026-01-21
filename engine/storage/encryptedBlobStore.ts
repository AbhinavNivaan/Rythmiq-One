
import { IBlobStore, BlobMetadata } from './types';
import { encrypt, decrypt } from './encryption';

export class EncryptedBlobStore implements IBlobStore {
    constructor(
        private readonly inner: IBlobStore,
        private readonly keyHex: string
    ) { }

    async put(bytes: Buffer, metadata: BlobMetadata, blobId?: string): Promise<string> {
        const encryptedBytes = encrypt(bytes, this.keyHex);

        // Calculate new size? 
        // Metadata usually tracks "logical" size or "physical" size?
        // For cost/storage tracking, physical size matters.
        // For the application logic (e.g. content-length check), logical size might matter.
        // But since BlobStore is opaque, we'll store the PHYSICAL encrypted size in the metadata passed to inner store,
        // but maybe we should preserve logical size in custom metadata?
        // For simplicity, we update the metadata to reflect the stored object.

        const newMetadata: BlobMetadata = {
            ...metadata,
            size: encryptedBytes.length, // Update size to match what is actually stored
        };

        return this.inner.put(encryptedBytes, newMetadata, blobId);
    }

    async get(blobId: string): Promise<Buffer | null> {
        const encryptedBytes = await this.inner.get(blobId);
        if (!encryptedBytes) return null;

        try {
            return decrypt(encryptedBytes, this.keyHex);
        } catch (error) {
            // If decryption fails, it might be an unencrypted file from before?
            // OR wrong key.
            // For safety, we fail.
            console.error(`Failed to decrypt blob ${blobId}:`, error);
            throw error;
        }
    }

    async getMetadata(blobId: string): Promise<BlobMetadata | null> {
        // Return underlying metadata. 
        // Note: The 'size' here will be the ENCRYPTED size.
        return this.inner.getMetadata(blobId);
    }

    async delete(blobId: string): Promise<boolean> {
        return this.inner.delete(blobId);
    }

    async exists(blobId: string): Promise<boolean> {
        return this.inner.exists(blobId);
    }
}
