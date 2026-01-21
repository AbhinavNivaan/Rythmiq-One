/**
 * VALIDATION ERROR SANITIZATION - QUICK REFERENCE
 * 
 * STATUS: ✅ COMPLETE
 * 
 * ============================================================================
 * FILES CREATED
 * ============================================================================
 * 
 * 1. api-gateway/errors/validationErrors.ts
 *    - sendValidationError(res, message?) → { errorCode: 'INVALID_REQUEST' }
 *    - sendAuthError(res, message?) → { errorCode: 'UNAUTHORIZED' }
 *    - sanitizationErrorHandler() → Catches framework errors
 * 
 * 2. api-gateway/errors/errorHandler.ts
 *    - globalErrorHandler() → Final error sanitization
 *    - asyncHandler(fn) → Wraps async route handlers
 * 
 * ============================================================================
 * FILES MODIFIED
 * ============================================================================
 * 
 * 1. api-gateway/routes/upload.ts
 *    ❌ REMOVED: error/message fields exposing details
 *    ❌ REMOVED: MAX_UPLOAD_SIZE in response (was exposing limit)
 *    ❌ REMOVED: Specific HTTP status codes (411, 413)
 *    ✅ ADDED: sendValidationError() for all validation errors
 *    ✅ RESULT: All validation errors now return status 400 + { errorCode: 'INVALID_REQUEST' }
 * 
 * 2. api-gateway/auth/middleware.ts
 *    ❌ REMOVED: "Token expired" message
 *    ❌ REMOVED: "Invalid token" message
 *    ❌ REMOVED: Specific JWT error messages
 *    ✅ ADDED: sendAuthError() for all auth failures
 *    ✅ RESULT: All auth errors now return status 401 + { errorCode: 'UNAUTHORIZED' }
 * 
 * 3. api-gateway/errors/apiError.ts
 *    ✅ ENHANCED: Security documentation and usage examples
 * 
 * ============================================================================
 * ERROR RESPONSE FORMAT (CLIENT ALWAYS SEES)
 * ============================================================================
 * 
 * Validation Error:
 *   Status: 400
 *   Body: { errorCode: 'INVALID_REQUEST' }
 * 
 * Authentication Error:
 *   Status: 401
 *   Body: { errorCode: 'UNAUTHORIZED' }
 * 
 * Server Error:
 *   Status: 500
 *   Body: { errorCode: 'INTERNAL_ERROR' }
 * 
 * ============================================================================
 * SERVER-SIDE LOGGING (DEBUGGING)
 * ============================================================================
 * 
 * All errors logged with full context:
 *   [VALIDATION_ERROR] Invalid Content-Type: expected 'application/octet-stream', got 'text/plain'
 *   [AUTH_ERROR] Token has expired
 *   [GLOBAL_ERROR_HANDLER] { message, stack, type }
 * 
 * ============================================================================
 * WHAT'S NO LONGER EXPOSED
 * ============================================================================
 * 
 * ✓ Size limits (100 MB limit)
 * ✓ Accepted content-types (application/octet-stream)
 * ✓ Header names (x-client-request-id, Authorization)
 * ✓ Token details (expired, invalid signature, missing claims)
 * ✓ Framework errors (body-parser, express errors)
 * ✓ Stack traces
 * ✓ Internal error types
 * 
 * ============================================================================
 * DEPLOYMENT NOTES
 * ============================================================================
 * 
 * In server.ts initialization:
 * 
 *   app.use(express.raw({ type: 'application/octet-stream' }));
 *   app.use(sanitizationErrorHandler);  // BEFORE routes
 *   app.use('/upload', uploadRoutes);
 *   app.use('/jobs', jobRoutes);
 *   app.use(globalErrorHandler);        // AFTER all routes
 * 
 * ============================================================================
 * TESTING CHECKLIST
 * ============================================================================
 * 
 * [ ] Invalid Content-Type → { errorCode: 'INVALID_REQUEST' }, status 400
 * [ ] Missing Content-Length → { errorCode: 'INVALID_REQUEST' }, status 400
 * [ ] Content-Length > limit → { errorCode: 'INVALID_REQUEST' }, status 400
 * [ ] Missing x-client-request-id → { errorCode: 'INVALID_REQUEST' }, status 400
 * [ ] Invalid x-client-request-id → { errorCode: 'INVALID_REQUEST' }, status 400
 * [ ] Missing Authorization header → { errorCode: 'UNAUTHORIZED' }, status 401
 * [ ] Invalid token → { errorCode: 'UNAUTHORIZED' }, status 401
 * [ ] Expired token → { errorCode: 'UNAUTHORIZED' }, status 401
 * [ ] Malformed JSON → { errorCode: 'INVALID_REQUEST' }, status 400
 * [ ] Unhandled exception → { errorCode: 'INTERNAL_ERROR' }, status 500
 * [ ] Server logs contain full error context ✓
 * [ ] No limit values in client response ✓
 * [ ] No header names in client response ✓
 * [ ] No stack traces in client response ✓
 * 
 * ============================================================================
 */
