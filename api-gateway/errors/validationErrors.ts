/**
 * Sanitized validation error handling
 * Prevents leaking internal limits, formats, and API details
 */

import { Request, Response, NextFunction } from 'express';
import { ApiError } from './apiError';

/**
 * Generic validation error response
 * Do NOT expose internal details
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
 * @param res - Express response
 * @param message - Internal debug message (never sent to client)
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
}

/**
 * Send sanitized authentication error
 * @param res - Express response
 * @param message - Internal debug message (never sent to client)
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
 * Wraps body parser errors, malformed JSON, etc.
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
