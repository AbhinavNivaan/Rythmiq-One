
import { S3Client, GetObjectCommand, HeadObjectCommand, DeleteObjectCommand } from '@aws-sdk/client-s3';
import { Upload } from '@aws-sdk/lib-storage';
import { IBlobStore, BlobMetadata } from './types';
import { randomUUID } from 'crypto';
import { Readable } from 'stream';

export class S3BlobStore implements IBlobStore {
    private client: S3Client;
    private bucket: string;

    constructor(endpoint: string, bucket: string, accessKeyId: string, secretAccessKey: string) {
        this.bucket = bucket;

        // Sanitize endpoint: If user provided "https://bucket.region.digitaloceanspaces.com",
        // the AWS SDK will prepend bucket again -> "bucket.bucket.region...".
        // We strip the bucket from the hostname if it's there.
        let sanitizedEndpoint = endpoint;
        try {
            const url = new URL(endpoint);
            if (url.hostname.startsWith(`${bucket}.`)) {
                url.hostname = url.hostname.substring(bucket.length + 1); // remove "bucket."
                sanitizedEndpoint = url.toString();
                // Remove trailing slash if present from toString() but typically new URL handles it
                if (sanitizedEndpoint.endsWith('/') && !endpoint.endsWith('/')) {
                    sanitizedEndpoint = sanitizedEndpoint.slice(0, -1);
                }
            }
        } catch (e) {
            // If invalid URL, fallback to original and let SDK error out
        }

        // For DigitalOcean Spaces, endpoint should be region-level e.g. https://sgp1.digitaloceanspaces.com
        this.client = new S3Client({
            endpoint: sanitizedEndpoint,
            region: 'us-east-1', // Required by SDK but ignored by DO Spaces
            credentials: {
                accessKeyId,
                secretAccessKey,
            },
            forcePathStyle: false, // Use virtual hosted style (bucket.endpoint)
        });
    }

    async put(bytes: Buffer, metadata: BlobMetadata, blobId?: string): Promise<string> {
        const id = blobId || randomUUID();
        const key = this.getKey(id);

        const upload = new Upload({
            client: this.client,
            params: {
                Bucket: this.bucket,
                Key: key,
                Body: bytes,
                Metadata: {
                    userid: metadata.userId,
                    timestamp: String(metadata.timestamp),
                    size: String(metadata.size)
                },
                ContentType: 'application/octet-stream'
            },
        });

        await upload.done();
        return id;
    }

    async get(blobId: string): Promise<Buffer | null> {
        const key = this.getKey(blobId);
        try {
            const command = new GetObjectCommand({
                Bucket: this.bucket,
                Key: key,
            });
            const response = await this.client.send(command);
            if (!response.Body) return null;
            return this.streamToBuffer(response.Body as Readable);
        } catch (error: any) {
            if (error.name === 'NoSuchKey') return null;
            throw error;
        }
    }

    async getMetadata(blobId: string): Promise<BlobMetadata | null> {
        const key = this.getKey(blobId);
        try {
            const command = new HeadObjectCommand({
                Bucket: this.bucket,
                Key: key,
            });
            const response = await this.client.send(command);

            return {
                size: Number(response.Metadata?.size || response.ContentLength || 0),
                userId: response.Metadata?.userid || '',
                timestamp: Number(response.Metadata?.timestamp || 0)
            };
        } catch (error: any) {
            if (error.name === 'NotFound' || error.name === 'NoSuchKey') return null;
            throw error;
        }
    }

    async delete(blobId: string): Promise<boolean> {
        const key = this.getKey(blobId);
        try {
            const command = new DeleteObjectCommand({
                Bucket: this.bucket,
                Key: key,
            });
            await this.client.send(command);
            return true;
        } catch {
            return false;
        }
    }

    async exists(blobId: string): Promise<boolean> {
        return (await this.getMetadata(blobId)) !== null;
    }

    private getKey(blobId: string): string {
        return `blobs/${blobId}`;
    }

    private async streamToBuffer(stream: Readable): Promise<Buffer> {
        return new Promise((resolve, reject) => {
            const chunks: Buffer[] = [];
            stream.on('data', (chunk) => chunks.push(Buffer.from(chunk)));
            stream.on('error', reject);
            stream.on('end', () => resolve(Buffer.concat(chunks)));
        });
    }
}
