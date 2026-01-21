# Red Team Output Delivery API - Findings Catalog

**Date:** 5 January 2026

---

## Finding 1: Job Enumeration via Error Message Differentiation

**Severity:** BLOCKER  
**Category:** Information Disclosure  
**CWE:** CWE-204 (Observable Discrepancy)

### Description
The API returns different error messages for "job doesn't exist" vs "job exists but user can't access", enabling attackers to enumerate valid jobIds without authorization.

### Attack Scenario
```
User A discovers User B's jobId by probing the endpoint:

GET /api/v1/jobs/INVALID-UUID/results
→ 404 { error: "Not Found", message: "Job not found: INVALID-UUID" }

GET /api/v1/jobs/EXISTING-UUID/results  
→ 403 { error: "Forbidden", message: "Access denied to this job" }

Inference: EXISTING-UUID belongs to User B
```

### Evidence

**File:** [api-gateway/routes/results.ts](api-gateway/routes/results.ts#L18-L29)

```typescript
const job = await jobStore.getJob(jobId);

if (!job) {
  res.status(404).json({
    error: 'Not Found',
    message: `Job not found: ${jobId}`,  // ← RETURNS DIFFERENT ERROR
  });
  return;
}

if (job.userId !== userId) {
  res.status(403).json({
    error: 'Forbidden',
    message: 'Access denied to this job',  // ← FROM THIS
  });
  return;
}
```

**Same issue in:** [api-gateway/routes/jobs.ts](api-gateway/routes/jobs.ts#L18-L29)

### Root Cause
The endpoint checks existence and authorization separately, revealing both states through error messages.

### Remediation

**Option 1 (Recommended): Unified Error Response**
```typescript
const job = await jobStore.getJob(jobId);

if (!job || job.userId !== userId) {
  res.status(404).json({
    errorCode: 'RESOURCE_NOT_FOUND',
    statusCode: 404,
  });
  return;
}
```

**Option 2: Return 403 for Both**
```typescript
const job = await jobStore.getJob(jobId);
if (!job) {
  res.status(403).json({
    errorCode: 'FORBIDDEN',
    statusCode: 403,
  });
  return;
}
if (job.userId !== userId) {
  res.status(403).json({
    errorCode: 'FORBIDDEN',
    statusCode: 403,
  });
  return;
}
```

### Affected Endpoints
- GET /api/v1/jobs/:jobId
- GET /api/v1/jobs/:jobId/results

### Impact
- Attackers can enumerate valid jobIds by probing error messages
- Timing attacks become possible (different execution paths)
- Violates zero-knowledge principle (information disclosure via side-channels)

---

## Finding 2: Job State Information Leakage in Error Messages

**Severity:** BLOCKER  
**Category:** Information Disclosure  
**CWE:** CWE-215 (Information Exposure Through Debug Information)

### Description
When results are not yet available, the error message reveals the job exists and is not in SUCCEEDED state, leaking processing progress information.

### Attack Scenario
```
Attacker polls job results endpoint:

GET /api/v1/jobs/{jobId}/results
→ 404 { message: "Results not available; job has not succeeded" }

Inference: 
- Job exists
- Job is not in SUCCEEDED state
- Combined with job status endpoint, attacker learns exact state
```

### Evidence

**File:** [api-gateway/routes/results.ts](api-gateway/routes/results.ts#L35-L39)

```typescript
if (job.state !== 'SUCCEEDED') {
  res.status(404).json({
    error: 'Not Found',
    message: 'Results not available; job has not succeeded',  // ← LEAKS STATE
  });
  return;
}
```

### Combined Attack Using Job Status Endpoint

**File:** [api-gateway/routes/jobs.ts](api-gateway/routes/jobs.ts#L34-L40)

```typescript
res.status(200).json({
  jobId: job.jobId,
  state: job.state,  // ← EXACT STATE EXPOSED
  retries: job.retries,
  createdAt: job.createdAt,
  updatedAt: job.updatedAt,
  error: job.errorCode ?? null,
});
```

**Sequence:**
```
1. Poll GET /api/v1/jobs/{jobId} → state: "RUNNING", retries: 0
2. Poll GET /api/v1/jobs/{jobId}/results → "job has not succeeded"
3. Poll GET /api/v1/jobs/{jobId} → state: "RETRYING", retries: 1
4. Poll GET /api/v1/jobs/{jobId}/results → "job has not succeeded"
5. Poll GET /api/v1/jobs/{jobId} → state: "SUCCEEDED", retries: 1
6. Poll GET /api/v1/jobs/{jobId}/results → 200 { schemaOutput: {...} }

Attacker now knows:
- Job was retried once
- Processing took N seconds
- Processing succeeded on second attempt
```

### Root Cause
Error message uses human-readable state description instead of opaque error code.

### Remediation

```typescript
// Before
if (job.state !== 'SUCCEEDED') {
  res.status(404).json({
    error: 'Not Found',
    message: 'Results not available; job has not succeeded',
  });
  return;
}

// After
if (job.state !== 'SUCCEEDED') {
  res.status(404).json({
    errorCode: 'RESOURCE_NOT_FOUND',
    statusCode: 404,
  });
  return;
}
```

### Affected Endpoints
- GET /api/v1/jobs/:jobId/results

### Impact
- Attacker can infer job state without direct access
- Timing information reveals processing duration
- Combined with other endpoints, enables side-channel inference

---

## Finding 3: Verbose Validation Error Messages Leak API Details

**Severity:** BLOCKER  
**Category:** Information Disclosure  
**CWE:** CWE-209 (Information Exposure Through an Error Message)

### Description
Upload validation errors include actual values and limits, enabling attackers to fingerprint the API and discover system constraints.

### Attack Scenario
```
Attacker probes upload endpoint:

POST /api/v1/upload
Content-Type: application/json
→ 400 { message: "Expected 'application/octet-stream', got 'application/json'" }

Inference:
- API accepts application/octet-stream
- API rejects application/json
- Attacker maps all supported content types

---

POST /api/v1/upload
Content-Length: 200000000000
→ 413 { message: "Upload exceeds maximum size of 104857600 bytes" }

Inference:
- Maximum upload size is 100 MB
- API uses exact size checking
```

### Evidence

**File:** [api-gateway/routes/upload.ts](api-gateway/routes/upload.ts#L83-L124)

```typescript
// Line 85-87: Leaks accepted content type
const contentType = req.headers['content-type'];
if (contentType !== ACCEPTED_CONTENT_TYPE) {
  res.status(400).json({
    error: 'Invalid Content-Type',
    message: `Expected '${ACCEPTED_CONTENT_TYPE}', got '${contentType}'`,  // ← LEAKS BOTH
  });
  return;
}

// Line 103-106: Leaks upload size limit
if (contentLength > MAX_UPLOAD_SIZE) {
  res.status(413).json({
    error: 'Payload Too Large',
    message: `Upload exceeds maximum size of ${MAX_UPLOAD_SIZE} bytes`,  // ← LEAKS LIMIT
  });
  return;
}

// Line 113-119: Leaks header name and format requirements
const clientRequestId = req.headers['x-client-request-id'];
if (!clientRequestId) {
  res.status(400).json({
    error: 'Missing Header',
    message: 'x-client-request-id header is required',  // ← LEAKS HEADER NAME
  });
  return;
}
```

### Leaked Information

| Error Message | Leaked Information |
|---------------|-------------------|
| `Expected 'application/octet-stream', got '...'` | Content-Type whitelist |
| `Upload exceeds maximum size of 104857600 bytes` | Exact size limit (100 MB) |
| `x-client-request-id header is required` | Header name and requirement |
| `Content-Length header is required` | Protocol requirements |

### Root Cause
Error messages use parameterized strings with actual values instead of constants.

### Remediation

```typescript
// Before
res.status(400).json({
  error: 'Invalid Content-Type',
  message: `Expected '${ACCEPTED_CONTENT_TYPE}', got '${contentType}'`,
});

// After
res.status(400).json({
  errorCode: 'INVALID_CONTENT_TYPE',
  statusCode: 400,
});
```

### Affected Endpoints
- POST /api/v1/upload

### Impact
- Attackers fingerprint API implementation
- Discover system limits (enables DoS optimization)
- Identify supported protocols and formats
- Violates API opacity principle

---

## Finding 4: Inconsistent Error Response Schema

**Severity:** BLOCKER  
**Category:** API Design  
**CWE:** CWE-1104 (Use of Unmaintained Third Party Components)

### Description
Error responses lack standardized structure across endpoints, with no opaque error code field required by security design.

### Current Error Formats

**Format 1: Authentication/Authorization Errors**
```typescript
res.status(401).json({
  error: 'Unauthorized',
  message: 'Authentication required',
});
```

**Format 2: Validation Errors**
```typescript
res.status(400).json({
  error: 'Invalid Content-Type',
  message: `Expected '${ACCEPTED_CONTENT_TYPE}', got '${contentType}'`,
});
```

**Format 3: Not Found Errors**
```typescript
res.status(404).json({
  error: 'Not Found',
  message: `Job not found: ${jobId}`,
});
```

### Missing Components
1. ❌ No opaque error code (system cannot differentiate errors programmatically)
2. ❌ Verbose messages (violates opacity requirement)
3. ❌ Inconsistent field names across endpoints
4. ❌ No type safety in responses

### Remediation

**Step 1: Define Error Code Enum**

Create [api-gateway/types/errors.ts](api-gateway/types/errors.ts):

```typescript
export enum ErrorCode {
  // Authentication
  UNAUTHORIZED = 'UNAUTHORIZED',
  TOKEN_EXPIRED = 'TOKEN_EXPIRED',
  INVALID_TOKEN = 'INVALID_TOKEN',
  
  // Authorization
  FORBIDDEN = 'FORBIDDEN',
  
  // Not Found
  RESOURCE_NOT_FOUND = 'RESOURCE_NOT_FOUND',
  
  // Validation
  INVALID_CONTENT_TYPE = 'INVALID_CONTENT_TYPE',
  MISSING_HEADER = 'MISSING_HEADER',
  INVALID_HEADER = 'INVALID_HEADER',
  PAYLOAD_TOO_LARGE = 'PAYLOAD_TOO_LARGE',
  LENGTH_REQUIRED = 'LENGTH_REQUIRED',
  
  // Server Errors
  INTERNAL_SERVER_ERROR = 'INTERNAL_SERVER_ERROR',
}

export interface ErrorResponse {
  errorCode: ErrorCode;
  statusCode: number;
}

export function createErrorResponse(
  code: ErrorCode,
  statusCode: number
): ErrorResponse {
  return { errorCode: code, statusCode };
}
```

**Step 2: Update All Endpoints**

```typescript
// Before
res.status(401).json({
  error: 'Unauthorized',
  message: 'Authentication required',
});

// After
res.status(401).json({
  errorCode: ErrorCode.UNAUTHORIZED,
  statusCode: 401,
});
```

### Affected Files
- [api-gateway/auth/middleware.ts](api-gateway/auth/middleware.ts)
- [api-gateway/routes/upload.ts](api-gateway/routes/upload.ts)
- [api-gateway/routes/jobs.ts](api-gateway/routes/jobs.ts)
- [api-gateway/routes/results.ts](api-gateway/routes/results.ts)

### Impact
- Unclear error semantics across endpoints
- Clients cannot programmatically distinguish error types
- Makes testing difficult (depends on string matching)
- Violates opaque error code requirement

---

## Finding 5: State Names Expose Internal Processing Details

**Severity:** ACCEPTABLE WITH NOTES  
**Category:** API Design  
**CWE:** CWE-215 (Information Exposure Through Debug Information)

### Description
Job status endpoint exposes internal state names (CREATED, QUEUED, RUNNING, RETRYING, SUCCEEDED, FAILED) that reveal processing pipeline structure.

### Evidence

**File:** [api-gateway/routes/jobs.ts](api-gateway/routes/jobs.ts#L34-L40)

```typescript
res.status(200).json({
  jobId: job.jobId,
  state: job.state,  // ← EXPOSES: CREATED, QUEUED, RUNNING, RETRYING, SUCCEEDED, FAILED
  retries: job.retries,
  createdAt: job.createdAt,
  updatedAt: job.updatedAt,
  error: job.errorCode ?? null,
});
```

### Information Revealed

| State | What Attacker Learns |
|-------|---------------------|
| CREATED | Job accepted but not queued |
| QUEUED | Job waiting for processing |
| RUNNING | Job actively processing |
| RETRYING | Job failed and scheduled for retry |
| SUCCEEDED | Job completed successfully |
| FAILED | Job failed permanently |

### Inference Attacks

**Attack 1: Processing Performance**
```
GET /api/v1/jobs/{jobId} @ T0 → state: RUNNING
GET /api/v1/jobs/{jobId} @ T1 → state: SUCCEEDED

Processing time = T1 - T0
Attacker can measure document processing duration
```

**Attack 2: Failure Pattern Discovery**
```
GET /api/v1/jobs/{jobId} → state: RETRYING, retries: 1
GET /api/v1/jobs/{jobId} → state: RETRYING, retries: 2
GET /api/v1/jobs/{jobId} → state: FAILED

Inference: Document failed twice, then gave up
Attacker learns retry policy (max 2 retries, then fail)
```

### Mitigation Options

**Option 1: Abstract State Names (Recommended)**
```typescript
// Map internal states to user-facing states
type UserFacingState = 'processing' | 'completed' | 'failed';

function mapInternalToUserFacing(internalState: JobState): UserFacingState {
  switch (internalState) {
    case 'CREATED':
    case 'QUEUED':
    case 'RUNNING':
    case 'RETRYING':
      return 'processing';
    case 'SUCCEEDED':
      return 'completed';
    case 'FAILED':
      return 'failed';
  }
}

res.status(200).json({
  jobId: job.jobId,
  state: mapInternalToUserFacing(job.state),  // Returns 'processing', 'completed', 'failed'
  ...
});
```

**Option 2: Accept as Acceptable**
- States are only visible to job owner (scoped to authenticated user)
- Timing information is already exposed via timestamps
- Frontend needs to know processing vs completed for UI
- Note as design trade-off in architecture documentation

### Affected Endpoints
- GET /api/v1/jobs/:jobId

### Impact
- Attackers can measure processing performance
- Retry patterns reveal failure handling strategy
- Combined with other endpoints, enables system fingerprinting
- **Note:** Only impacts authenticated users (scoped to own jobs)

### Recommendation
**DEFER** – Not a blocker since information is user-scoped, but consider state abstraction for better privacy posture.

---

## Finding 6: Retry Count Exposure

**Severity:** ACCEPTABLE WITH NOTES  
**Category:** API Design

### Description
Job status endpoint exposes retry count, revealing failure history and retry policy.

### Evidence

**File:** [api-gateway/routes/jobs.ts](api-gateway/routes/jobs.ts#L36)

```typescript
res.status(200).json({
  ...
  retries: job.retries,  // ← EXPOSES: "Retried 2 times"
  ...
});
```

### Information Revealed

```
retries: 0 → Job succeeded on first attempt
retries: 1 → Job failed once, succeeded on second attempt  
retries: 2 → Job failed twice, succeeded on third attempt
retries: 3 → Job max retries reached (system retry policy inferred)
```

### Inference Attack

**Retry Policy Discovery:**
```
Sample 100 documents with retries: [0, 0, 1, 1, 1, 0, 2, 1, 0, 1, ...]

Average retries: 1.2
Max observed: 2

Inference: System retries up to 3 times (max observed + 1)
Attacker learns retry policy without access to source code
```

### Mitigation

**Option 1: Omit Retry Count**
```typescript
res.status(200).json({
  jobId: job.jobId,
  state: job.state,
  // Removed: retries,
  createdAt: job.createdAt,
  updatedAt: job.updatedAt,
  error: job.errorCode ?? null,
});
```

**Option 2: Accept as Acceptable**
- Information scoped to job owner (user-authenticated)
- Retry count useful for UI transparency (why is this taking long?)
- Not sensitive if tied to authenticated user's own jobs

### Affected Endpoints
- GET /api/v1/jobs/:jobId

### Recommendation
**DEFER** – Acceptable since information is user-scoped, but consider omitting for minimal information disclosure.

---

## Summary of Findings

| # | Issue | Severity | Status | File |
|---|-------|----------|--------|------|
| 1 | Job enumeration via error messages | BLOCKER | Must fix | results.ts, jobs.ts |
| 2 | Job state leakage in error messages | BLOCKER | Must fix | results.ts |
| 3 | Verbose validation error messages | BLOCKER | Must fix | upload.ts |
| 4 | Inconsistent error response schema | BLOCKER | Must fix | All routes |
| 5 | State names expose internal details | ACCEPTABLE | Defer | jobs.ts |
| 6 | Retry count exposure | ACCEPTABLE | Defer | jobs.ts |

---

## Implementation Checklist

- [ ] Add `ErrorCode` enum to [api-gateway/types/errors.ts](api-gateway/types/errors.ts)
- [ ] Update [api-gateway/auth/middleware.ts](api-gateway/auth/middleware.ts) error responses
- [ ] Update [api-gateway/routes/upload.ts](api-gateway/routes/upload.ts) error responses
- [ ] Update [api-gateway/routes/jobs.ts](api-gateway/routes/jobs.ts) error responses
- [ ] Update [api-gateway/routes/results.ts](api-gateway/routes/results.ts) error responses
- [ ] Add integration tests for enumeration prevention
- [ ] Verify no verbose messages in production build
- [ ] Document API error codes in OpenAPI/Swagger spec
- [ ] Add TypeScript type guards for error responses

---

## References

- Full Review: [RED_TEAM_OUTPUT_DELIVERY_API_REVIEW.md](RED_TEAM_OUTPUT_DELIVERY_API_REVIEW.md)
- Quick Reference: [RED_TEAM_OUTPUT_DELIVERY_API_QUICK_REFERENCE.md](RED_TEAM_OUTPUT_DELIVERY_API_QUICK_REFERENCE.md)
- Threat Model: [security/threat-model.md](security/threat-model.md)
