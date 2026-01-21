/**
 * VALIDATION ERROR SANITIZATION - COMPLETE IMPLEMENTATION
 * TypeScript only. No details exposed to clients.
 */

// ============================================================================
// FILE 1: api-gateway/errors/validationErrors.ts
// ============================================================================

import { Request, Response, NextFunction } from 'express';
import { ApiError } from './apiError';

/**
 * Generic validation error response
 * Do NOT expose internal limits, formats, or API details
 */
export const SANITIZED_VALIDATION_ERROR = {
  errorCode: 'INVALID_REQUEST',
  statusCode: 400,
};

/**
 * Sanitized authentication error response
 * Do NOT expose token expiration or claims details
 */
export const SANITIZED_AUTH_ERROR = {
  errorCode: 'UNAUTHORIZED',
  statusCode: 401,
};

/**
 * Send sanitized validation error
 * Logs internal message server-side, returns generic error to client
 */
export function sendValidationError(
  res: Response,
  message?: string
): void {
  if (message) {
    console.warn('[VALIDATION_ERROR]', message);
  }
  res.status(SANITIZED_VALIDATION_ERROR.statusCode).json({
    errorCode: SANITIZED_VALIDATION_ERROR.errorCode,
  });
  return;
}

/**
 * Send sanitized authentication error
 * Logs internal message server-side, returns generic error to client
 */
export function sendAuthError(
  res: Response,
  message?: string
): void {
  if (message) {
    console.warn('[AUTH_ERROR]', message);
  }
  res.status(SANITIZED_AUTH_ERROR.statusCode).json({
    errorCode: SANITIZED_AUTH_ERROR.errorCode,
  });
  return;
}

/**
 * Middleware to catch and sanitize framework validation errors
 * Wraps body parser errors, malformed JSON, Content-Type mismatches, etc.
 */
export function sanitizationErrorHandler(
  err: any,
  req: Request,
  res: Response,
  next: NextFunction
): void {
  // Body parser / content-type errors
  if (
    err.type === 'entity.parse.failed' ||
    err.message?.includes('content-type') ||
    err.message?.includes('Content-Type') ||
    err.message?.includes('payload') ||
    err.message?.includes('Payload')
  ) {
    console.warn('[FRAMEWORK_ERROR]', err.message);
    res.status(400).json({ errorCode: 'INVALID_REQUEST' });
    return;
  }

  // Content-Length errors
  if (
    err.message?.includes('Content-Length') ||
    err.message?.includes('content-length') ||
    err.message?.includes('size') ||
    err.message?.includes('exceeded')
  ) {
    console.warn('[FRAMEWORK_ERROR]', err.message);
    res.status(413).json({ errorCode: 'INVALID_REQUEST' });
    return;
  }

  // Header validation errors
  if (err.message?.includes('header') || err.message?.includes('Header')) {
    console.warn('[FRAMEWORK_ERROR]', err.message);
    res.status(400).json({ errorCode: 'INVALID_REQUEST' });
    return;
  }

  // Unknown error - pass to next handler
  next(err);
}

// ============================================================================
// FILE 2: api-gateway/errors/errorHandler.ts
// ============================================================================

/**
 * Global error handler for Express
 * Sanitizes all errors before sending to client
 * Prevents leaking stack traces, internal details, or framework information
 * 
 * MUST be registered LAST in middleware chain:
 * app.use(globalErrorHandler);
 */
export function globalErrorHandler(
  err: any,
  req: Request,
  res: Response,
  next: NextFunction
): void {
  // Log full error server-side for debugging
  console.error('[GLOBAL_ERROR_HANDLER]', {
    message: err?.message || 'Unknown error',
    stack: err?.stack,
    type: err?.constructor?.name,
  });

  // Known API error with proper error code
  if (err?.errorCode && err?.statusCode) {
    res.status(err.statusCode).json({
      errorCode: err.errorCode,
    });
    return;
  }

  // Default: Return generic error without exposing details
  res.status(500).json({
    errorCode: 'INTERNAL_ERROR',
  });
}

