/**
 * SERVER.TS INTEGRATION EXAMPLE
 * How to set up the API gateway with error sanitization
 */

import express, { Express } from 'express';
import uploadRoutes from './routes/upload';
import jobRoutes from './routes/jobs';
import resultsRoutes from './routes/results';
import { sanitizationErrorHandler, globalErrorHandler } from './errors/errorHandler';

/**
 * Initialize Express application with proper error handling
 */
export function createApp(): Express {
  const app = express();

  // ========================================================================
  // BODY PARSERS (Process incoming request bodies)
  // ========================================================================
  // Must be before sanitizationErrorHandler so framework errors are caught

  // JSON parser for typical requests
  app.use(express.json({ limit: '10kb' }));

  // Raw binary parser for upload endpoint
  // Limit set here (100MB) but NOT exposed in error responses
  app.use(express.raw({ type: 'application/octet-stream', limit: '100mb' }));

  // ========================================================================
  // SANITIZATION ERROR HANDLER (Catch framework validation errors)
  // ========================================================================
  // Catches errors from body parsers before they reach routes
  // Sanitizes framework errors: content-type, size, header validation
  app.use(sanitizationErrorHandler);

  // ========================================================================
  // HEALTH CHECK & STATIC ROUTES (Optional)
  // ========================================================================
  app.get('/health', (req, res) => {
    res.status(200).json({ status: 'ok' });
  });

  // ========================================================================
  // API ROUTES
  // ========================================================================
  // Routes handle their own validation using sendValidationError()
  // Auth errors in routes use sendAuthError()
  app.use('/upload', uploadRoutes);
  app.use('/jobs', jobRoutes);
  app.use('/results', resultsRoutes);

  // ========================================================================
  // 404 HANDLER (Routes not found)
  // ========================================================================
  app.use((req, res) => {
    res.status(404).json({ errorCode: 'NOT_FOUND' });
  });

  // ========================================================================
  // GLOBAL ERROR HANDLER (Catch all unhandled errors)
  // ========================================================================
  // MUST be last in middleware chain
  // Sanitizes any errors that weren't caught earlier
  // Routes can pass errors with next(error)
  app.use(globalErrorHandler);

  return app;
}

/**
 * Start the server
 */
export function startServer(): void {
  const app = createApp();
  const port = process.env.PORT || 3000;

  app.listen(port, () => {
    console.log(`Server running on http://localhost:${port}`);
  });
}

// ============================================================================
// ERROR FLOW DIAGRAM
// ============================================================================
//
//  Request
//    ↓
//  Body Parser (express.json, express.raw)
//    ↓
//  Framework Error? → sanitizationErrorHandler → { errorCode: 'INVALID_REQUEST' }
//    ↓ (No error)
//  Route Handler
//    ↓
//  Validation Check → sendValidationError() → { errorCode: 'INVALID_REQUEST' }
//    ↓ (Passes validation)
//  Auth Check → sendAuthError() → { errorCode: 'UNAUTHORIZED' }
//    ↓ (Passes auth)
//  Business Logic
//    ↓
//  Throws Error? → next(error) → globalErrorHandler
//    ↓ (Error caught)
//  globalErrorHandler → Sanitize & Log → { errorCode: 'INTERNAL_ERROR' }
//    ↓
//  Response to Client
//
// ============================================================================
// MIDDLEWARE REGISTRATION ORDER (CRITICAL)
// ============================================================================
//
// 1. Body parsers
//    app.use(express.json());
//    app.use(express.raw({ ... }));
//
// 2. Sanitization error handler (catches framework errors)
//    app.use(sanitizationErrorHandler);
//
// 3. Routes
//    app.use('/upload', uploadRoutes);
//    app.use('/jobs', jobRoutes);
//    app.use('/results', resultsRoutes);
//
// 4. 404 handler (optional but recommended)
//    app.use((req, res) => res.status(404).json({ errorCode: 'NOT_FOUND' }));
//
// 5. Global error handler (MUST be last)
//    app.use(globalErrorHandler);
//
// ============================================================================
// ROUTE HANDLER PATTERNS
// ============================================================================

