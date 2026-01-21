/**
 * CANONICAL ERROR SCHEMA - COMPLETE REFERENCE
 * 
 * This file documents the complete error handling system that enforces
 * the canonical ApiError schema globally across all API responses.
 */

/**
 * ============================================================================
 * CANONICAL SCHEMA
 * ============================================================================
 * 
 * All API error responses MUST conform to this schema:
 * 
 *   {
 *     "errorCode": string (SCREAMING_SNAKE_CASE)
 *   }
 * 
 * Additional context:
 *   - HTTP statusCode is set via the response status() call
 *   - NO message field
 *   - NO stack traces
 *   - NO error details
 *   - NO framework error objects
 * 
 * Example response body:
 *   { "errorCode": "INVALID_REQUEST" }
 * 
 * With HTTP status:
 *   Status: 400
 *   Body: { "errorCode": "INVALID_REQUEST" }
 */

/**
 * ============================================================================
 * ERROR HANDLING FLOW
 * ============================================================================
 * 
 * REQUEST → ROUTE HANDLER → ONE OF THREE PATHS:
 * 
 * PATH 1: Valid ApiError thrown
 *   - handler throws throwApiError('ERROR_CODE', statusCode)
 *   - globalErrorHandler catches it
 *   - isApiError() type guard identifies it
 *   - Response: { errorCode: 'ERROR_CODE' } with statusCode
 * 
 * PATH 2: Any other error thrown
 *   - handler throws any Error or object
 *   - globalErrorHandler catches it
 *   - isApiError() type guard returns false
 *   - Response: { errorCode: 'INTERNAL_ERROR' } with status 500
 * 
 * PATH 3: No error (success)
 *   - handler sends response directly
 *   - globalErrorHandler not invoked
 */

/**
 * ============================================================================
 * MIDDLEWARE REGISTRATION ORDER
 * ============================================================================
 * 
 * Correct order in Express app:
 * 
 *   1. app.use(express.json())                    // Parse JSON bodies
 *   2. app.use(sanitizationErrorHandler)          // Catch parser errors
 *   3. app.get('/health', ...)                    // Health checks
 *   4. app.use('/api', routes)                    // All API routes
 *   5. app.use((req, res) => {                    // 404 handler
 *        res.status(404).json({ errorCode: 'NOT_FOUND' })
 *      })
 *   6. app.use(globalErrorHandler)                // MUST be LAST
 * 
 * Why globalErrorHandler must be last:
 *   - Express error handlers have 4 parameters (err, req, res, next)
 *   - Must be registered after all other middleware
 *   - Catches errors passed via next(error)
 *   - Catches any unhandled promise rejections from async handlers
 */

/**
 * ============================================================================
 * STANDARD ERROR CODES
 * ============================================================================
 * 
 * Use these error codes consistently across the API:
 * 
 * 400 BAD REQUEST:
 *   throwApiError('INVALID_REQUEST', 400)
 *   Use for: malformed input, missing fields, validation failures
 * 
 * 401 UNAUTHORIZED:
 *   throwApiError('UNAUTHORIZED', 401)
 *   Use for: missing/invalid credentials, expired tokens
 * 
 * 403 FORBIDDEN:
 *   throwApiError('FORBIDDEN', 403)
 *   Use for: authenticated but lacking permission
 * 
 * 404 NOT FOUND:
 *   throwApiError('JOB_NOT_FOUND', 404) or similar
 *   Use for: requested resource doesn't exist
 * 
 * 409 CONFLICT:
 *   throwApiError('JOB_ALREADY_EXISTS', 409) or similar
 *   Use for: state conflicts, duplicate submissions
 * 
 * 500 INTERNAL ERROR:
 *   throwApiError('INTERNAL_ERROR', 500)
 *   Use for: unexpected server errors (mapped by globalErrorHandler)
 */

/**
 * ============================================================================
 * IMPLEMENTATION EXAMPLES
 * ============================================================================
 */

/**
 * Example 1: Valid Request
 */
export const example1_validRequest = `
import { Router } from 'express';
import { asyncHandler } from '../errors/errorHandler';
import { throwApiError } from '../errors/apiError';

const router = Router();

router.post('/submit', asyncHandler(async (req, res) => {
  // Handler logic
  const { data } = req.body;
  
  // Validation error
  if (!data) {
    throwApiError('INVALID_REQUEST', 400);
  }
  
  // Process data
  const result = processData(data);
  
  // Success response
  res.status(200).json({ result });
}));
`;

/**
 * Example 2: Any Error Auto-Mapped
 */
