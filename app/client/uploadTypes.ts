/**
 * Type definitions for client upload module
 *
 * Exported types:
 * - UploadResult: Union type for success/error
 * - UploadSuccessResponse: Successful upload response
 * - GatewayErrorResponse: Error response from gateway
 * - UploadOptions: Configuration for upload
 * - SerializationError: Validation error during serialization
 * - UploadError: Network or protocol error
 */

/**
 * Configuration options for upload operation
 */
export interface UploadOptions {
  /**
   * Gateway base URL
   * @default "http://localhost:3001"
   */
  baseUrl?: string;

  /**
   * Maximum number of retries for transient errors
   * @default 3
   */
  maxRetries?: number;

  /**
   * Initial retry delay in milliseconds (exponential backoff applied)
   * @default 1000
   */
  retryDelayMs?: number;
}

/**
 * Successful upload response from gateway
 *
 * Indicates that the server accepted and persisted the encrypted payload.
 * The server does NOT verify encryption - it treats the payload as opaque bytes.
 */
export interface UploadSuccessResponse {
  /**
   * Server-assigned blob identifier (UUID v4)
   * Use this to reference the stored encrypted payload
   */
  blobId: string;

  /**
   * Echo of the client-provided request ID for idempotency
   */
  clientRequestId: string;

  /**
   * Number of bytes stored (should match request Content-Length)
   */
  uploadedBytes: number;
}

/**
 * Error response from gateway
 *
 * This could be a client error (4xx), server error (5xx), or network error.
 */
export interface GatewayErrorResponse {
  /**
   * HTTP status code (0 for network errors)
   */
  status: number;

  /**
   * Error type identifier (e.g., "Invalid Content-Type", "Server Error")
   */
  error?: string;

  /**
   * Human-readable error message
   */
  message?: string;

  /**
   * Additional error details from gateway response
   */
  details?: Record<string, unknown>;
}

/**
 * Upload result - discriminated union of success and failure
 *
 * Usage:
 *   const result = await uploadEncryptedPayload(payload, requestId);
 *   if (result.success) {
 *     // result.response is UploadSuccessResponse
 *     console.log("BlobId:", result.response.blobId);
 *   } else {
 *     // result.error is GatewayErrorResponse
 *     if (result.error.status >= 500) {
 *       // Safe to retry
 *     }
 *   }
 */
export type UploadResult =
  | {
      success: true;
      response: UploadSuccessResponse;
    }
  | {
      success: false;
      error: GatewayErrorResponse;
    };

/**
 * Serialization validation error
 *
 * Thrown when EncryptedPayload structure is invalid and cannot be serialized.
 * This should be caught before attempting upload.
 */
export class SerializationError extends Error {
  /**
   * The invalid field name
   */
  field: string;

  /**
   * The validation that failed
   */
  reason: string;

  constructor(field: string, reason: string) {
    super(`Serialization error in ${field}: ${reason}`);
    this.name = "SerializationError";
    this.field = field;
    this.reason = reason;
  }
}

/**
 * Upload protocol error
 *
 * Thrown for protocol-level errors (invalid headers, network errors, etc.)
 * that are not recoverable.
 */
export class UploadProtocolError extends Error {
  /**
   * HTTP status code (0 for network errors)
   */
  status: number;

  /**
   * Error type from gateway
   */
  errorType?: string;

  /**
   * Whether this error is retryable
   */
  retryable: boolean;

  constructor(
    status: number,
    message: string,
    errorType?: string,
    retryable: boolean = false
  ) {
    super(message);
    this.name = "UploadProtocolError";
    this.status = status;
    this.errorType = errorType;
    this.retryable = retryable;
  }

  /**
   * Check if this error should trigger a retry
   */
  isRetryable(): boolean {
    return this.retryable;
  }
}

/**
 * Gateway configuration (read-only)
 */
export interface GatewayConfiguration {
  /**
   * Base URL for gateway API
   */
  baseUrl: string;

  /**
   * Upload endpoint path
   */
  uploadEndpoint: string;

  /**
   * Maximum number of automatic retries
   */
  maxRetries: number;

  /**
   * Initial retry delay in milliseconds
   */
  retryDelayMs: number;

  /**
   * Maximum upload size in bytes
   */
  maxUploadSizeBytes: number;
}

/**
 * HTTP request configuration (for fetch)
 *
 * Internal type used for composing HTTP requests.
 */
export interface HttpRequestConfig {
  /**
   * Request method (POST for uploads)
   */
  method: string;

  /**
   * Request headers
   */
  headers: Record<string, string>;

  /**
   * Request body as Uint8Array
   */
  body: Uint8Array;
}

/**
 * HTTP response (parsed from fetch)
 *
 * Internal type for handling HTTP responses.
 */
export interface HttpResponse {
  /**
   * HTTP status code
   */
  status: number;

  /**
   * Response headers
   */
  headers: Record<string, string>;

  /**
   * Parsed response body (JSON or text)
   */
  data: unknown;
}

/**
 * Retry state for tracking retry attempts
 *
 * Internal type for retry logic.
 */
export interface RetryState {
  /**
   * Current attempt number (0-indexed)
   */
  attempt: number;

  /**
   * Maximum attempts allowed
   */
  maxAttempts: number;

  /**
   * Last error encountered
   */
  lastError?: Error;

  /**
   * Computed delay for this attempt (milliseconds)
   */
  delayMs: number;
}

/**
 * Type guard: Check if result is success
 *
 * Usage:
 *   const result = await uploadEncryptedPayload(payload, requestId);
 *   if (isUploadSuccess(result)) {
 *     // result.response is accessible
 *   }
 */
export function isUploadSuccess(result: UploadResult): result is {
  success: true;
  response: UploadSuccessResponse;
} {
  return result.success === true;
}

/**
 * Type guard: Check if result is error
 *
 * Usage:
 *   const result = await uploadEncryptedPayload(payload, requestId);
 *   if (isUploadError(result)) {
 *     // result.error is accessible
 *   }
 */
export function isUploadError(result: UploadResult): result is {
  success: false;
  error: GatewayErrorResponse;
} {
  return result.success === false;
}

/**
 * Helper: Check if error is retryable
 *
 * @param error - Error response from gateway
 * @returns true if error indicates transient failure and retry is safe
 */
export function isRetryableError(error: GatewayErrorResponse): boolean {
  // 5xx: Server errors (transient)
  if (error.status >= 500 && error.status < 600) {
    return true;
  }

  // 429: Too Many Requests (transient)
  if (error.status === 429) {
    return true;
  }

  // 0: Network error (transient)
  if (error.status === 0) {
    return true;
  }

  // 4xx: Client errors (not transient, except 408 and 409)
  if (error.status === 408) {
    // Request Timeout
    return true;
  }
  if (error.status === 409) {
    // Conflict (might be idempotency-related)
    return true;
  }

  return false;
}

/**
 * Helper: Get human-readable error description
 *
 * @param error - Error response from gateway
 * @returns Formatted error message
 */
export function formatGatewayError(error: GatewayErrorResponse): string {
  if (error.status === 0) {
    return `Network error: ${error.message || "Connection failed"}`;
  }

  if (error.status >= 500) {
    return `Server error (${error.status}): ${
      error.message || "Internal server error"
    }`;
  }

  if (error.status >= 400) {
    return `Client error (${error.status}): ${
      error.message || "Invalid request"
    }`;
  }

  return `HTTP error (${error.status}): ${error.message || "Unknown error"}`;
}
