/**
 * Client-side upload module for encrypted payloads.
 *
 * SECURITY NOTICE:
 * ================
 * This module serializes and transmits EncryptedPayload objects to the server.
 * The server CANNOT verify encryption, decrypt payloads, or validate contents.
 * The server treats payloads as opaque bytes only.
 *
 * DO NOT claim server-verified encryption.
 * Encryption verification happens only at the processing engine with UMK.
 * A hostile or misconfigured client can upload plaintext without detection.
 */

import { EncryptedPayload } from "./crypto/encryptDocument";

/**
 * Gateway configuration
 */
export const GATEWAY_CONFIG = {
  baseUrl: process.env.REACT_APP_GATEWAY_URL || "http://localhost:3001",
  uploadEndpoint: "/upload",
  maxRetries: 3,
  retryDelayMs: 1000,
  maxUploadSizeBytes: 100 * 1024 * 1024, // 100 MB
};

/**
 * Serialized format: version (1 byte) + wrappedDEK + nonce + ciphertext + tag
 *
 * Format:
 *   [0:1]              - version (uint8)
 *   [1:33]             - wrappedDEK.version (uint8) + algorithm (string, length-prefixed)
 *   [33:33+wrapped]    - wrappedKey (length-prefixed bytes)
 *   [...]              - nonce (12 bytes)
 *   [...]              - ciphertext (variable, length-prefixed)
 *   [...]              - tag (16 bytes)
 *
 * Length-prefixed encoding: 4-byte big-endian uint32 length + bytes
 */

/**
 * Serialize EncryptedPayload to raw bytes
 *
 * @param payload - EncryptedPayload to serialize
 * @returns Buffer containing serialized payload
 * @throws Error if payload is invalid
 */
export function serializeEncryptedPayload(
  payload: EncryptedPayload
): Uint8Array {
  // Validate payload structure
  if (!payload || typeof payload !== "object") {
    throw new Error("Payload must be a non-null object");
  }

  if (
    typeof payload.version !== "number" ||
    payload.version < 0 ||
    payload.version > 255
  ) {
    throw new Error(
      `Invalid payload version: ${payload.version}. Must be 0-255.`
    );
  }

  if (!payload.wrappedDEK || typeof payload.wrappedDEK !== "object") {
    throw new Error("wrappedDEK must be a non-null object");
  }

  if (
    typeof payload.wrappedDEK.version !== "number" ||
    typeof payload.wrappedDEK.algorithm !== "string" ||
    !payload.wrappedDEK.wrappedKey
  ) {
    throw new Error(
      "wrappedDEK must contain version (number), algorithm (string), and wrappedKey (Uint8Array)"
    );
  }

  if (!(payload.nonce instanceof Uint8Array)) {
    throw new Error("nonce must be a Uint8Array");
  }
  if (payload.nonce.length !== 12) {
    throw new Error(`nonce must be 12 bytes, got ${payload.nonce.length}`);
  }

  if (!(payload.ciphertext instanceof Uint8Array)) {
    throw new Error("ciphertext must be a Uint8Array");
  }
  if (payload.ciphertext.length === 0) {
    throw new Error("ciphertext must not be empty");
  }

  if (!(payload.tag instanceof Uint8Array)) {
    throw new Error("tag must be a Uint8Array");
  }
  if (payload.tag.length !== 16) {
    throw new Error(`tag must be 16 bytes, got ${payload.tag.length}`);
  }

  if (!(payload.wrappedDEK.wrappedKey instanceof Uint8Array)) {
    throw new Error("wrappedDEK.wrappedKey must be a Uint8Array");
  }

  // Build buffer
  const encoder = new TextEncoder();
  const algorithmBytes = encoder.encode(payload.wrappedDEK.algorithm);

  // Calculate total size
  const totalSize =
    1 + // payload version
    1 + // wrappedDEK.version
    4 +
    algorithmBytes.length + // algorithm (length-prefixed)
    4 +
    payload.wrappedDEK.wrappedKey.length + // wrappedKey (length-prefixed)
    payload.nonce.length + // nonce
    4 +
    payload.ciphertext.length + // ciphertext (length-prefixed)
    payload.tag.length; // tag

  const buffer = new Uint8Array(totalSize);
  let offset = 0;

  // Write payload version
  buffer[offset] = payload.version;
  offset += 1;

  // Write wrappedDEK.version
  buffer[offset] = payload.wrappedDEK.version;
  offset += 1;

  // Write algorithm (length-prefixed string)
  writeUint32BE(buffer, offset, algorithmBytes.length);
  offset += 4;
  buffer.set(algorithmBytes, offset);
  offset += algorithmBytes.length;

  // Write wrappedKey (length-prefixed bytes)
  writeUint32BE(buffer, offset, payload.wrappedDEK.wrappedKey.length);
  offset += 4;
  buffer.set(payload.wrappedDEK.wrappedKey, offset);
  offset += payload.wrappedDEK.wrappedKey.length;

  // Write nonce (fixed 12 bytes)
  buffer.set(payload.nonce, offset);
  offset += payload.nonce.length;

  // Write ciphertext (length-prefixed bytes)
  writeUint32BE(buffer, offset, payload.ciphertext.length);
  offset += 4;
  buffer.set(payload.ciphertext, offset);
  offset += payload.ciphertext.length;

  // Write tag (fixed 16 bytes)
  buffer.set(payload.tag, offset);
  offset += payload.tag.length;

  if (offset !== totalSize) {
    throw new Error(
      `Buffer serialization error: expected ${totalSize} bytes, wrote ${offset}`
    );
  }

  return buffer;
}