/**
 * Pattern 1: Synchronous route with validation
 */
function uploadRouteExample(req: express.Request, res: express.Response, next: express.NextFunction) {
  // Validation errors are caught here
  const { sendValidationError } = require('./errors/validationErrors');

  if (!req.headers['x-client-request-id']) {
    sendValidationError(res, 'Missing header: x-client-request-id');
    return;
  }

  // Success
  res.status(200).json({ blobId: 'blob-123' });
}

/**
 * Pattern 2: Async route with error handling
 */
async function jobRouteAsyncExample(
  req: express.Request,
  res: express.Response,
  next: express.NextFunction
) {
  try {
    const { asyncHandler } = require('./errors/errorHandler');

    // Async code here
    const job = await getJobFromDatabase(req.params.jobId);

    if (!job) {
      const { throwApiError } = require('./errors/apiError');
      throwApiError('JOB_NOT_AVAILABLE', 404);
    }

    res.status(200).json(job);
  } catch (error) {
    // Pass to global error handler
    next(error);
  }
}

/**
 * Pattern 3: Using asyncHandler wrapper (recommended)
 */
function setupAsyncRouteExample() {
  const { asyncHandler } = require('./errors/errorHandler');
  const { throwApiError } = require('./errors/apiError');

  // Async route that automatically catches errors
  return asyncHandler(async (req, res, next) => {
    const job = await getJobFromDatabase(req.params.jobId);

    if (!job) {
      throwApiError('JOB_NOT_AVAILABLE', 404);
    }

    res.status(200).json(job);
  });
}

/**
 * Pattern 4: Auth middleware with sanitized errors
 */
function authMiddlewareExample(req: express.Request, res: express.Response, next: express.NextFunction) {
  const { sendAuthError } = require('./errors/validationErrors');

  const token = req.headers.authorization?.substring(7);

  if (!token) {
    sendAuthError(res, 'Missing authorization token');
    return;
  }

  try {
    // Verify token...
    next();
  } catch (error) {
    sendAuthError(res, 'Token verification failed');
    return;
  }
}

// ============================================================================
// TESTING VALIDATION
// ============================================================================

/**
 * Test cases to verify error sanitization:
 * 
 * 1. Content-Type Validation
 *    POST /upload -H "Content-Type: text/plain" -H "x-client-request-id: 123"
 *    Expected: { errorCode: 'INVALID_REQUEST' }, status 400
 *    NOT: message exposing accepted content-type
 * 
 * 2. Size Limit (Framework)
 *    POST /upload -H "Content-Type: application/octet-stream" --data-binary "@100mb.bin"
 *    Expected: { errorCode: 'INVALID_REQUEST' }, status 400
 *    NOT: message with exact size limit (104857600)
 * 
 * 3. Missing Header
 *    POST /upload -H "Content-Type: application/octet-stream" --data-binary "@file.bin"
 *    Expected: { errorCode: 'INVALID_REQUEST' }, status 400
 *    NOT: message with header name (x-client-request-id)
 * 
 * 4. Auth Failure
 *    GET /jobs/123 -H "Authorization: Bearer invalid"
 *    Expected: { errorCode: 'UNAUTHORIZED' }, status 401
 *    NOT: message saying "Token expired" or "Invalid signature"
 * 
 * 5. Unhandled Error
 *    GET /jobs/nonexistent (triggers database error)
 *    Expected: { errorCode: 'INTERNAL_ERROR' }, status 500
 *    NOT: stack trace or error details
 * 
 * Verify server logs:
 *    [VALIDATION_ERROR] Invalid Content-Type: expected...
 *    [AUTH_ERROR] Token has expired
 *    [GLOBAL_ERROR_HANDLER] { message, stack, type }
 */

// Helper function (stub)
async function getJobFromDatabase(jobId: string): Promise<any> {
  // Implementation
  return null;
}
