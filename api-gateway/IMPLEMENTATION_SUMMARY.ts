/**
 * ============================================================================
 * VALIDATION ERROR SANITIZATION - EXECUTIVE SUMMARY
 * ============================================================================
 * 
 * TASK: Sanitize all request validation errors
 * STATUS: ✅ COMPLETE
 * 
 * ============================================================================
 * PROBLEM IDENTIFIED
 * ============================================================================
 * 
 * Validation errors were leaking sensitive internal information:
 * 
 * ❌ Size Limits: "Upload exceeds maximum size of 104857600 bytes" (100 MB)
 * ❌ Header Names: "x-client-request-id header is required"
 * ❌ Formats: "Expected 'application/octet-stream', got 'text/plain'"
 * ❌ Token Details: "Token expired", "Invalid token claims"
 * ❌ Framework Info: "entity.parse.failed", "Payload Too Large"
 * ❌ Stack Traces: Full JavaScript stack with file paths and line numbers
 * 
 * SECURITY IMPACT:
 * - Attackers could enumerate valid headers
 * - Attackers could learn API constraints
 * - Framework versions could be fingerprinted
 * - Source code structure could be reverse-engineered
 * 
 * ============================================================================
 * SOLUTION IMPLEMENTED
 * ============================================================================
 * 
 * All validation errors now return IDENTICAL sanitized responses:
 * 
 * ✅ Validation Errors: { errorCode: 'INVALID_REQUEST' }, statusCode: 400
 * ✅ Auth Errors: { errorCode: 'UNAUTHORIZED' }, statusCode: 401
 * ✅ Server Errors: { errorCode: 'INTERNAL_ERROR' }, statusCode: 500
 * 
 * Full context logged server-side:
 * ✅ Console logs with [VALIDATION_ERROR], [AUTH_ERROR], [GLOBAL_ERROR_HANDLER]
 * ✅ Stack traces available in server logs (not in client responses)
 * ✅ Complete error context for debugging
 * 
 * ============================================================================
 * FILES CREATED (New Sanitization Layer)
 * ============================================================================
 * 
 * 1. api-gateway/errors/validationErrors.ts
 *    ├─ sendValidationError(res, message?) → Sanitized validation response
 *    ├─ sendAuthError(res, message?) → Sanitized auth response
 *    ├─ sanitizationErrorHandler() → Catches framework errors
 *    ├─ SANITIZED_VALIDATION_ERROR constant
 *    └─ SANITIZED_AUTH_ERROR constant
 * 
 * 2. api-gateway/errors/errorHandler.ts
 *    ├─ globalErrorHandler() → Final error sanitization (last middleware)
 *    └─ asyncHandler(fn) → Wraps async route handlers
 * 
 * Documentation Files (Reference Only):
 * 3. api-gateway/COMPLETE_IMPLEMENTATION.ts
 * 4. api-gateway/SANITIZATION_IMPLEMENTATION.ts
 * 5. api-gateway/SANITIZATION_QUICK_REFERENCE.ts
 * 6. api-gateway/BEFORE_AFTER_COMPARISON.ts
 * 7. api-gateway/SERVER_INTEGRATION_EXAMPLE.ts
 * 
 * ============================================================================
 * FILES MODIFIED (Updated for Sanitization)
 * ============================================================================
 * 
 * 1. api-gateway/routes/upload.ts
 *    BEFORE: res.status(400).json({ error: '...', message: '...' })
 *    AFTER: sendValidationError(res, 'internal debug message')
 * 
 *    Changes:
 *    ✅ Added import: sendValidationError
 *    ✅ Replaced Content-Type validation (no format exposed)
 *    ✅ Replaced Content-Length validation (no limit exposed)
 *    ✅ Replaced header validation (no header names exposed)
 *    ✅ All errors now return status 400 + { errorCode: 'INVALID_REQUEST' }
 * 
 * 2. api-gateway/auth/middleware.ts
 *    BEFORE: res.status(401).json({ error: '...', message: '...' })
 *    AFTER: sendAuthError(res, 'internal debug message')
 * 
 *    Changes:
 *    ✅ Added import: sendAuthError
 *    ✅ Removed "Token expired" message
 *    ✅ Removed "Invalid token" message
 *    ✅ Removed "Invalid token claims" message
 *    ✅ All errors now return status 401 + { errorCode: 'UNAUTHORIZED' }
 * 
 * 3. api-gateway/errors/apiError.ts
 *    ✅ Enhanced documentation
 *    ✅ Added security warnings
 *    ✅ Added usage examples
 * 
 * ============================================================================
 * NO DETAILS EXPOSED (Guaranteed)
 * ============================================================================
 * 
 * BEFORE                              AFTER
 * ─────────────────────────────────────────────────────────────────────
 * Size limits        ❌ Exposed        ✅ Secret
 * Header names       ❌ Exposed        ✅ Secret
 * Format specs       ❌ Exposed        ✅ Secret
 * Token state        ❌ Exposed        ✅ Secret
 * Framework type     ❌ Exposed        ✅ Secret
 * Framework version  ❌ Exposed        ✅ Secret
 * Stack traces       ❌ In response    ✅ In server logs only
 * File paths         ❌ In response    ✅ In server logs only
 * Line numbers       ❌ In response    ✅ In server logs only
 * 
 * ============================================================================
 * HOW IT WORKS
 * ============================================================================
 * 
 * VALIDATION ERROR FLOW:
 * 1. Request arrives
 * 2. Body parser processes it
 * 3. Framework error? → sanitizationErrorHandler catches it
 * 4. Route validation check? → sendValidationError() sanitizes it
 * 5. Auth check? → sendAuthError() sanitizes it
 * 6. Unhandled exception? → globalErrorHandler sanitizes it
 * 
 * CLIENT SEES:           SERVER LOGS:
 * ────────────────────────────────────────────────────────────────────
 * { errorCode: '...' }   [VALIDATION_ERROR] Missing header: x-client-request-id
 * Status: 400            [AUTH_ERROR] Token has expired
 * (No details)           [GLOBAL_ERROR_HANDLER] TypeError at line 42
 *                        Full stack trace for debugging
 * 
 * ============================================================================
 * DEPLOYMENT INSTRUCTIONS
 * ============================================================================
 * 
 * Files are ready to use. Code is TypeScript-only as requested.
 * 
 * In your server.ts initialization:
 * 
 *   import { sanitizationErrorHandler, globalErrorHandler } from './errors/errorHandler';
 *   
 *   const app = express();
 *   
 *   // 1. Body parsers
 *   app.use(express.json());
 *   app.use(express.raw({ type: 'application/octet-stream' }));
 *   
 *   // 2. Sanitization error handler (catches framework errors)
 *   app.use(sanitizationErrorHandler);
 *   
 *   // 3. Routes (upload, jobs, results)
 *   app.use('/upload', uploadRoutes);
 *   app.use('/jobs', jobRoutes);
 *   app.use('/results', resultsRoutes);
 *   
 *   // 4. Global error handler (MUST be last)
 *   app.use(globalErrorHandler);
 * 
 * ============================================================================
 * VALIDATION CHECKLIST
 * ============================================================================
 * 
 * ✅ All validation errors return { errorCode: 'INVALID_REQUEST' }
 * ✅ All auth errors return { errorCode: 'UNAUTHORIZED' }
 * ✅ All server errors return { errorCode: 'INTERNAL_ERROR' }
 * ✅ Size limits never exposed in error messages
 * ✅ Header names never exposed in error messages
 * ✅ Format specifications never exposed in error messages
 * ✅ Token details never exposed in error messages
 * ✅ Framework errors caught and sanitized
 * ✅ Stack traces only in server logs (never in client response)
 * ✅ Full error context logged for debugging
 * ✅ Consistent error format across all endpoints
 * ✅ TypeScript-only implementation
 * ✅ Ready for production deployment
 * 
 * ============================================================================
 * SECURITY BENEFITS
 * ============================================================================
 * 
 * 1. PREVENTS RECONNAISSANCE
 *    Attackers cannot enumerate:
 *    - API limits and constraints
 *    - Required header names
 *    - Accepted request formats
 *    - Framework type and version
 * 
 * 2. CONSISTENT API SURFACE
 *    Single error code for all validation failures
 *    No clues about which field/rule failed
 * 
 * 3. AUDIT TRAIL
 *    Full errors logged server-side
 *    Available for security investigations
 * 
 * 4. DEFENSE IN DEPTH
 *    Three layers of error handling:
 *    - Framework level (sanitizationErrorHandler)
 *    - Route level (sendValidationError, sendAuthError)
 *    - Global level (globalErrorHandler)
 * 
 * 5. FUTURE-PROOF
 *    Changes to limits or formats won't leak new information
 * 
 * ============================================================================
 * REFERENCE DOCUMENTATION
 * ============================================================================
 * 
 * See documentation files in api-gateway/ directory:
 * 
 * • COMPLETE_IMPLEMENTATION.ts
 *   → Full TypeScript code ready to copy/paste
 * 
 * • SANITIZATION_IMPLEMENTATION.ts
 *   → Security principles and implementation guide
 * 
 * • SANITIZATION_QUICK_REFERENCE.ts
 *   → Quick lookup for changes and testing
 * 
 * • BEFORE_AFTER_COMPARISON.ts
 *   → Detailed before/after examples for all error types
 * 
 * • SERVER_INTEGRATION_EXAMPLE.ts
 *   → How to integrate into existing Express app
 * 
 * ============================================================================
 */
