/**
 * QUICK REFERENCE - GLOBAL ERROR HANDLER
 * Copy-paste ready implementation
 */

/**
 * ============================================================================
 * FILE: api-gateway/errors/apiError.ts
 * ============================================================================
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
 */

import { Request, Response, NextFunction } from 'express';

function isApiError(err: unknown): err is ApiError {
  return (
    err !== null &&
    typeof err === 'object' &&
    'errorCode' in err &&
    'statusCode' in err &&
    typeof (err as any).errorCode === 'string' &&
    typeof (err as any).statusCode === 'number'
  );
}

export function globalErrorHandler(
  err: unknown,
  req: Request,
  res: Response,
  next: NextFunction
): void {
  // Log full error server-side for debugging
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

  // ApiError: serialize as-is
  if (isApiError(err)) {
    res.status(err.statusCode).json({
      errorCode: err.errorCode,
    });
    return;
  }

  // Non-ApiError: map to INTERNAL_ERROR
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
 * ROUTE HANDLER EXAMPLE
 * ============================================================================
 */

import { Router } from 'express';

const router = Router();

// Example 1: Validation
router.post('/submit', asyncHandler(async (req, res) => {
  const { data } = req.body;
  
  if (!data) {
    throwApiError('INVALID_REQUEST', 400);
  }
  
  res.json({ success: true });
}));

// Example 2: Not Found
router.get('/item/:id', asyncHandler(async (req, res) => {
  const item = await getItem(req.params.id);
  
  if (!item) {
    throwApiError('ITEM_NOT_FOUND', 404);
  }
  
  res.json(item);
}));

// Example 3: Permission
router.delete('/item/:id', asyncHandler(async (req, res) => {
  const item = await getItem(req.params.id);
  
  if (item.userId !== req.user.id) {
    throwApiError('FORBIDDEN', 403);
  }
  
  await deleteItem(item.id);
  res.status(204).send();
}));

/**
 * ============================================================================
 * SERVER SETUP
 * ============================================================================
 */

import express from 'express';
import { sanitizationErrorHandler } from './errors/errorHandler';

export function createApp() {
  const app = express();

  // Body parsers
  app.use(express.json({ limit: '10kb' }));
  app.use(express.raw({ type: 'application/octet-stream', limit: '100mb' }));

  // Sanitization error handler
  app.use(sanitizationErrorHandler);

  // Health check
  app.get('/health', (req, res) => {
    res.status(200).json({ status: 'ok' });
  });

  // API routes
  app.use('/api', routes);

  // 404 handler
  app.use((req, res) => {
    res.status(404).json({ errorCode: 'NOT_FOUND' });
  });

  // Global error handler (MUST be LAST)
  app.use(globalErrorHandler);

  return app;
}

/**
 * ============================================================================
 * ERROR CODE REFERENCE
 * ============================================================================
 */

export const errorCodes = {
  // 400 Bad Request
  INVALID_REQUEST: {
    code: 'INVALID_REQUEST',
    status: 400,
    use: 'Validation failures, malformed input',
  },

  // 401 Unauthorized
  UNAUTHORIZED: {
    code: 'UNAUTHORIZED',
    status: 401,
    use: 'Missing or invalid credentials',
  },

  // 403 Forbidden
  FORBIDDEN: {
    code: 'FORBIDDEN',
    status: 403,
    use: 'Authenticated but lacking permission',
  },

  // 404 Not Found
  NOT_FOUND: {
    code: 'NOT_FOUND',
    status: 404,
    use: 'Resource not found',
  },

  // 500 Internal Error
  INTERNAL_ERROR: {
    code: 'INTERNAL_ERROR',
    status: 500,
    use: 'Unexpected server error (auto-mapped)',
  },
};

/**
 * ============================================================================
 * RESPONSE EXAMPLES
 * ============================================================================
 */

export const examples = {
  // Validation Error
  validationError: {
    request: 'POST /api/submit with missing data',
    response: 'Status 400: { "errorCode": "INVALID_REQUEST" }',
  },

  // Not Found Error
  notFoundError: {
    request: 'GET /api/item/xyz',
    response: 'Status 404: { "errorCode": "ITEM_NOT_FOUND" }',
  },

  // Permission Error
  permissionError: {
    request: 'DELETE /api/item/123 (different user)',
    response: 'Status 403: { "errorCode": "FORBIDDEN" }',
  },

  // Unhandled Error
  unhandledError: {
    request: 'Any route that throws unexpected error',
    response: 'Status 500: { "errorCode": "INTERNAL_ERROR" }',
  },
};

/**
 * ============================================================================
 * CHECKLIST
 * ============================================================================
 */

export const checklist = `
Implementation Checklist:

[ ] Update api-gateway/errors/apiError.ts
[ ] Update api-gateway/errors/errorHandler.ts
[ ] Wrap all async route handlers with asyncHandler()
[ ] Replace all manual error responses with throwApiError()
[ ] Verify globalErrorHandler is registered LAST
[ ] Verify sanitizationErrorHandler is registered EARLY
[ ] Run test suite (ERROR_HANDLER_TESTS.ts)
[ ] Test in staging environment
[ ] Verify no sensitive data in logs
[ ] Document error codes for API consumers
[ ] Deploy to production
`;

/**
 * ============================================================================
 * KEY POINTS
 * ============================================================================
 */

export const keyPoints = `
✅ CANONICAL SCHEMA
   All errors: { errorCode: string }

✅ TYPE GUARD
   isApiError() distinguishes ApiError from other errors

✅ AUTOMATIC MAPPING
   Non-ApiError → INTERNAL_ERROR (500)

✅ ASYNC SUPPORT
   asyncHandler() catches promise rejections

✅ NO LEAKS
   Stack traces, messages, details: never in response

✅ SERVER-SIDE LOGGING
   Full error details logged for debugging

✅ TYPE SAFETY
   Uses unknown instead of any
   Type narrowing with isApiError()

✅ CONSISTENT
   All errors handled uniformly
   No special cases
`;
