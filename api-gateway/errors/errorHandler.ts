/**
 * Global error handler for Express
 * Sanitizes all errors before sending to client
 * Prevents leaking stack traces, internal details, or framework information
 */

import { Request, Response, NextFunction } from 'express';
import { ApiError } from './apiError';

/**
 * Global error handler middleware
 * Must be registered LAST in the middleware chain
 * 
 * @param err - The error object
 * @param req - Express request
 * @param res - Express response
 * @param next - Express next function
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
 * Create a wrapper for route handlers to catch async errors
 * 
 * Usage:
 * router.get('/path', asyncHandler(async (req, res) => { ... }))
 */
export function asyncHandler(
  fn: (req: Request, res: Response, next: NextFunction) => Promise<void>
) {
  return (req: Request, res: Response, next: NextFunction) => {
    Promise.resolve(fn(req, res, next)).catch(next);
  };
}
