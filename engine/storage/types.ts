
export interface BlobMetadata {
    size: number;
    userId: string;
    timestamp: number;
}

export interface IBlobStore {
    put(bytes: Buffer, metadata: BlobMetadata, blobId?: string): Promise<string>;
    get(blobId: string): Promise<Buffer | null>;
    getMetadata(blobId: string): Promise<BlobMetadata | null>;
    delete(blobId: string): Promise<boolean>;
    exists(blobId: string): Promise<boolean>;
}
