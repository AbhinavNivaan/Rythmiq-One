/**
 * Canonical API error contract
 * Minimal, consistent error handling for production
 * CRITICAL: Never expose internal details, limits, or implementation specifics
 */

/**
 * ApiError interface - canonical schema
 * Only contains errorCode and statusCode
 * No messages, stack traces, or internal details
 */
export interface ApiError extends Error {
  errorCode: string;
  statusCode: number;
}

/**
 * Throw a standardized API error
 * Enforces canonical schema with no exposed details
 * 
 * @param errorCode - SCREAMING_SNAKE_CASE error identifier (never expose details)
 * @param statusCode - HTTP status code
 * @throws ApiError
 * 
 * Examples:
 * - throwApiError('INVALID_REQUEST', 400) - for validation errors
 * - throwApiError('UNAUTHORIZED', 401) - for auth failures
 * - throwApiError('FORBIDDEN', 403) - for permission errors
 * - throwApiError('JOB_NOT_AVAILABLE', 404) - for not found
 * - throwApiError('INTERNAL_ERROR', 500) - for unexpected errors
 */
export function throwApiError(errorCode: string, statusCode: number): never {
  const error = new Error() as ApiError;
  error.errorCode = errorCode;
  error.statusCode = statusCode;
  error.name = 'ApiError';
  throw error;
}

/**
 * Assert that an error is an ApiError
 * Type guard for narrowing error types
 */
export function isApiError(err: unknown): err is ApiError {
  return (
    err !== null &&
    typeof err === 'object' &&
    'errorCode' in err &&
    'statusCode' in err &&
    typeof (err as any).errorCode === 'string' &&
    typeof (err as any).statusCode === 'number'
  );
}
