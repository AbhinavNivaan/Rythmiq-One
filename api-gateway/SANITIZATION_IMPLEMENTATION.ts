/**
 * ============================================================================
 * VALIDATION ERROR SANITIZATION - IMPLEMENTATION GUIDE
 * ============================================================================
 * 
 * All request validation errors now return sanitized responses that do NOT
 * expose internal limits, API details, header names, or framework specifics.
 * 
 * CRITICAL PRINCIPLE:
 * - Client receives: { errorCode: 'INVALID_REQUEST' } with statusCode: 400
 * - Server logs: Full error details for debugging
 * - Never leak size limits, header names, format specifications
 * 
 * ============================================================================
 * FILES MODIFIED
 * ============================================================================
 * 
 * 1. api-gateway/errors/validationErrors.ts [NEW]
 *    - sendValidationError(res, message?) - Sanitized validation error
 *    - sendAuthError(res, message?) - Sanitized auth error
 *    - sanitizationErrorHandler - Framework error catcher
 *    - SANITIZED_VALIDATION_ERROR constant
 *    - SANITIZED_AUTH_ERROR constant
 * 
 * 2. api-gateway/routes/upload.ts [MODIFIED]
 *    - Replaced all validation error responses with sendValidationError()
 *    - Content-Type validation: No longer exposes expected format
 *    - Content-Length validation: No longer exposes MAX_UPLOAD_SIZE
 *    - Header validation: No longer exposes specific header names
 *    - All errors now return: { errorCode: 'INVALID_REQUEST' }, statusCode: 400
 * 
 * 3. api-gateway/auth/middleware.ts [MODIFIED]
 *    - Replaced all auth error responses with sendAuthError()
 *    - Token expiration error: No longer says "Token expired"
 *    - Invalid token error: No longer says "Invalid token"
 *    - JWT verification errors: Generic message only
 *    - All errors now return: { errorCode: 'UNAUTHORIZED' }, statusCode: 401
 * 
 * 4. api-gateway/errors/apiError.ts [MODIFIED]
 *    - Enhanced documentation with security warnings
 *    - Clarified that errorCode should never include details
 *    - Added usage examples for proper error codes
 * 
 * 5. api-gateway/errors/errorHandler.ts [NEW]
 *    - globalErrorHandler - Catches all unhandled errors
 *    - asyncHandler - Wrapper for async route handlers
 *    - Sanitizes all errors before client response
 *    - Server-side logging for debugging
 * 
 * ============================================================================
 * MIGRATION CHECKLIST
 * ============================================================================
 * 
 * [ ] Register sanitizationErrorHandler in Express app (before routes)
 * [ ] Register globalErrorHandler in Express app (after all routes)
 * [ ] Import sendValidationError, sendAuthError in all route files
 * [ ] Import asyncHandler for async route handlers
 * [ ] Update server.ts to:
 *     app.use(sanitizationErrorHandler);  // First
 *     app.use(routes);                     // Routes here
 *     app.use(globalErrorHandler);         // Last
 * [ ] Test: Verify no stack traces leak in error responses
 * [ ] Test: Verify internal details not in client responses
 * [ ] Test: Verify server logs contain full error context
 * 
 * ============================================================================
 * ERROR RESPONSE EXAMPLES (BEFORE → AFTER)
 * ============================================================================
 * 
 * Content-Type Validation:
 *   BEFORE:
 *     { error: 'Invalid Content-Type', 
 *       message: 'Expected \'application/octet-stream\', got \'application/json\'' }
 *   AFTER:
 *     { errorCode: 'INVALID_REQUEST' }
 * 
 * Size Limit Exceeded:
 *   BEFORE:
 *     { error: 'Payload Too Large', 
 *       message: 'Upload exceeds maximum size of 104857600 bytes' }
 *   AFTER:
 *     { errorCode: 'INVALID_REQUEST' }
 * 
 * Missing Header:
 *   BEFORE:
 *     { error: 'Missing Header',
 *       message: 'x-client-request-id header is required' }
 *   AFTER:
 *     { errorCode: 'INVALID_REQUEST' }
 * 
 * Token Expired:
 *   BEFORE:
 *     { error: 'Unauthorized', 
 *       message: 'Token expired' }
 *   AFTER:
 *     { errorCode: 'UNAUTHORIZED' }
 * 
 * ============================================================================
 * TECHNICAL DETAILS
 * ============================================================================
 * 
 * Server-Side Logging:
 * All errors are logged with full context server-side:
 *   console.warn('[VALIDATION_ERROR]', 'Missing Content-Length header')
 *   console.error('[AUTH_ERROR]', 'Token has expired')
 *   console.error('[GLOBAL_ERROR_HANDLER]', { message, stack, type })
 * 
 * Framework Error Handling:
 * The sanitizationErrorHandler catches Express/body-parser errors:
 *   - Malformed JSON (entity.parse.failed)
 *   - Content-Type mismatches
 *   - Payload size exceeding limits
 *   - Invalid header formats
 * 
 * No Details Leaked:
 * ✓ Size limits NOT exposed
 * ✓ Header names NOT exposed
 * ✓ Format specifications NOT exposed
 * ✓ Framework details NOT exposed
 * ✓ Stack traces NOT exposed
 * ✓ Internal error types NOT exposed
 * 
 * ============================================================================
 * SECURITY BENEFITS
 * ============================================================================
 * 
 * 1. Prevents Reconnaissance
 *    Attackers cannot enumerate valid header names or size limits
 * 
 * 2. Consistent API Surface
 *    Single error code ('INVALID_REQUEST') for all validation failures
 * 
 * 3. Audit Trail
 *    Full errors logged server-side for security investigations
 * 
 * 4. Defense in Depth
 *    Framework errors caught and sanitized before reaching client
 * 
 * 5. Future-Proof
 *    Changes to limits/formats don't leak new information
 * 
 * ============================================================================
 */

// This file is a reference guide. No code here.
