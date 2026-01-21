/**
 * INTEGRATION EXAMPLE - Complete Express Server Setup
 * Copy-paste ready for production
 */

import express, { Express, Request, Response, NextFunction } from 'express';
import uploadRoutes from './routes/upload';
import jobRoutes from './routes/jobs';
import resultsRoutes from './routes/results';
import { sanitizationErrorHandler, globalErrorHandler } from './errors/errorHandler';

/**
 * Create Express application with global error handling
 */
export function createApp(): Express {
  const app = express();

  /**
   * =====================================================================
   * STEP 1: BODY PARSERS
   * =====================================================================
   * Process incoming request bodies
   * Must be before sanitizationErrorHandler
   */
  app.use(express.json({ limit: '10kb' }));
  app.use(express.raw({ type: 'application/octet-stream', limit: '100mb' }));

  /**
   * =====================================================================
   * STEP 2: SANITIZATION ERROR HANDLER
   * =====================================================================
   * Catches framework validation errors (content-type, size, headers)
   * Transforms them to canonical error schema before globalErrorHandler
   */
  app.use(sanitizationErrorHandler);

  /**
   * =====================================================================
   * STEP 3: HEALTH CHECK ROUTE
   * =====================================================================
   * Simple health check for load balancers and monitoring
   */
  app.get('/health', (req: Request, res: Response) => {
    res.status(200).json({ status: 'ok' });
  });

  /**
   * =====================================================================
   * STEP 4: API ROUTES
   * =====================================================================
   * All application routes using asyncHandler() and throwApiError()
   * 
   * Route handlers MUST:
   * - Be wrapped with asyncHandler()
   * - Use throwApiError() for error responses
   * - Never manually serialize errors
   */
  app.use('/upload', uploadRoutes);
  app.use('/jobs', jobRoutes);
  app.use('/results', resultsRoutes);

  /**
   * =====================================================================
   * STEP 5: 404 HANDLER
   * =====================================================================
   * Handle requests to non-existent routes
   * Must be after all other routes
   */
  app.use((req: Request, res: Response) => {
    res.status(404).json({ errorCode: 'NOT_FOUND' });
  });

  /**
   * =====================================================================
   * STEP 6: GLOBAL ERROR HANDLER
   * =====================================================================
   * CRITICAL: Must be LAST in middleware chain
   * 
   * Enforces canonical schema:
   * - ApiError → serialize as-is (errorCode + statusCode)
   * - Other errors → map to INTERNAL_ERROR (500)
   * - No stack traces, messages, or details in response
   */
  app.use(globalErrorHandler);

  return app;
}

/**
 * Start the Express server
 */
export function startServer(): void {
  const app = createApp();
  const port = process.env.PORT || 3000;

  app.listen(port, () => {
    console.log(`✓ Server running on http://localhost:${port}`);
    console.log(`✓ Health check: GET http://localhost:${port}/health`);
    console.log(`✓ API routes: /upload, /jobs, /results`);
  });
}

/**
 * =========================================================================
 * EXAMPLE ROUTE IMPLEMENTATION - Upload Handler
 * =========================================================================
 */

// routes/upload.ts
import { Router } from 'express';
import { asyncHandler } from '../errors/errorHandler';
import { throwApiError } from '../errors/apiError';

const uploadRouter = Router();

uploadRouter.post('/document', asyncHandler(async (req: Request, res: Response) => {
  // Validate input
  if (!req.body) {
    throwApiError('INVALID_REQUEST', 400);
  }

  // Simulate processing
  const uploadId = await processUpload(req.body);

  // Success response
  res.status(201).json({
    uploadId,
    status: 'processing',
  });
}));

uploadRouter.get('/status/:uploadId', asyncHandler(async (req: Request, res: Response) => {
  const { uploadId } = req.params;

  // Check if upload exists
  const upload = await getUploadStatus(uploadId);
  if (!upload) {
    throwApiError('UPLOAD_NOT_FOUND', 404);
  }

  // Return status
  res.json(upload);
}));

/**
 * =========================================================================
 * EXAMPLE ROUTE IMPLEMENTATION - Jobs Handler
 * =========================================================================
 */

// routes/jobs.ts
const jobRouter = Router();

jobRouter.post('/', asyncHandler(async (req: Request, res: Response) => {
  const { jobType, data } = req.body;

  // Validate request
  if (!jobType || !data) {
    throwApiError('INVALID_REQUEST', 400);
  }

  // Create job
  const job = await createJob(jobType, data);

  res.status(201).json({
    jobId: job.id,
    status: 'queued',
  });
}));

jobRouter.get('/:jobId', asyncHandler(async (req: Request, res: Response) => {
  const { jobId } = req.params;

  // Get job
  const job = await getJob(jobId);
  if (!job) {
    throwApiError('JOB_NOT_FOUND', 404);
  }

  // Check authorization
  if (job.userId !== req.user?.id) {
    throwApiError('FORBIDDEN', 403);
  }

  res.json(job);
}));

jobRouter.delete('/:jobId', asyncHandler(async (req: Request, res: Response) => {
  const { jobId } = req.params;

  // Get job
  const job = await getJob(jobId);
  if (!job) {
    throwApiError('JOB_NOT_FOUND', 404);
  }

  // Check authorization
  if (job.userId !== req.user?.id) {
    throwApiError('FORBIDDEN', 403);
  }

  // Delete job
  await deleteJob(jobId);

  res.status(204).send();
}));

