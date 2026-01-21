/**
 * GLOBAL ERROR HANDLING MIDDLEWARE - IMPLEMENTATION
 * 
 * Complete TypeScript implementation of the canonical ApiError schema
 * with global error handling middleware
 */

/**
 * ============================================================================
 * FILE: api-gateway/errors/apiError.ts
 * ============================================================================
 * Canonical error contract and factory
 */

export interface ApiError extends Error {
  errorCode: string;
  statusCode: number;
}

export function throwApiError(errorCode: string, statusCode: number): never {
  const error = new Error() as ApiError;
  error.errorCode = errorCode;
  error.statusCode = statusCode;
  error.name = 'ApiError';
  throw error;
}

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

/**
 * ============================================================================
 * FILE: api-gateway/errors/errorHandler.ts
 * ============================================================================
 * Global error handler middleware - ENFORCES CANONICAL SCHEMA
 */

import { Request, Response, NextFunction } from 'express';

export function globalErrorHandler(
  err: unknown,
  req: Request,
  res: Response,
  next: NextFunction
): void {
  // Log full error server-side for debugging (NEVER sent to client)
  if (err !== null && typeof err === 'object') {
    const errorObj = err as any;
    console.error('[GLOBAL_ERROR_HANDLER]', {
      errorCode: errorObj.errorCode || 'UNKNOWN',
      statusCode: errorObj.statusCode || 'UNKNOWN',
      message: errorObj.message || 'Unknown error',
      stack: errorObj.stack || 'No stack trace',
      type: errorObj.constructor?.name || typeof err,
      isApiError: isApiError(err),
    });
  } else {
    console.error('[GLOBAL_ERROR_HANDLER]', {
      error: err,
      type: typeof err,
    });
  }

  // ApiError: serialize as-is (already conforms to canonical schema)
  if (isApiError(err)) {
    res.status(err.statusCode).json({
      errorCode: err.errorCode,
    });
    return;
  }

  // Non-ApiError: map to INTERNAL_ERROR (generic, no details exposed)
  res.status(500).json({
    errorCode: 'INTERNAL_ERROR',
  });
}

export function asyncHandler(
  fn: (req: Request, res: Response, next: NextFunction) => Promise<void>
) {
  return (req: Request, res: Response, next: NextFunction) => {
    Promise.resolve(fn(req, res, next)).catch(next);
  };
}

/**
 * ============================================================================
 * FILE: api-gateway/errors/validationErrors.ts
 * ============================================================================
 * Helpers for common validation and auth errors (optional, for convenience)
 */

export const SANITIZED_VALIDATION_ERROR = {
  errorCode: 'INVALID_REQUEST',
  statusCode: 400,
};

export const SANITIZED_AUTH_ERROR = {
  errorCode: 'UNAUTHORIZED',
  statusCode: 401,
};

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

export function sendAuthError(res: Response, message?: string): void {
  if (message) {
    console.warn('[AUTH_ERROR]', message);
  }
  res.status(SANITIZED_AUTH_ERROR.statusCode).json({
    errorCode: SANITIZED_AUTH_ERROR.errorCode,
  });
  return;
}

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

  // Pass to next handler
  next(err);
}

/**
 * ============================================================================
 * FILE: server.ts - COMPLETE SETUP
 * ============================================================================
 * How to register error handlers in the correct order
 */

export function createApp_Example(): any {
  const express = require('express');
  const app = express();

  // ========================================================================
  // BODY PARSERS
  // ========================================================================
  app.use(express.json({ limit: '10kb' }));
  app.use(express.raw({ type: 'application/octet-stream', limit: '100mb' }));

  // ========================================================================
  // SANITIZATION ERROR HANDLER (framework errors)
  // ========================================================================
  app.use(sanitizationErrorHandler);

  // ========================================================================
  // HEALTH CHECK
  // ========================================================================
  app.get('/health', (req: Request, res: Response) => {
    res.status(200).json({ status: 'ok' });
  });

  // ========================================================================
  // API ROUTES
  // ========================================================================
  // Routes use asyncHandler() and throwApiError() for consistent error handling
  // app.use('/upload', uploadRoutes);
  // app.use('/jobs', jobRoutes);
  // app.use('/results', resultsRoutes);

  // ========================================================================
  // 404 HANDLER
  // ========================================================================
  app.use((req: Request, res: Response) => {
    res.status(404).json({ errorCode: 'NOT_FOUND' });
  });

  // ========================================================================
  // GLOBAL ERROR HANDLER (MUST be LAST)
  // ========================================================================
  app.use(globalErrorHandler);

  return app;
}

