import { Router, Request, Response, NextFunction } from 'express';
import { v4 as uuidv4 } from 'uuid';
import { storageLayer } from '../storage';
import { authenticateRequest } from '../auth/middleware';
import { jobStore } from '../../engine/jobs/jobStore';
import { sendValidationError } from '../errors/validationErrors';

const router = Router();

// Configuration
const MAX_UPLOAD_SIZE = 100 * 1024 * 1024; // 100 MB
const ACCEPTED_CONTENT_TYPE = 'application/octet-stream';

// Product default schema (server-assigned)
const DEFAULT_SCHEMA_ID = 'invoice';
const DEFAULT_SCHEMA_VERSION = 'v1';

/**
 * POST /upload
 * 
 * Upload envelope containing encrypted payload.
 * Server treats payload as opaque bytes and does NOT inspect contents.
 * 
 * Body format: Raw binary (application/octet-stream)
 * Rationale: Raw binary chosen over multipart for:
 * - Simpler streaming without multipart overhead
 * - Direct payload passthrough without parsing
 * - Better performance for large uploads
 * - Aligns with crypto-blind architecture
 */
router.post(
  '/upload',
  authenticateRequest,
  validateUploadRequest,
  async (req: Request, res: Response, next: NextFunction) => {
    try {
      // Extract headers (already validated by middleware)
      const clientRequestId = req.headers['x-client-request-id'] as string;
      const userId = (req as any).userId as string;
      
      // Generate server-side blob identifier
      const blobId = uuidv4();
      
      // Get payload bytes
      const payloadBuffer = req.body;
      
      // Pass opaque bytes to storage layer with idempotency support
      // Storage layer checks (userId, clientRequestId) and returns existing blobId if found
      const storageResult = await storageLayer.store({
        blobId,
        clientRequestId,
        payloadBytes: payloadBuffer,
        userId,
      });

      // Create job record with idempotent behavior
      // Attach server-assigned schema metadata
      const jobResult = await jobStore.createJob({
        blobId: storageResult.blobId,
        userId,
        clientRequestId,
        schemaId: DEFAULT_SCHEMA_ID,
        schemaVersion: DEFAULT_SCHEMA_VERSION,
      });
      
      res.status(storageResult.isNewUpload ? 201 : 200).json({
        blobId: storageResult.blobId,
        jobId: jobResult.jobId,
        clientRequestId,
        uploadedBytes: payloadBuffer.length,
      });
    } catch (error) {
      next(error);
    }
  }
);

/**
 * Validate upload request
 * - Content-Type must be application/octet-stream
 * - Content-Length must not exceed MAX_UPLOAD_SIZE
 * - clientRequestId header must be present
 */
function validateUploadRequest(
  req: Request,
  res: Response,
  next: NextFunction
): void {
  // Validate Content-Type
  const contentType = req.headers['content-type'];
  if (contentType !== ACCEPTED_CONTENT_TYPE) {
    sendValidationError(
      res,
      `Invalid Content-Type: expected '${ACCEPTED_CONTENT_TYPE}', got '${contentType}'`
    );
    return;
  }

  // Validate Content-Length
  const contentLength = parseInt(req.headers['content-length'] || '0', 10);
  if (contentLength === 0) {
    sendValidationError(
      res,
      'Missing or zero Content-Length header'
    );
    return;
  }

  if (contentLength > MAX_UPLOAD_SIZE) {
    sendValidationError(
      res,
      `Content-Length ${contentLength} exceeds maximum size of ${MAX_UPLOAD_SIZE}`
    );
    return;
  }

  // Validate clientRequestId header
  const clientRequestId = req.headers['x-client-request-id'];
  if (!clientRequestId) {
    sendValidationError(
      res,
      'Missing required header: x-client-request-id'
    );
    return;
  }

  if (typeof clientRequestId !== 'string' || clientRequestId.trim() === '') {
    sendValidationError(
      res,
      'Invalid x-client-request-id: must be non-empty string'
    );
    return;
  }

  next();
}

export default router;
