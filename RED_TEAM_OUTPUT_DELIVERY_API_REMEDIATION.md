# Output Delivery API - Remediation Code Examples

**Date:** 5 January 2026  
**Purpose:** Concrete code fixes for all BLOCKER findings

---

## Overview

Three BLOCKER findings require fixes before production:
1. Error messages leak system state (Finding #1, #2, #3)
2. Error response schema is inconsistent (Finding #4)
3. No opaque error codes (Finding #4)

This document provides concrete code to fix all issues.

---

## Step 1: Create Error Code Definitions

**New File:** `api-gateway/types/errors.ts`

```typescript
/**
 * Opaque error codes for API responses
 * 
 * All errors must use these codes instead of verbose messages.
 * System state, API requirements, and limits must never be exposed to clients.
 */

export enum ErrorCode {
  // Authentication errors (401)
  UNAUTHORIZED = 'UNAUTHORIZED',
  TOKEN_EXPIRED = 'TOKEN_EXPIRED',
  INVALID_TOKEN = 'INVALID_TOKEN',
  INVALID_TOKEN_CLAIMS = 'INVALID_TOKEN_CLAIMS',
  AUTH_FAILED = 'AUTH_FAILED',

  // Authorization errors (403)
  FORBIDDEN = 'FORBIDDEN',

  // Resource not found (404)
  // NOTE: This code is returned for both "resource doesn't exist"
  // and "user doesn't have access" to prevent enumeration attacks.
  RESOURCE_NOT_FOUND = 'RESOURCE_NOT_FOUND',

  // Validation errors (400)
  INVALID_CONTENT_TYPE = 'INVALID_CONTENT_TYPE',
  MISSING_HEADER = 'MISSING_HEADER',
  INVALID_HEADER = 'INVALID_HEADER',
  LENGTH_REQUIRED = 'LENGTH_REQUIRED',

  // Payload too large (413)
  PAYLOAD_TOO_LARGE = 'PAYLOAD_TOO_LARGE',

  // Server errors (500)
  AUTH_CONFIGURATION_ERROR = 'AUTH_CONFIGURATION_ERROR',
  INTERNAL_SERVER_ERROR = 'INTERNAL_SERVER_ERROR',
}

/**
 * Standard error response format
 * 
 * All API error responses must follow this shape:
 * {
 *   errorCode: string,
 *   statusCode: number
 * }
 * 
 * NO other fields are allowed in error responses.
 * NO verbose messages, hints, or system details.
 */
export interface ErrorResponse {
  readonly errorCode: ErrorCode;
  readonly statusCode: number;
}

/**
 * Helper to create error responses with TypeScript safety
 */
export function createErrorResponse(
  code: ErrorCode,
  statusCode: number,
): ErrorResponse {
  return { errorCode: code, statusCode };
}
```

---

## Step 2: Update Authentication Middleware

**File:** `api-gateway/auth/middleware.ts`

### BEFORE:
```typescript
export function authenticateRequest(
  req: Request,
  res: Response,
  next: NextFunction
): void {
  const authHeader = req.headers.authorization;

  if (!authHeader || !authHeader.startsWith('Bearer ')) {
    res.status(401).json({
      error: 'Unauthorized',
      message: 'Authentication required',  // ← VERBOSE
    });
    return;
  }

  const token = authHeader.substring(7);

  if (!token || token.trim() === '') {
    res.status(401).json({
      error: 'Unauthorized',
      message: 'Invalid authentication token',  // ← VERBOSE
    });
    return;
  }

  const secret = process.env.AUTH_JWT_SECRET;
  if (!secret) {
    res.status(500).json({
      error: 'Internal Server Error',
      message: 'Authentication configuration missing',  // ← VERBOSE
    });
    return;
  }

  try {
    const payload = jwt.verify(token, secret) as TokenPayload;

    if (!payload.sub) {
      res.status(401).json({
        error: 'Unauthorized',
        message: 'Invalid token claims',  // ← VERBOSE
      });
      return;
    }

    (req as AuthenticatedRequest).userId = payload.sub;
    next();
  } catch (error) {
    if (error instanceof jwt.TokenExpiredError) {
      res.status(401).json({
        error: 'Unauthorized',
        message: 'Token expired',  // ← VERBOSE
      });
    } else if (error instanceof jwt.JsonWebTokenError) {
      res.status(401).json({
        error: 'Unauthorized',
        message: 'Invalid token',  // ← VERBOSE
      });
    } else {
      res.status(401).json({
        error: 'Unauthorized',
        message: 'Authentication failed',  // ← VERBOSE
      });
    }
  }
}
```

### AFTER:
```typescript
import { ErrorCode, ErrorResponse } from './types/errors';

export function authenticateRequest(
  req: Request,
  res: Response,
  next: NextFunction
): void {
  const authHeader = req.headers.authorization;

  if (!authHeader || !authHeader.startsWith('Bearer ')) {
    // No verbose message; just opaque error code
    res.status(401).json({
      errorCode: ErrorCode.UNAUTHORIZED,
      statusCode: 401,
    } as ErrorResponse);
    return;
  }

  const token = authHeader.substring(7);

  if (!token || token.trim() === '') {
    res.status(401).json({
      errorCode: ErrorCode.INVALID_TOKEN,
      statusCode: 401,
    } as ErrorResponse);
    return;
  }

  const secret = process.env.AUTH_JWT_SECRET;
  if (!secret) {
    // Log the configuration error server-side only
    console.error('[AUTH] JWT_SECRET not configured');
    
    res.status(500).json({
      errorCode: ErrorCode.AUTH_CONFIGURATION_ERROR,
      statusCode: 500,
    } as ErrorResponse);
    return;
  }

  try {
    const payload = jwt.verify(token, secret) as TokenPayload;

    if (!payload.sub) {
      res.status(401).json({
        errorCode: ErrorCode.INVALID_TOKEN_CLAIMS,
        statusCode: 401,
      } as ErrorResponse);
      return;
    }

    (req as AuthenticatedRequest).userId = payload.sub;
    next();
  } catch (error) {
    // Log the error for debugging, but don't expose details to client
    if (error instanceof jwt.TokenExpiredError) {
      console.debug('[AUTH] Token expired');
    } else if (error instanceof jwt.JsonWebTokenError) {
      console.debug('[AUTH] Token verification failed');
    } else {
      console.error('[AUTH] Unexpected error during token verification', error);
    }
    
    // Return opaque error code for ALL failures
    res.status(401).json({
      errorCode: ErrorCode.UNAUTHORIZED,
      statusCode: 401,
    } as ErrorResponse);
  }
}
```

---

## Step 3: Update Results Route

**File:** `api-gateway/routes/results.ts`

### BEFORE:
```typescript
router.get(
  '/:jobId/results',
  authenticateRequest,
  async (req: Request, res: Response, next: NextFunction) => {
    try {
      const { jobId } = req.params;
      const userId = (req as AuthenticatedRequest).userId as string;

      const job = await jobStore.getJob(jobId);

      if (!job) {
        res.status(404).json({
          error: 'Not Found',
          message: `Job not found: ${jobId}`,  // ← LEAKS: jobId doesn't exist
        });
        return;
      }

      if (job.userId !== userId) {
        res.status(403).json({
          error: 'Forbidden',
          message: 'Access denied to this job',  // ← DIFFERENT ERROR
        });
        return;
      }

      if (job.state !== 'SUCCEEDED') {
        res.status(404).json({
          error: 'Not Found',
          message: 'Results not available; job has not succeeded',  // ← LEAKS STATE
        });
        return;
      }

      res.status(200).json({
        jobId: job.jobId,
        schemaOutput: job.schemaOutput ?? null,
        confidence: job.confidence ?? null,
        qualityScore: job.qualityScore ?? null,
      });
    } catch (error) {
      next(error);
    }
  },
);
```

### AFTER:
```typescript
import { ErrorCode, ErrorResponse } from '../types/errors';

router.get(
  '/:jobId/results',
  authenticateRequest,
  async (req: Request, res: Response, next: NextFunction) => {
    try {
      const { jobId } = req.params;
      const userId = (req as AuthenticatedRequest).userId as string;

      const job = await jobStore.getJob(jobId);

      // Return same error for both "doesn't exist" and "forbidden"
      // This prevents enumeration attacks (attacker can't tell if job exists)
      if (!job || job.userId !== userId) {
        res.status(404).json({
          errorCode: ErrorCode.RESOURCE_NOT_FOUND,
          statusCode: 404,
        } as ErrorResponse);
        return;
      }

      if (job.state !== 'SUCCEEDED') {
        // Same error as above: attacker can't tell if job failed vs succeeded
        res.status(404).json({
          errorCode: ErrorCode.RESOURCE_NOT_FOUND,
          statusCode: 404,
        } as ErrorResponse);
        return;
      }

      res.status(200).json({
        jobId: job.jobId,
        schemaOutput: job.schemaOutput ?? null,
        confidence: job.confidence ?? null,
        qualityScore: job.qualityScore ?? null,
      });
    } catch (error) {
      next(error);
    }
  },
);
```

---

## Step 4: Update Jobs Route

**File:** `api-gateway/routes/jobs.ts`

### BEFORE:
```typescript
router.get(
  '/:jobId',
  authenticateRequest,
  async (req: Request, res: Response, next: NextFunction) => {
    try {
      const { jobId } = req.params;
      const userId = (req as AuthenticatedRequest).userId as string;

      const job = await jobStore.getJob(jobId);

      if (!job) {
        res.status(404).json({
          error: 'Not Found',
          message: `Job not found: ${jobId}`,  // ← LEAKS
        });
        return;
      }

      if (job.userId !== userId) {
        res.status(403).json({
          error: 'Forbidden',
          message: 'Access denied to this job',  // ← DIFFERENT
        });
        return;
      }

      res.status(200).json({
        jobId: job.jobId,
        state: job.state,
        retries: job.retries,
        createdAt: job.createdAt,
        updatedAt: job.updatedAt,
        error: job.errorCode ?? null,
      });
    } catch (error) {
      next(error);
    }
  },
);
```

### AFTER:
```typescript
import { ErrorCode, ErrorResponse } from '../types/errors';

router.get(
  '/:jobId',
  authenticateRequest,
  async (req: Request, res: Response, next: NextFunction) => {
    try {
      const { jobId } = req.params;
      const userId = (req as AuthenticatedRequest).userId as string;

      const job = await jobStore.getJob(jobId);

      if (!job || job.userId !== userId) {
        res.status(404).json({
          errorCode: ErrorCode.RESOURCE_NOT_FOUND,
          statusCode: 404,
        } as ErrorResponse);
        return;
      }

      res.status(200).json({
        jobId: job.jobId,
        state: job.state,
        retries: job.retries,
        createdAt: job.createdAt,
        updatedAt: job.updatedAt,
        error: job.errorCode ?? null,
      });
    } catch (error) {
      next(error);
    }
  },
);
```

---

## Step 5: Update Upload Route

**File:** `api-gateway/routes/upload.ts`

### BEFORE:
```typescript
function validateUploadRequest(
  req: Request,
  res: Response,
  next: NextFunction
): void {
  // Validate Content-Type
  const contentType = req.headers['content-type'];
  if (contentType !== ACCEPTED_CONTENT_TYPE) {
    res.status(400).json({
      error: 'Invalid Content-Type',
      message: `Expected '${ACCEPTED_CONTENT_TYPE}', got '${contentType}'`,  // ← LEAKS
    });
    return;
  }

  // Validate Content-Length
  const contentLength = parseInt(req.headers['content-length'] || '0', 10);
  if (contentLength === 0) {
    res.status(411).json({
      error: 'Length Required',
      message: 'Content-Length header is required',  // ← LEAKS
    });
    return;
  }

  if (contentLength > MAX_UPLOAD_SIZE) {
    res.status(413).json({
      error: 'Payload Too Large',
      message: `Upload exceeds maximum size of ${MAX_UPLOAD_SIZE} bytes`,  // ← LEAKS LIMIT
    });
    return;
  }

  // Validate clientRequestId header
  const clientRequestId = req.headers['x-client-request-id'];
  if (!clientRequestId) {
    res.status(400).json({
      error: 'Missing Header',
      message: 'x-client-request-id header is required',  // ← LEAKS HEADER NAME
    });
    return;
  }

  if (typeof clientRequestId !== 'string' || clientRequestId.trim() === '') {
    res.status(400).json({
      error: 'Invalid Header',
      message: 'x-client-request-id must be a non-empty string',  // ← LEAKS FORMAT
    });
    return;
  }

  next();
}
```

### AFTER:
```typescript
import { ErrorCode, ErrorResponse } from '../types/errors';

function validateUploadRequest(
  req: Request,
  res: Response,
  next: NextFunction
): void {
  // Validate Content-Type
  const contentType = req.headers['content-type'];
  if (contentType !== ACCEPTED_CONTENT_TYPE) {
    res.status(400).json({
      errorCode: ErrorCode.INVALID_CONTENT_TYPE,
      statusCode: 400,
    } as ErrorResponse);
    return;
  }

  // Validate Content-Length
  const contentLength = parseInt(req.headers['content-length'] || '0', 10);
  if (contentLength === 0) {
    res.status(411).json({
      errorCode: ErrorCode.LENGTH_REQUIRED,
      statusCode: 411,
    } as ErrorResponse);
    return;
  }

  if (contentLength > MAX_UPLOAD_SIZE) {
    res.status(413).json({
      errorCode: ErrorCode.PAYLOAD_TOO_LARGE,
      statusCode: 413,
    } as ErrorResponse);
    return;
  }

  // Validate clientRequestId header
  const clientRequestId = req.headers['x-client-request-id'];
  if (!clientRequestId) {
    res.status(400).json({
      errorCode: ErrorCode.MISSING_HEADER,
      statusCode: 400,
    } as ErrorResponse);
    return;
  }

  if (typeof clientRequestId !== 'string' || clientRequestId.trim() === '') {
    res.status(400).json({
      errorCode: ErrorCode.INVALID_HEADER,
      statusCode: 400,
    } as ErrorResponse);
    return;
  }

  next();
}
```

---

## Step 6: Add Test Coverage

**New File:** `api-gateway/routes/__tests__/enumeration-prevention.test.ts`

```typescript
import request from 'supertest';
import { app } from '../../app';
import { jobStore } from '../../../engine/jobs/jobStore';

/**
 * Tests to verify enumeration prevention
 * Attackers should not be able to distinguish between:
 * 1. Invalid jobId (doesn't exist)
 * 2. Valid jobId but access denied
 * 3. Valid jobId but results not ready
 */

describe('Enumeration Prevention', () => {
  const authToken = 'Bearer valid-jwt-token'; // Mock JWT
  const userId = 'user-123';
  const otherUserId = 'user-456';

  beforeEach(() => {
    jobStore.clear();
  });

  describe('Invalid jobId vs Forbidden jobId', () => {
    it('should return SAME error for invalid and forbidden jobIds', async () => {
      // Create a job for other user
      const job = await jobStore.createJob({
        blobId: 'blob-123',
        userId: otherUserId,
        clientRequestId: 'req-123',
      });
      const otherUsersJobId = job.jobId;

      // Test 1: Request invalid jobId
      const invalidResponse = await request(app)
        .get(`/api/v1/jobs/invalid-uuid`)
        .set('Authorization', authToken)
        .expect(404);

      // Test 2: Request other user's jobId
      const forbiddenResponse = await request(app)
        .get(`/api/v1/jobs/${otherUsersJobId}`)
        .set('Authorization', authToken)
        .expect(404); // Should ALSO be 404, not 403

      // Critical: Both should have same error code
      expect(invalidResponse.body.errorCode).toBe(forbiddenResponse.body.errorCode);
      expect(invalidResponse.body.errorCode).toBe('RESOURCE_NOT_FOUND');

      // Critical: Should NOT have any message
      expect(invalidResponse.body).not.toHaveProperty('message');
      expect(forbiddenResponse.body).not.toHaveProperty('message');

      // Critical: Should NOT leak jobId in any form
      expect(JSON.stringify(invalidResponse.body)).not.toContain('invalid-uuid');
      expect(JSON.stringify(forbiddenResponse.body)).not.toContain(otherUsersJobId);
    });
  });

  describe('Results endpoint enumeration prevention', () => {
    it('should return SAME error for invalid jobId and non-SUCCEEDED job', async () => {
      // Create a job in QUEUED state
      const job = await jobStore.createJob({
        blobId: 'blob-123',
        userId,
        clientRequestId: 'req-123',
      });
      
      // Job starts in CREATED, move to QUEUED
      await jobStore.updateJobState(job.jobId, 'QUEUED');

      // Test 1: Request results for invalid jobId
      const invalidResponse = await request(app)
        .get(`/api/v1/jobs/invalid-uuid/results`)
        .set('Authorization', authToken)
        .expect(404);

      // Test 2: Request results for QUEUED job (not SUCCEEDED)
      const notReadyResponse = await request(app)
        .get(`/api/v1/jobs/${job.jobId}/results`)
        .set('Authorization', authToken)
        .expect(404);

      // Critical: Both should return identical error
      expect(invalidResponse.body.errorCode).toBe(notReadyResponse.body.errorCode);
      expect(invalidResponse.body.errorCode).toBe('RESOURCE_NOT_FOUND');

      // Critical: No verbose messages
      expect(invalidResponse.body).not.toHaveProperty('message');
      expect(notReadyResponse.body).not.toHaveProperty('message');
    });
  });

  describe('Error response schema consistency', () => {
    it('should only include errorCode and statusCode in error responses', async () => {
      const response = await request(app)
        .get(`/api/v1/jobs/invalid-uuid`)
        .set('Authorization', 'Bearer invalid-token')
        .expect(401);

      // Only these two fields allowed
      const keys = Object.keys(response.body);
      expect(keys).toEqual(['errorCode', 'statusCode']);

      // No other fields
      expect(response.body).not.toHaveProperty('message');
      expect(response.body).not.toHaveProperty('error');
      expect(response.body).not.toHaveProperty('details');
      expect(response.body).not.toHaveProperty('hint');
    });

    it('should use opaque error codes, not verbose messages', async () => {
      const response = await request(app)
        .post('/api/v1/upload')
        .set('Content-Type', 'application/json') // Wrong type
        .set('Authorization', authToken)
        .expect(400);

      // Should be opaque code
      expect(response.body.errorCode).toBe('INVALID_CONTENT_TYPE');

      // Should NOT be verbose message
      expect(response.body.errorCode).not.toContain('Expected');
      expect(response.body.errorCode).not.toContain('application/octet-stream');
    });
  });

  describe('Upload validation errors use opaque codes', () => {
    it('should not leak upload size limit', async () => {
      const response = await request(app)
        .post('/api/v1/upload')
        .set('Authorization', authToken)
        .set('Content-Type', 'application/octet-stream')
        .set('Content-Length', '999999999999')
        .expect(413);

      // Should NOT include the actual limit
      expect(JSON.stringify(response.body)).not.toContain('104857600');
      expect(JSON.stringify(response.body)).not.toContain('100 MB');

      // Should use opaque code
      expect(response.body.errorCode).toBe('PAYLOAD_TOO_LARGE');
    });

    it('should not leak required header names', async () => {
      const response = await request(app)
        .post('/api/v1/upload')
        .set('Authorization', authToken)
        .set('Content-Type', 'application/octet-stream')
        .set('Content-Length', '100')
        .expect(400);

      // Should NOT mention 'x-client-request-id' by name
      expect(JSON.stringify(response.body)).not.toContain('x-client-request-id');
      expect(JSON.stringify(response.body)).not.toContain('clientRequestId');

      // Should use opaque code
      expect(response.body.errorCode).toBe('MISSING_HEADER');
    });
  });
});
```

---

## Step 7: Update package.json (if needed)

Ensure types are properly exported from the new error file:

```json
{
  "exports": {
    "./types/errors": "./dist/api-gateway/types/errors.js"
  }
}
```

---

## Testing Checklist

After applying these fixes:

- [ ] Run unit tests: `npm test`
- [ ] Run enumeration prevention tests specifically
- [ ] Verify all error responses follow `{ errorCode, statusCode }` format
- [ ] Verify no verbose messages in error responses
- [ ] Verify all routes return 404 for both "invalid jobId" and "forbidden jobId"
- [ ] Verify TypeScript compilation succeeds
- [ ] Verify no console.error/log statements expose sensitive details
- [ ] Run security linter if available

---

## Implementation Time Estimate

| Task | Time |
|------|------|
| Create error types file | 30 min |
| Update auth middleware | 45 min |
| Update results route | 30 min |
| Update jobs route | 30 min |
| Update upload route | 45 min |
| Add test coverage | 90 min |
| Testing & verification | 60 min |
| **Total** | **~5 hours** |

---

## Verification

After implementation, verify:

```bash
# 1. No verbose error messages
grep -r "message.*\$\|message.*\`" api-gateway/routes/*.ts
# Should return: nothing (all message fields removed)

# 2. All errors use ErrorCode enum
grep -r "res.status.*json" api-gateway/routes/*.ts
# Should all reference ErrorCode

# 3. Tests pass
npm test -- enumeration-prevention.test.ts
# Should pass all tests

# 4. TypeScript compilation
npx tsc --noEmit
# Should compile without errors
```

---

## Rollback Plan

If issues arise after deployment:

1. Revert error response changes (git revert)
2. Restore verbose messages temporarily
3. Debug and fix issues
4. Re-implement with fixes

However, this is a **low-risk change** that only:
- Removes verbose information (not adds it)
- Unifies error responses (makes logic simpler)
- Adds type safety (improves code quality)

---

## Questions?

Refer to the main findings documents:
- [RED_TEAM_OUTPUT_DELIVERY_API_QUICK_REFERENCE.md](RED_TEAM_OUTPUT_DELIVERY_API_QUICK_REFERENCE.md)
- [RED_TEAM_OUTPUT_DELIVERY_API_FINDINGS.md](RED_TEAM_OUTPUT_DELIVERY_API_FINDINGS.md)
- [RED_TEAM_OUTPUT_DELIVERY_API_REVIEW.md](RED_TEAM_OUTPUT_DELIVERY_API_REVIEW.md)