/**
 * ============================================================================
 * ROUTE IMPLEMENTATION EXAMPLE
 * ============================================================================
 */

export const routeExample = `
import { Router, Request, Response } from 'express';
import { asyncHandler } from '../errors/errorHandler';
import { throwApiError } from '../errors/apiError';

const router = Router();

// Example 1: Validation error
router.post('/validate', asyncHandler(async (req: Request, res: Response) => {
  const { data } = req.body;
  
  if (!data) {
    throwApiError('INVALID_REQUEST', 400);
  }
  
  res.json({ success: true });
}));

// Example 2: Not found error
router.get('/item/:id', asyncHandler(async (req: Request, res: Response) => {
  const item = await getItem(req.params.id);
  
  if (!item) {
    throwApiError('ITEM_NOT_FOUND', 404);
  }
  
  res.json(item);
}));

// Example 3: Permission error
router.delete('/item/:id', asyncHandler(async (req: Request, res: Response) => {
  const item = await getItem(req.params.id);
  
  if (item.userId !== req.user.id) {
    throwApiError('FORBIDDEN', 403);
  }
  
  await deleteItem(item.id);
  res.status(204).send();
}));

// Example 4: Unhandled error (auto-mapped)
router.post('/process', asyncHandler(async (req: Request, res: Response) => {
  // This error will be caught by globalErrorHandler
  // and returned as { errorCode: 'INTERNAL_ERROR' } with status 500
  const result = await unreliableOperation();
  res.json(result);
}));

export default router;
`;

/**
 * ============================================================================
 * ERROR RESPONSE EXAMPLES
 * ============================================================================
 */

export const responseExamples = {
  // Valid request with ApiError
  apiError_400_validation: {
    statusCode: 400,
    body: { errorCode: 'INVALID_REQUEST' },
  },
  apiError_401_auth: {
    statusCode: 401,
    body: { errorCode: 'UNAUTHORIZED' },
  },
  apiError_403_permission: {
    statusCode: 403,
    body: { errorCode: 'FORBIDDEN' },
  },
  apiError_404_notFound: {
    statusCode: 404,
    body: { errorCode: 'JOB_NOT_FOUND' },
  },

  // Non-ApiError (any unhandled error)
  nonApiError_mapped: {
    statusCode: 500,
    body: { errorCode: 'INTERNAL_ERROR' },
  },

  // What is NEVER in the response
  never_in_response: {
    stack: 'Error: Database connection failed at ...',
    message: 'Database connection failed',
    details: 'Connection timeout after 30s',
    error: { /* framework error object */ },
  },
};

/**
 * ============================================================================
 * KEY IMPLEMENTATION FEATURES
 * ============================================================================
 * 
 * 1. SINGLE CANONICAL SCHEMA
 *    - All errors: { errorCode: string }
 *    - HTTP status via response.status()
 *    - No variations or optional fields
 * 
 * 2. TYPE GUARD
 *    - isApiError() checks for errorCode + statusCode
 *    - Distinguishes ApiError from other errors
 *    - Type-safe error checking in globalErrorHandler
 * 
 * 3. AUTOMATIC MAPPING
 *    - Any non-ApiError thrown → INTERNAL_ERROR
 *    - No need to handle different error types
 *    - Prevents accidental leaks of internal errors
 * 
 * 4. ASYNC SUPPORT
 *    - asyncHandler() wraps Promise.resolve().catch(next)
 *    - Catches promise rejections automatically
 *    - Prevents unhandled promise rejection errors
 * 
 * 5. SERVER-SIDE LOGGING
 *    - Full error details logged server-side
 *    - Never included in client response
 *    - Integration point for monitoring tools
 * 
 * 6. MIDDLEWARE ORDER ENFORCEMENT
 *    - sanitizationErrorHandler catches framework errors early
 *    - globalErrorHandler must be last in chain
 *    - 404 handler before globalErrorHandler
 * 
 * 7. NO EXPOSED DETAILS
 *    - Stack traces: never in response
 *    - Error messages: never in response
 *    - Internal implementation: never in response
 *    - Framework objects: never in response
 */