/**
 * =========================================================================
 * ERROR RESPONSE FLOW - VISUAL GUIDE
 * =========================================================================
 * 
 * REQUEST
 *   ↓
 * ROUTE HANDLER (wrapped with asyncHandler)
 *   ├→ throwApiError('CODE', status) [VALIDATION ERROR]
 *   │   ↓
 *   │  asyncHandler catches, passes to globalErrorHandler
 *   │   ↓
 *   │  globalErrorHandler recognizes ApiError
 *   │   ↓
 *   │  Response: { errorCode: 'CODE' } with statusCode
 *   │
 *   └→ throw new Error() [UNEXPECTED ERROR]
 *       ↓
 *      asyncHandler catches, passes to globalErrorHandler
 *       ↓
 *      globalErrorHandler recognizes non-ApiError
 *       ↓
 *      Response: { errorCode: 'INTERNAL_ERROR' } with status 500
 * 
 */

/**
 * =========================================================================
 * TESTING THE IMPLEMENTATION
 * =========================================================================
 */

export const testingExample = `
import request from 'supertest';
import { createApp } from './server';

describe('Error Handler Integration', () => {
  const app = createApp();

  test('validation error returns INVALID_REQUEST', async () => {
    const response = await request(app)
      .post('/upload/document')
      .send({})
      .expect(400);

    expect(response.body).toEqual({
      errorCode: 'INVALID_REQUEST',
    });
  });

  test('not found error returns JOB_NOT_FOUND', async () => {
    const response = await request(app)
      .get('/jobs/xyz')
      .expect(404);

    expect(response.body).toEqual({
      errorCode: 'JOB_NOT_FOUND',
    });
  });

  test('permission error returns FORBIDDEN', async () => {
    const response = await request(app)
      .delete('/jobs/123')
      .set('Authorization', 'Bearer token-for-different-user')
      .expect(403);

    expect(response.body).toEqual({
      errorCode: 'FORBIDDEN',
    });
  });

  test('unhandled error returns INTERNAL_ERROR', async () => {
    // This test assumes a route that throws an error
    const response = await request(app)
      .post('/jobs')
      .send({ jobType: 'bad', data: null })
      .expect(500);

    expect(response.body).toEqual({
      errorCode: 'INTERNAL_ERROR',
    });

    // Verify no stack trace in response
    expect(response.body.stack).toBeUndefined();
    expect(response.body.message).toBeUndefined();
  });

  test('health check returns ok', async () => {
    const response = await request(app)
      .get('/health')
      .expect(200);

    expect(response.body).toEqual({ status: 'ok' });
  });

  test('not found route returns NOT_FOUND', async () => {
    const response = await request(app)
      .get('/nonexistent')
      .expect(404);

    expect(response.body).toEqual({
      errorCode: 'NOT_FOUND',
    });
  });
});
`;

/**
 * =========================================================================
 * DEPLOYMENT CHECKLIST
 * =========================================================================
 */

export const deploymentChecklist = `
Before deploying to production:

PROJECT SETUP
[ ] Copy this file to your project
[ ] Update route imports to match your structure
[ ] Verify all routes use asyncHandler()
[ ] Verify all errors use throwApiError()

ERROR HANDLING
[ ] globalErrorHandler is registered LAST
[ ] sanitizationErrorHandler is registered early
[ ] No manual error response serialization
[ ] No try-catch blocks without recovery logic

TESTING
[ ] Run full test suite
[ ] Test validation errors (400)
[ ] Test auth errors (401)
[ ] Test permission errors (403)
[ ] Test not found errors (404)
[ ] Test unhandled errors (500)
[ ] Verify response schema consistency

LOGGING
[ ] Verify console.error() is captured
[ ] Set up monitoring for INTERNAL_ERROR
[ ] Configure error log aggregation
[ ] Test error log output

DOCUMENTATION
[ ] Document all error codes
[ ] Document error recovery strategies
[ ] Update API documentation
[ ] Communicate changes to API consumers

PRODUCTION
[ ] Deploy to staging first
[ ] Monitor error rates
[ ] Verify no information leaks
[ ] Monitor performance impact
[ ] Deploy to production
`;

/**
 * =========================================================================
 * TROUBLESHOOTING
 * =========================================================================
 */

export const troubleshooting = `
Problem: Errors still showing stack traces
Solution: Verify globalErrorHandler is registered LAST in middleware chain
         Check that no middleware after it is also handling errors

Problem: Async errors not being caught
Solution: Verify all async route handlers are wrapped with asyncHandler()
         Check that asyncHandler is imported correctly

Problem: Status code not being set correctly
Solution: Verify throwApiError() is called with correct status code
         Check that globalErrorHandler is setting res.status()

Problem: Custom error codes not working
Solution: Any string can be used as errorCode
         Verify it's passed to throwApiError() as first argument

Problem: Still seeing framework error messages
Solution: Verify sanitizationErrorHandler is registered early
         Check that it's catching framework errors

Problem: Performance issues
Solution: Error handling adds minimal overhead
         Type guards and JSON serialization are fast
         Check if the issue is in your application logic
`;

// Placeholder implementations for demonstration
async function processUpload(body: any): Promise<string> {
  return 'upload-id';
}

async function getUploadStatus(uploadId: string): Promise<any> {
  return { uploadId, status: 'complete' };
}

async function createJob(jobType: string, data: any): Promise<any> {
  return { id: 'job-id', status: 'queued' };
}

async function getJob(jobId: string): Promise<any> {
  return { id: jobId, userId: 'user-id', status: 'processing' };
}

async function deleteJob(jobId: string): Promise<void> {
  // implementation
}

export default {
  createApp,
  startServer,
};