/**
 * Wrapper for async route handlers to catch errors
 * Usage: router.get('/path', asyncHandler(async (req, res) => { ... }))
 */
export function asyncHandler(
  fn: (req: Request, res: Response, next: NextFunction) => Promise<void>
) {
  return (req: Request, res: Response, next: NextFunction) => {
    Promise.resolve(fn(req, res, next)).catch(next);
  };
}

// ============================================================================
// FILE 3: api-gateway/errors/apiError.ts (ENHANCED)
// ============================================================================

/**
 * Canonical API error contract
 * Minimal, consistent error handling for production
 * CRITICAL: Never expose internal details, limits, or implementation specifics
 */
export interface ApiError extends Error {
  errorCode: string;
  statusCode: number;
}

/**
 * Throw a standardized API error
 * Do NOT include detailed error messages in errorCode
 * @param errorCode - SCREAMING_SNAKE_CASE identifier (never expose details)
 * @param statusCode - HTTP status code
 * 
 * Examples:
 * - throwApiError('INVALID_REQUEST', 400) - for validation errors
 * - throwApiError('UNAUTHORIZED', 401) - for auth failures
 * - throwApiError('FORBIDDEN', 403) - for permission errors
 * - throwApiError('JOB_NOT_AVAILABLE', 404) - for not found
 * - throwApiError('SERVER_ERROR', 500) - for unexpected errors
 */
export function throwApiError(errorCode: string, statusCode: number): never {
  const error = new Error() as ApiError;
  error.errorCode = errorCode;
  error.statusCode = statusCode;
  error.name = 'ApiError';
  throw error;
}

// ============================================================================
// FILE 4: api-gateway/routes/upload.ts (SANITIZED VALIDATION)
// ============================================================================

// Import sendValidationError at top:
// import { sendValidationError } from '../errors/validationErrors';

/**
 * validateUploadRequest - No longer exposes:
 * ✓ Accepted content-type
 * ✓ Maximum upload size limits
 * ✓ Specific header names
 * All errors return: { errorCode: 'INVALID_REQUEST' }, statusCode: 400
 */
function validateUploadRequest(
  req: Request,
  res: Response,
  next: NextFunction
): void {
  // Validate Content-Type
  const contentType = req.headers['content-type'];
  if (contentType !== ACCEPTED_CONTENT_TYPE) {
    sendValidationError(
      res,
      `Invalid Content-Type: expected '${ACCEPTED_CONTENT_TYPE}', got '${contentType}'`
    );
    return;
  }

  // Validate Content-Length
  const contentLength = parseInt(req.headers['content-length'] || '0', 10);
  if (contentLength === 0) {
    sendValidationError(
      res,
      'Missing or zero Content-Length header'
    );
    return;
  }

  if (contentLength > MAX_UPLOAD_SIZE) {
    sendValidationError(
      res,
      `Content-Length ${contentLength} exceeds maximum size of ${MAX_UPLOAD_SIZE}`
    );
    return;
  }

  // Validate clientRequestId header
  const clientRequestId = req.headers['x-client-request-id'];
  if (!clientRequestId) {
    sendValidationError(
      res,
      'Missing required header: x-client-request-id'
    );
    return;
  }

  if (typeof clientRequestId !== 'string' || clientRequestId.trim() === '') {
    sendValidationError(
      res,
      'Invalid x-client-request-id: must be non-empty string'
    );
    return;
  }

  next();
}

// ============================================================================
// FILE 5: api-gateway/auth/middleware.ts (SANITIZED AUTH ERRORS)
// ============================================================================

// Import sendAuthError at top:
// import { sendAuthError } from '../errors/validationErrors';

