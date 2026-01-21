
import { randomBytes, createCipheriv, createDecipheriv } from 'crypto';

const ALGORITHM = 'aes-256-gcm';
const IV_LENGTH = 12; // 96 bits for GCM
const TAG_LENGTH = 16; // 128 bits

export interface EncryptedData {
    encrypted: Buffer;
    iv: Buffer;
    authTag: Buffer;
}

export function encrypt(data: Buffer, keyHex: string): Buffer {
    // Key must be 32 bytes (64 hex chars)
    const key = Buffer.from(keyHex, 'hex');
    if (key.length !== 32) throw new Error(`Invalid key length: ${key.length}. Expected 32 bytes.`);

    const iv = randomBytes(IV_LENGTH);
    const cipher = createCipheriv(ALGORITHM, key, iv);

    const encrypted = Buffer.concat([cipher.update(data), cipher.final()]);
    const authTag = cipher.getAuthTag();

    // Return format: [IV (12)][AuthTag (16)][EncryptedData (...)]
    return Buffer.concat([iv, authTag, encrypted]);
}

export function decrypt(packedData: Buffer, keyHex: string): Buffer {
    const key = Buffer.from(keyHex, 'hex');
    if (key.length !== 32) throw new Error(`Invalid key length: ${key.length}. Expected 32 bytes.`);

    if (packedData.length < IV_LENGTH + TAG_LENGTH) {
        throw new Error('Data too short to contain IV and AuthTag');
    }

    const iv = packedData.subarray(0, IV_LENGTH);
    const authTag = packedData.subarray(IV_LENGTH, IV_LENGTH + TAG_LENGTH);
    const encrypted = packedData.subarray(IV_LENGTH + TAG_LENGTH);

    const decipher = createDecipheriv(ALGORITHM, key, iv);
    decipher.setAuthTag(authTag);

    return Buffer.concat([decipher.update(encrypted), decipher.final()]);
}