export const example2_anyErrorMapped = `
router.post('/process', asyncHandler(async (req, res) => {
  // This error will be caught by globalErrorHandler
  // and returned as { errorCode: 'INTERNAL_ERROR' } with status 500
  throw new Error('Database connection failed');
}));
`;

/**
 * Example 3: Nested Async Errors
 */
export const example3_nestedAsyncErrors = `
router.post('/nested', asyncHandler(async (req, res) => {
  // asyncHandler catches promise rejections
  // This works even in nested promises
  const data = await Promise.reject(new Error('Async error'));
  res.json(data);
}));
`;

/**
 * Example 4: Non-ApiError Objects
 */
export const example4_nonApiErrorObjects = `
router.post('/various', asyncHandler(async (req, res) => {
  // All of these are caught and mapped to INTERNAL_ERROR:
  
  // throw null;
  // throw 'string error';
  // throw 42;
  // throw { custom: 'object' };
  // throw new TypeError('type error');
  
  // All result in: { errorCode: 'INTERNAL_ERROR' } + 500 status
}));
`;

/**
 * ============================================================================
 * VALIDATION PATTERNS
 * ============================================================================
 */

/**
 * Pattern 1: Early validation
 */
export const pattern1_earlyValidation = `
router.post('/create', asyncHandler(async (req, res) => {
  const { name, email } = req.body;
  
  // Validate early, fail fast
  if (!name || typeof name !== 'string') {
    throwApiError('INVALID_REQUEST', 400);
  }
  
  if (!email || !email.includes('@')) {
    throwApiError('INVALID_REQUEST', 400);
  }
  
  // Continue with logic
  const result = await createRecord(name, email);
  res.status(201).json(result);
}));
`;

/**
 * Pattern 2: Check existence
 */
export const pattern2_checkExistence = `
router.get('/job/:id', asyncHandler(async (req, res) => {
  const job = await getJob(req.params.id);
  
  if (!job) {
    throwApiError('JOB_NOT_FOUND', 404);
  }
  
  res.json(job);
}));
`;

/**
 * Pattern 3: Permission checks
 */
export const pattern3_permissionChecks = `
router.delete('/job/:id', asyncHandler(async (req, res) => {
  const job = await getJob(req.params.id);
  
  if (!job) {
    throwApiError('JOB_NOT_FOUND', 404);
  }
  
  if (job.userId !== req.user.id) {
    throwApiError('FORBIDDEN', 403);
  }
  
  await deleteJob(job.id);
  res.status(204).send();
}));
`;

/**
 * ============================================================================
 * TESTING THE ERROR HANDLER
 * ============================================================================
 */

export const testingExample = `
describe('Error Handler', () => {
  test('ApiError is serialized as-is', async () => {
    const response = await request(app)
      .post('/test')
      .expect(401)
      .expect({ errorCode: 'UNAUTHORIZED' });
  });

  test('Other errors map to INTERNAL_ERROR', async () => {
    const response = await request(app)
      .post('/test')
      .expect(500)
      .expect({ errorCode: 'INTERNAL_ERROR' });
  });

  test('No stack traces in response', async () => {
    const response = await request(app)
      .post('/test')
      .expect(500);
    
    expect(response.body.stack).toBeUndefined();
  });

  test('No messages in response', async () => {
    const response = await request(app)
      .post('/test')
      .expect(500);
    
    expect(response.body.message).toBeUndefined();
  });
});
`;

/**
 * ============================================================================
 * LOGGING (SERVER-SIDE ONLY)
 * ============================================================================
 * 
 * The globalErrorHandler logs FULL error details server-side:
 * 
 *   [GLOBAL_ERROR_HANDLER] {
 *     errorCode: 'INTERNAL_ERROR',
 *     statusCode: 500,
 *     message: 'Database connection failed',
 *     stack: 'Error: Database connection failed at ...',
 *     type: 'Error',
 *     isApiError: false
 *   }
 * 
 * This gives you debugging information without exposing details to clients.
 * Logs should be sent to monitoring/logging system (e.g., DataDog, Sentry).
 */

/**
 * ============================================================================
 * KEY GUARANTEES
 * ============================================================================
 * 
 * ✓ All error responses have the same schema: { errorCode: string }
 * ✓ No stack traces ever sent to client
 * ✓ No error messages ever sent to client
 * ✓ No framework error objects sent to client
 * ✓ ApiError objects are serialized without modification
 * ✓ All non-ApiErrors are mapped to INTERNAL_ERROR
 * ✓ Async errors are caught via asyncHandler wrapper
 * ✓ Type-safe error checking with isApiError() guard
 */