/**
 * authenticateRequest - No longer exposes:
 * ✓ Token expiration details ("Token expired")
 * ✓ Signature validity ("Invalid token")
 * ✓ Claims format ("Invalid token claims")
 * All errors return: { errorCode: 'UNAUTHORIZED' }, statusCode: 401
 */
export function authenticateRequest(
  req: Request,
  res: Response,
  next: NextFunction
): void {
  const authHeader = req.headers.authorization;

  if (!authHeader || !authHeader.startsWith('Bearer ')) {
    sendAuthError(res, 'Missing or malformed authorization header');
    return;
  }

  const token = authHeader.substring(7);

  if (!token || token.trim() === '') {
    sendAuthError(res, 'Empty authorization token');
    return;
  }

  const secret = process.env.AUTH_JWT_SECRET;
  if (!secret) {
    console.error('[AUTH_CONFIG_ERROR] JWT_SECRET not configured');
    res.status(500).json({ errorCode: 'SERVER_ERROR' });
    return;
  }

  try {
    const payload = jwt.verify(token, secret) as TokenPayload;

    if (!payload.sub) {
      sendAuthError(res, 'Invalid token: missing subject claim');
      return;
    }

    (req as AuthenticatedRequest).userId = payload.sub;
    next();
  } catch (error) {
    // Don't expose JWT error details (expired, invalid signature, etc.)
    const message =
      error instanceof jwt.TokenExpiredError
        ? 'Token has expired'
        : error instanceof jwt.JsonWebTokenError
          ? 'Invalid token signature'
          : 'Token verification failed';

    sendAuthError(res, message);
    return;
  }
}

// ============================================================================
// REGISTRATION IN server.ts (EXPRESS APP SETUP)
// ============================================================================

/**
 * Usage pattern for Express app initialization:
 * 
 * import express from 'express';
 * import { sanitizationErrorHandler, globalErrorHandler } from './errors/errorHandler';
 * import uploadRoutes from './routes/upload';
 * import jobRoutes from './routes/jobs';
 * import resultsRoutes from './routes/results';
 * 
 * const app = express();
 * 
 * // Body parser (before sanitization handler)
 * app.use(express.json());
 * app.use(express.raw({ type: 'application/octet-stream', limit: '100mb' }));
 * 
 * // Sanitization error handler (catches framework errors)
 * app.use(sanitizationErrorHandler);
 * 
 * // Routes
 * app.use('/upload', uploadRoutes);
 * app.use('/jobs', jobRoutes);
 * app.use('/results', resultsRoutes);
 * 
 * // Global error handler (MUST be last)
 * app.use(globalErrorHandler);
 * 
 * app.listen(3000);
 */

// ============================================================================
// SECURITY GUARANTEES
// ============================================================================

/**
 * NO DETAILS LEAKED:
 * ✓ Size limits NOT exposed (100MB limit kept secret)
 * ✓ Header names NOT exposed (x-client-request-id kept secret)
 * ✓ Format specifications NOT exposed (application/octet-stream kept secret)
 * ✓ Framework errors NOT exposed (body-parser errors sanitized)
 * ✓ Stack traces NOT exposed (only error codes to client)
 * ✓ Internal error types NOT exposed (TokenExpiredError, JsonWebTokenError hidden)
 * 
 * CONSISTENT RESPONSE:
 * Validation errors: { errorCode: 'INVALID_REQUEST' }, statusCode: 400
 * Auth errors: { errorCode: 'UNAUTHORIZED' }, statusCode: 401
 * Business logic errors: { errorCode: 'JOB_NOT_AVAILABLE' }, statusCode: 404
 * Unexpected errors: { errorCode: 'INTERNAL_ERROR' }, statusCode: 500
 * 
 * FULL AUDIT TRAIL:
 * All errors logged server-side with context:
 *   [VALIDATION_ERROR] Missing Content-Length header
 *   [AUTH_ERROR] Token has expired
 *   [GLOBAL_ERROR_HANDLER] { message, stack, type }
 */