/**
 * Write 32-bit big-endian unsigned integer to buffer
 *
 * @param buffer - Target buffer
 * @param offset - Offset to write at
 * @param value - Value to write
 */
function writeUint32BE(
  buffer: Uint8Array,
  offset: number,
  value: number
): void {
  if (value < 0 || value > 0xffffffff) {
    throw new Error(`Value out of range: ${value}`);
  }
  buffer[offset] = (value >> 24) & 0xff;
  buffer[offset + 1] = (value >> 16) & 0xff;
  buffer[offset + 2] = (value >> 8) & 0xff;
  buffer[offset + 3] = value & 0xff;
}

/**
 * Gateway error response
 */
export interface GatewayErrorResponse {
  error?: string;
  message?: string;
  status: number;
  details?: Record<string, unknown>;
}

/**
 * Successful upload response
 */
export interface UploadSuccessResponse {
  blobId: string;
  clientRequestId: string;
  uploadedBytes: number;
}

/**
 * Upload result - either success or error
 */
export type UploadResult =
  | { success: true; response: UploadSuccessResponse }
  | { success: false; error: GatewayErrorResponse };

/**
 * Upload encrypted payload to gateway with retry logic
 *
 * IMPORTANT: Server does NOT verify encryption. A misconfigured or hostile
 * client can upload plaintext without detection.
 *
 * @param encryptedPayload - Encrypted payload to upload
 * @param clientRequestId - Unique request ID for idempotency
 * @param options - Override default configuration
 * @returns Upload result (success or error with details)
 *
 * @example
 * ```typescript
 * const plaintext = new TextEncoder().encode("secret");
 * const umk = generateUMK();
 * const encrypted = await encryptDocument(plaintext, umk);
 *
 * const clientRequestId = "550e8400-e29b-41d4-a716-446655440000"; // UUID v4
 * const result = await uploadEncryptedPayload(encrypted, clientRequestId);
 *
 * if (result.success) {
 *   console.log("Upload succeeded, blobId:", result.response.blobId);
 * } else {
 *   console.error("Upload failed:", result.error.message);
 * }
 * ```
 */
export async function uploadEncryptedPayload(
  encryptedPayload: EncryptedPayload,
  clientRequestId: string,
  options?: {
    baseUrl?: string;
    maxRetries?: number;
    retryDelayMs?: number;
  }
): Promise<UploadResult> {
  const config = {
    baseUrl: options?.baseUrl ?? GATEWAY_CONFIG.baseUrl,
    maxRetries: options?.maxRetries ?? GATEWAY_CONFIG.maxRetries,
    retryDelayMs: options?.retryDelayMs ?? GATEWAY_CONFIG.retryDelayMs,
  };

  // Validate inputs
  if (!clientRequestId || typeof clientRequestId !== "string") {
    return {
      success: false,
      error: {
        status: 400,
        error: "Invalid Input",
        message: "clientRequestId must be a non-empty string",
      },
    };
  }

  // Serialize payload
  let serialized: Uint8Array;
  try {
    serialized = serializeEncryptedPayload(encryptedPayload);
  } catch (serializationError) {
    return {
      success: false,
      error: {
        status: 400,
        error: "Serialization Error",
        message: `Failed to serialize payload: ${
          serializationError instanceof Error
            ? serializationError.message
            : String(serializationError)
        }`,
      },
    };
  }

  // Check size limit
  if (serialized.length > GATEWAY_CONFIG.maxUploadSizeBytes) {
    return {
      success: false,
      error: {
        status: 413,
        error: "Payload Too Large",
        message: `Payload size ${serialized.length} bytes exceeds maximum ${GATEWAY_CONFIG.maxUploadSizeBytes} bytes`,
      },
    };
  }

  // Retry logic
  let lastError: GatewayErrorResponse | Error | null = null;

  for (let attempt = 0; attempt <= config.maxRetries; attempt++) {
    try {
      const response = await performUpload(
        serialized,
        clientRequestId,
        config.baseUrl
      );

      // Success (2xx status)
      if (response.status >= 200 && response.status < 300) {
        return {
          success: true,
          response: response.data as UploadSuccessResponse,
        };
      }

      // Client error (4xx) - don't retry
      if (response.status >= 400 && response.status < 500) {
        return {
          success: false,
          error: {
            status: response.status,
            error: response.data?.error ?? "Request Error",
            message:
              response.data?.message ?? "Gateway rejected the request",
            details: response.data,
          },
        };
      }

      // Server error (5xx) or other - prepare for retry
      lastError = {
        status: response.status,
        error: response.data?.error ?? "Server Error",
        message: response.data?.message ?? `HTTP ${response.status}`,
        details: response.data,
      };

      // Don't retry on last attempt
      if (attempt < config.maxRetries) {
        const delay = config.retryDelayMs * Math.pow(2, attempt);
        await sleep(delay);
      }
    } catch (networkError) {
      lastError = networkError as Error;

      // Don't retry on last attempt
      if (attempt < config.maxRetries) {
        const delay = config.retryDelayMs * Math.pow(2, attempt);
        await sleep(delay);
      }
    }
  }

  // All retries exhausted
  if (lastError instanceof Error) {
    return {
      success: false,
      error: {
        status: 0,
        error: "Network Error",
        message: lastError.message,
      },
    };
  }

  return {
    success: false,
    error: lastError as GatewayErrorResponse,
  };
}

/**
 * Perform actual HTTP POST to gateway
 *
 * @param serialized - Serialized payload bytes
 * @param clientRequestId - Request ID for idempotency
 * @param baseUrl - Gateway base URL
 * @returns HTTP response with status and data
 */
async function performUpload(
  serialized: Uint8Array,
  clientRequestId: string,
  baseUrl: string
): Promise<{
  status: number;
  data: unknown;
}> {
  const url = `${baseUrl}${GATEWAY_CONFIG.uploadEndpoint}`;

  const response = await fetch(url, {
    method: "POST",
    headers: {
      "content-type": "application/octet-stream",
      "x-client-request-id": clientRequestId,
      "content-length": String(serialized.length),
    },
    body: serialized,
  });

  let data: unknown;
  const contentType = response.headers.get("content-type");

  try {
    if (contentType && contentType.includes("application/json")) {
      data = await response.json();
    } else if (response.status !== 204) {
      // 204 No Content has no body
      const text = await response.text();
      data = text.length > 0 ? text : undefined;
    }
  } catch {
    // Failed to parse response body
    data = undefined;
  }

  return {
    status: response.status,
    data,
  };
}

/**
 * Sleep for specified milliseconds
 *
 * @param ms - Milliseconds to sleep
 */
function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Generate a UUID v4 for clientRequestId
 *
 * @returns UUID v4 string
 */
export function generateClientRequestId(): string {
  return crypto.randomUUID ? crypto.randomUUID() : generateUUID();
}

/**
 * Fallback UUID v4 generator (for environments without crypto.randomUUID)
 *
 * @returns UUID v4 string
 */
function generateUUID(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));

  // Set version to 4 (random)
  bytes[6] = (bytes[6] & 0x0f) | 0x40;

  // Set variant to RFC 4122
  bytes[8] = (bytes[8] & 0x3f) | 0x80;

  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join(
    ""
  );

  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(
    12,
    16
  )}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
