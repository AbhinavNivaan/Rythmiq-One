# Red Team Review: Output Delivery API & Artifact Storage

**Date:** 5 January 2026  
**Phase:** Backend Delivery Security Review  
**Status:** Complete  
**Reviewed By:** Red Team Security Lead

---

## Executive Summary

The output delivery API implements **strong state-based access controls** with enforced per-user authorization and strict result availability gating. However, **critical information disclosure risks remain unmitigated** in error responses and response shapes. The system demonstrates good architectural hygiene but violates security principles through verbose error handling and insufficient redaction of internal implementation details.

**Critical Classification:**
- ✅ State-based result gating: **PROPERLY ENFORCED**
- ✅ Per-user authorization: **PROPERLY ENFORCED**
- ✅ Authentication: **PROPERLY ENFORCED**
- ❌ Error response redaction: **BLOCKER** (verbose error messages leak system state)
- ❌ Response shape stability: **BLOCKER** (internal fields exposed; inconsistent error handling)

---

## 1. Results Access Control (Requirement 1)

### Finding: State-Based Gating is Properly Enforced ✅

**File:** [api-gateway/routes/results.ts](api-gateway/routes/results.ts)

The results endpoint enforces strict state validation:

```typescript
if (job.state !== 'SUCCEEDED') {
  res.status(404).json({
    error: 'Not Found',
    message: 'Results not available; job has not succeeded',
  });
  return;
}
```

**Verification:**
1. Results are **only accessible when `job.state === 'SUCCEEDED'`** ✓
2. All other states (CREATED, QUEUED, RUNNING, RETRYING, FAILED) return 404 ✓
3. State validation occurs **before response serialization** ✓
4. State machine in [engine/jobs/stateMachine.ts](engine/jobs/stateMachine.ts) enforces terminal state immutability ✓

**Terminal States:** SUCCEEDED and FAILED are immutable; no transitions possible from these states.

**Architecture Quality:** Excellent. The check is simple, early in the request lifecycle, and uses status code semantics correctly (404 indicates "not available" per HTTP spec).

**Classification:** ✅ **ACCEPTABLE** – Properly enforced, no bypass paths identified.

---

## 2. Authentication & Per-User Authorization (Requirement 2)

### Finding: Enforcement is Properly Layered ✅

**File:** [api-gateway/auth/middleware.ts](api-gateway/auth/middleware.ts)

#### Authentication Layer (Strong)

1. **Bearer Token Validation:**
   - Enforces `Authorization: Bearer <token>` format
   - Validates token structure and presence
   - Uses JWT verification with `process.env.AUTH_JWT_SECRET`
   - Handles `TokenExpiredError`, `JsonWebTokenError` separately
   - Returns 401 on any failure (no false passes)

2. **Token Payload Extraction:**
   - Extracts `sub` claim (subject/userId) from JWT
   - Validates `sub` is present (rejects tokens without subject)
   - Attaches to `AuthenticatedRequest.userId` for downstream use

**Verification:** Authentication middleware is applied **before all routes:**
- ✓ Upload route: `authenticateRequest` applied
- ✓ Jobs route: `authenticateRequest` applied  
- ✓ Results route: `authenticateRequest` applied

#### Per-User Authorization (Strong)

**File:** [api-gateway/routes/results.ts](api-gateway/routes/results.ts#L15-L28) and [api-gateway/routes/jobs.ts](api-gateway/routes/jobs.ts#L15-L28)

Both endpoints enforce user isolation:

```typescript
const userId = (req as AuthenticatedRequest).userId as string;
const job = await jobStore.getJob(jobId);

if (job.userId !== userId) {
  res.status(403).json({
    error: 'Forbidden',
    message: 'Access denied to this job',
  });
  return;
}
```

**Verification:**
1. ✓ Authenticated `userId` extracted from token
2. ✓ Job retrieved from storage
3. ✓ Job ownership (`job.userId`) checked against authenticated user
4. ✓ 403 Forbidden returned immediately on mismatch
5. ✓ No data leaked before check (job details not included in error)

**Cross-User Attack Surface:**
- Cannot access another user's jobs: ✓ Checked before any data exposure
- Cannot modify another user's jobs: ✓ Only GET endpoints exposed in current API
- Cannot guess jobIds to access data: ✓ Requires valid JWT token AND ownership match

**Idempotency Layer Verification:**

The system uses `(userId, clientRequestId)` tuples for idempotent uploads:
- [api-gateway/storage.ts](api-gateway/storage.ts#L26-L28): Idempotency key includes both `userId` and `clientRequestId`
- [engine/jobs/jobStore.ts](engine/jobs/jobStore.ts#L55-L56): Job creation uses same tuple

**Result:** Different users cannot collide on idempotency keys (tuples are user-specific).

**Classification:** ✅ **ACCEPTABLE** – Authorization is properly enforced at multiple layers with correct HTTP semantics.

---

## 3. Information Disclosure: Plaintext OCR Text & Internal Paths (Requirement 3)

### Finding 3A: OCR Text Not Exposed in Results ✅

**File:** [api-gateway/routes/results.ts](api-gateway/routes/results.ts#L40-L46)

Results response returns only sanitized fields:

```typescript
res.status(200).json({
  jobId: job.jobId,
  schemaOutput: job.schemaOutput ?? null,
  confidence: job.confidence ?? null,
  qualityScore: job.qualityScore ?? null,
});
```

**Verification:**
- ✓ **No plaintext OCR text** in response (not included in Job interface)
- ✓ Only structured schema output returned
- ✓ No raw document content
- ✓ No file paths or blob identifiers

**Design Quality:** Excellent. The response schema explicitly omits dangerous fields (`blobId`, `ocrArtifactId`, `schemaArtifactId`, `errorCode` is not included in success response).

**Classification:** ✅ **ACCEPTABLE** – No plaintext OCR or internal identifiers exposed.

### Finding 3B: CRITICAL ISSUE - Error Responses Leak System State ❌ **BLOCKER**

**File:** [api-gateway/routes/results.ts](api-gateway/routes/results.ts), [api-gateway/routes/jobs.ts](api-gateway/routes/jobs.ts)

#### Issue 1: Verbose Error Messages Leak Job Not-Found Status

**Current behavior:**
```typescript
// Line 19 in results.ts
res.status(404).json({
  error: 'Not Found',
  message: `Job not found: ${jobId}`,  // ← LEAKS: jobId was invalid OR doesn't exist
});
```

**Attack:** Enumerate jobIds to fingerprint which ones exist:
```
GET /jobs/550e8400-e29b-41d4-a716-446655440000/results
→ 404 { error: "Not Found", message: "Job not found: ..." }
  (Attacker: "This UUID doesn't exist in system")

GET /jobs/550e8400-e29b-41d4-a716-446655440001/results
→ 403 { error: "Forbidden", message: "Access denied to this job" }
  (Attacker: "This UUID EXISTS and belongs to someone else")
```

**Same issue appears in** [api-gateway/routes/jobs.ts](api-gateway/routes/jobs.ts#L19-L22).

#### Issue 2: State Information Leak in Results 404

**Current behavior:**
```typescript
// Line 35 in results.ts
if (job.state !== 'SUCCEEDED') {
  res.status(404).json({
    error: 'Not Found',
    message: 'Results not available; job has not succeeded',  // ← LEAKS: job exists + state != SUCCEEDED
  });
  return;
}
```

**Information leaked:** Attacker learns:
- Job exists and belongs to you (authentication passed)
- Job has not reached terminal SUCCEEDED state
- Job may be in QUEUED, RUNNING, RETRYING, CREATED, or FAILED states

**Combined with job status endpoint** [api-gateway/routes/jobs.ts](api-gateway/routes/jobs.ts#L34-L40):
```typescript
res.status(200).json({
  jobId: job.jobId,
  state: job.state,  // ← EXPOSES STATE
  retries: job.retries,
  createdAt: job.createdAt,
  updatedAt: job.updatedAt,
  error: job.errorCode ?? null,
});
```

**Risk:** Attacker can probe job state and error codes to understand processing details and potential failure modes.

#### Issue 3: No Consistent Error Code Strategy

**Current behavior:**
- Authentication errors: Use string literals (`'Unauthorized'`, `'Invalid token'`)
- Authorization errors: Use string literals (`'Forbidden'`)
- Not-found errors: Mix string literals with verbose messages

**Missing:** Opaque error codes that clients cannot use for timing attacks or system fingerprinting.

### Finding 3C: Internal Artifact Identifiers Not Exposed ✅

**File:** [engine/jobs/jobStore.ts](engine/jobs/jobStore.ts#L12-L16)

Job interface contains but **does not expose** in API response:
```typescript
ocrArtifactId?: string;
schemaArtifactId?: string;
```

Results endpoint explicitly omits these fields. ✓ Good.

**Classification:**
- ❌ **BLOCKER** – Error responses leak system state, enabling enumeration and side-channel attacks
- ❌ **BLOCKER** – Inconsistent error handling across endpoints
- ✅ **ACCEPTABLE** – Internal identifiers not exposed in success responses

---

## 4. Error Response Opacity (Requirement 4)

### Finding: Verbose Error Messages Enable Fingerprinting ❌ **BLOCKER**

**Evidence across all routes:**

| Endpoint | Error Type | Message | Issue |
|----------|-----------|---------|-------|
| POST /upload | 400 | `Expected '${ACCEPTED_CONTENT_TYPE}', got '${contentType}'` | Leaks supported content types |
| POST /upload | 411 | `Content-Length header is required` | Leaks protocol requirements |
| POST /upload | 413 | `Upload exceeds maximum size of ${MAX_UPLOAD_SIZE} bytes` | Leaks upload limits |
| POST /upload | 400 | `x-client-request-id header is required` | Leaks header names |
| GET /:jobId | 404 | `Job not found: ${jobId}` | Timing/enumeration attacks |
| GET /:jobId | 404 | `Job has not succeeded` | State inference |
| GET /:jobId/results | 404 | `Job not found: ${jobId}` | Timing/enumeration attacks |
| GET /:jobId/results | 404 | `Job has not succeeded` | State inference |

**Result:** These messages enable:
1. **API fingerprinting** – Attacker learns exact validation rules
2. **Enumeration attacks** – Attacker discovers which jobIds exist via timing/404 patterns
3. **State inference** – Attacker probes job states without direct access
4. **Limit discovery** – Attacker learns upload size limits, content types, etc.

**Comparison to Requirement 4:**
> "Error responses use opaque error codes only"

**Current state:** ❌ Requirement violated. Error responses use **verbose messages** instead of opaque codes.

### Example Attack: jobId Enumeration

```
# Attacker generates UUIDs systematically
for jobId in <generated_list>:
  response = GET /api/v1/jobs/{jobId}/results
  
  if response.status == 404:
    if "Job not found" in response.message:
      # Invalid UUID or deleted
      record(invalid)
    elif "Job has not succeeded" in response.message:
      # Job exists, user has access, state != SUCCEEDED
      record(owned_job_pending)
  elif response.status == 403:
    # Job exists, user does NOT have access (belongs to someone else)
    record(other_user_job)
  elif response.status == 200:
    # Job succeeded and user has access
    record(owned_job_completed)
```

**Classification:** ❌ **BLOCKER** – Error responses must use opaque error codes, not verbose messages.

---

## 5. Response Shape Stability (Requirement 5)

### Finding 5A: Success Response Shapes are Appropriate ✅

#### Upload Response
**File:** [api-gateway/routes/upload.ts](api-gateway/routes/upload.ts#L53-L58)

```typescript
res.status(storageResult.isNewUpload ? 201 : 200).json({
  blobId: storageResult.blobId,
  jobId: jobResult.jobId,
  clientRequestId,
  uploadedBytes: payloadBuffer.length,
});
```

**Evaluation:**
- ✓ Stable field names (no internal details)
- ✓ HTTP semantics correct (201 for new, 200 for idempotent replay)
- ✓ No implementation leakage
- ✓ Suitable for UI: jobId can be used to poll status

#### Job Status Response
**File:** [api-gateway/routes/jobs.ts](api-gateway/routes/jobs.ts#L34-L40)

```typescript
res.status(200).json({
  jobId: job.jobId,
  state: job.state,
  retries: job.retries,
  createdAt: job.createdAt,
  updatedAt: job.updatedAt,
  error: job.errorCode ?? null,
});
```

**Evaluation:**
- ✓ Field names are stable and documented
- ✓ ISO timestamps (searchable)
- ✓ No internal identifiers (no blobId)
- ✓ Suitable for UI polling

**CONCERN:** `state` field exposes internal state names (CREATED, QUEUED, RUNNING, etc.). This is appropriate for polling but consider whether frontend should know about intermediate states.

#### Results Response
**File:** [api-gateway/routes/results.ts](api-gateway/routes/results.ts#L40-L46)

```typescript
res.status(200).json({
  jobId: job.jobId,
  schemaOutput: job.schemaOutput ?? null,
  confidence: job.confidence ?? null,
  qualityScore: job.qualityScore ?? null,
});
```

**Evaluation:**
- ✓ Minimal, stable fields
- ✓ No internal implementation details
- ✓ Suitable for consuming UI
- ✓ `null` used consistently for missing data

### Finding 5B: CRITICAL ISSUE - Error Responses Have Unstable Shapes ❌ **BLOCKER**

**Pattern 1: Two Different 404 Formats**

Results endpoint (line 19-22):
```typescript
res.status(404).json({
  error: 'Not Found',
  message: `Job not found: ${jobId}`,  // Format A: error + message
});
```

Upload endpoint (line 85-87):
```typescript
res.status(400).json({
  error: 'Invalid Content-Type',
  message: `Expected '${ACCEPTED_CONTENT_TYPE}', got '${contentType}'`,  // Format B: error + message
});
```

**Pattern 2: Inconsistent Error vs Errors Field**

Some endpoints use `{ error: '...' }` while the response shape doesn't explicitly document whether it should be `{ errors: [...] }` for validation errors.

**Pattern 3: Missing Error Code Field**

None of the error responses include an opaque error code:
```typescript
// Current
{ error: 'Not Found', message: '...' }

// Should be (per Requirement 4)
{ errorCode: 'JOB_NOT_FOUND', statusCode: 404 }
```

**Pattern 4: Inconsistent 404 vs Other Status Codes**

Not-found uses 404 (appropriate), but 403 Forbidden also returns success-like JSON structure:
```typescript
res.status(403).json({
  error: 'Forbidden',
  message: 'Access denied to this job',
});
```

**Classification:** ❌ **BLOCKER** – Response shapes are inconsistent across endpoints and violate the opaque error code requirement.

---

## 6. Artifact Storage & Result Persistence

### Finding 6A: Artifact Storage Properly Treats Data as Opaque ✅

**File:** [engine/storage/artifactStore.ts](engine/storage/artifactStore.ts)

The artifact store implements **crypto-blind storage:**
- ✓ No content inspection
- ✓ No schema awareness
- ✓ Size validation only
- ✓ Binary-safe operations
- ✓ Opaque metadata handling

**Code verification:**
```typescript
// Store an artifact
putArtifact(
  data: ArtifactData,  // No validation of content
  metadata: Partial<ArtifactMetadata> = {}
): ArtifactId {
  // Only validates size; no content inspection
  const dataSize = Buffer.byteLength(data);
  if (dataSize > this.maxArtifactSize) {
    throw error;  // Size limit only
  }
  // ... stores opaque data
}
```

**Verification:**
- ✓ Stores `schemaArtifactId` and `ocrArtifactId` (references, not content)
- ✓ Does not deserialize or inspect artifact content
- ✓ Result: Plaintext OCR never mixed with other artifacts

**Classification:** ✅ **ACCEPTABLE** – Artifact storage properly isolates processing results.

### Finding 6B: Result Persistence is Decoupled from State ✅

**File:** [engine/jobs/jobStore.ts](engine/jobs/jobStore.ts#L127-L141)

Results are set via `setJobOutput()` after successful processing:
```typescript
async setJobOutput(
  jobId: string,
  ocrArtifactId: string,
  schemaArtifactId: string,
  schemaOutput: Record<string, any>,
  confidence: Record<string, number>,
  qualityScore: number
): Promise<void> {
  // ... updates job with output fields
}
```

**Verification:**
- ✓ `setJobOutput()` is called only after job transitions to SUCCEEDED
- ✓ Results cannot be set before terminal state is reached
- ✓ State machine prevents accessing non-terminal jobs

**Classification:** ✅ **ACCEPTABLE** – Results persist with correct lifecycle management.

---

## 7. Attack Surface Analysis

### Attack 1: Cross-User Job Access ❌ MITIGATED

**Attack:** User A tries to access User B's job results.

**Defense:**
```typescript
if (job.userId !== userId) {
  res.status(403).json({
    error: 'Forbidden',
    message: 'Access denied to this job',
  });
  return;
}
```

**Result:** ✅ Properly blocked with 403. However, the verbose error message reveals job exists.

**Severity:** Medium (access prevented, but existence confirmed).

### Attack 2: Unauthenticated Access ❌ MITIGATED

**Attack:** Attacker accesses endpoints without JWT token.

**Defense:** `authenticateRequest` middleware applied to all routes.

```typescript
const authHeader = req.headers.authorization;
if (!authHeader || !authHeader.startsWith('Bearer ')) {
  res.status(401).json({
    error: 'Unauthorized',
    message: 'Authentication required',
  });
  return;
}
```

**Result:** ✅ Properly blocked with 401. Error message is appropriate (unauthenticated).

**Severity:** Mitigated.

### Attack 3: jobId Enumeration Via Timing ⚠️ PARTIALLY MITIGATED

**Attack:** Attacker generates UUIDs and checks if they produce different 404 messages.

**Example:**
```
GET /api/v1/jobs/550e8400-e29b-41d4-a716-446655440000/results
→ 404 { message: "Job not found: 550e8400-e29b-41d4-a716-446655440000" }

GET /api/v1/jobs/550e8400-e29b-41d4-a716-446655440001/results
→ 403 { message: "Access denied to this job" }
```

**Inference:** UUID #1 doesn't exist; UUID #2 exists but belongs to someone else.

**Current mitigation:**
- ❌ Error messages distinguish between "not found" and "forbidden"
- ❌ Attacker can fingerprint existing jobIds

**Result:** ⚠️ Partially vulnerable. Timing is not attacked; message content is.

**Severity:** Medium (exists enumeration possible, but requires valid JWT token).

### Attack 4: Job State Inference ⚠️ VULNERABLE

**Attack:** Attacker polls job status endpoint repeatedly to infer processing state.

**Example:**
```
GET /api/v1/jobs/550e8400-e29b-41d4-a716-446655440000
→ 200 { state: "RUNNING", retries: 0, ... }
→ 200 { state: "RETRYING", retries: 1, ... }
→ 200 { state: "SUCCEEDED", retries: 1, ... }
GET /api/v1/jobs/550e8400-e29b-41d4-a716-446655440000/results
→ 200 { schemaOutput: {...} }
```

**Attacker learns:**
- Job was retried once
- Job succeeded after retry
- Exact timing of transitions (via polling intervals)

**Current mitigation:**
- ✓ State information is only exposed to job owner
- ❌ Exact state names expose internal processing details
- ❌ Retry count exposes failure information

**Severity:** Low (information limited to job owner, but fine-grained state exposed).

---

## 8. Cross-Verification with Threat Model

**Reference:** [security/threat-model.md](security/threat-model.md)

### Threat Model Requirements
The threat model specifies:
1. **Per-user storage isolation** – Enforced at infrastructure level
2. **API Gateway cannot detect plaintext uploads** – Acknowledged limitation
3. **Authorization must prevent cross-user access** – Application responsibility
4. **Compliant clients upload encrypted payloads** – Assumed for zero-knowledge

### API Compliance

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Enforce per-user access | ✅ Enforced | [jobs.ts#L24-L28](api-gateway/routes/jobs.ts#L24-L28) |
| Prevent plaintext in API responses | ✅ Enforced | No OCR text in results endpoint |
| Require authentication | ✅ Enforced | All routes protected by JWT middleware |
| No access to FAILED job results | ✅ Enforced | Results blocked for non-SUCCEEDED states |
| Error responses reveal no information | ❌ Violated | Verbose error messages leak state |

**Classification:** The API enforcement is strong, but error response design violates zero-knowledge principles by enabling inference attacks.

---

## 9. Summary of Findings

### ✅ ACCEPTABLE (Proper Enforcement)

1. **State-based result gating** – Results only accessible when `state === SUCCEEDED`
2. **Per-user authorization** – Proper ownership checks with 403 responses
3. **Authentication** – JWT tokens required, properly validated
4. **Plaintext OCR not exposed** – Success response shapes omit dangerous fields
5. **Artifact storage** – Opaque, crypto-blind, size-limited only
6. **Idempotency** – Per-user key tuples prevent collision attacks

### ❌ BLOCKER (Must Fix Before Production)

1. **Error responses leak system state** – Verbose messages enable enumeration and inference attacks
   - `Job not found: {jobId}` vs `Access denied to this job` enables enumeration
   - `Job has not succeeded` leaks state information
   - **Fix required:** Use opaque error codes only

2. **Response shapes are inconsistent** – No opaque error code field, mixed error formats
   - Need standardized `{ errorCode: '...', statusCode: ... }` structure
   - **Fix required:** Uniform error response schema

3. **Verbose validation errors** – Leak API requirements
   - `Expected 'application/octet-stream', got 'application/json'` leaks content types
   - `Upload exceeds maximum size of 104857600 bytes` leaks limits
   - **Fix required:** Use codes like `INVALID_CONTENT_TYPE` instead

### ⚠️ ACCEPTABLE WITH NOTES (Design Decisions)

1. **State names exposed in job status** – Internal states (QUEUED, RUNNING, RETRYING) visible to frontend
   - This may be intentional for UI design
   - **Recommendation:** Consider abstracting to user-facing states (e.g., "Processing" instead of "QUEUED")

2. **Retry count exposed** – Shows failure history
   - Only exposed to job owner; acceptable for transparency
   - **Note:** Combining with state names can infer failure patterns

---

## 10. Remediation Recommendations

### BLOCKER 1: Opaque Error Codes

**Problem:** All error messages are verbose and leak system state.

**Solution:** Implement standard error response format:

```typescript
// Before
res.status(404).json({
  error: 'Not Found',
  message: `Job not found: ${jobId}`,
});

// After
res.status(404).json({
  errorCode: 'RESOURCE_NOT_FOUND',
  statusCode: 404,
});
```

**Implementation:**
1. Define error code constants (e.g., `ErrorCode` enum)
2. Remove all verbose messages from API responses
3. Log verbose details server-side only (in structured logs, not exposed)
4. Use HTTP status codes + opaque code only

**Files to modify:**
- [api-gateway/routes/results.ts](api-gateway/routes/results.ts)
- [api-gateway/routes/jobs.ts](api-gateway/routes/jobs.ts)
- [api-gateway/routes/upload.ts](api-gateway/routes/upload.ts)
- [api-gateway/auth/middleware.ts](api-gateway/auth/middleware.ts)

### BLOCKER 2: Consistent Error Response Schema

**Problem:** Different endpoints return different error shapes.

**Solution:** Define and enforce a single schema:

```typescript
interface ErrorResponse {
  errorCode: string;
  statusCode: number;
  [key: string]: never;  // Reject any additional fields
}

interface SuccessResponse<T> {
  data: T;
}
```

**Implementation:**
1. Create `api-gateway/types/responses.ts`
2. Define both success and error response types
3. Apply type checking to all route handlers
4. Update all responses to match schema

### BLOCKER 3: Enumeration Prevention

**Problem:** Different 404 messages for "not found" vs "forbidden" enable enumeration.

**Solution:** Consolidate both cases to single response:

```typescript
// Both "not found" and "forbidden" return the same generic error
res.status(404).json({
  errorCode: 'RESOURCE_NOT_FOUND',
  statusCode: 404,
});
```

**Rationale:** Attacker cannot distinguish between missing resource and access denied.

**Trade-off:** API returns 404 even for access denied (breaks REST convention slightly, but improves security).

**Alternative:** Return 403 for both, but only after confirming resource exists (requires two lookups).

---

## 11. Test Plan Recommendations

### Test 1: Error Code Consistency
```typescript
// All errors should follow schema
const response = await GET('/api/v1/jobs/invalid-id');
expect(response.body).toHaveProperty('errorCode');
expect(response.body).not.toHaveProperty('message');
expect(response.body).not.toHaveProperty('error');
```

### Test 2: Enumeration Prevention
```typescript
// Both invalid jobId and forbidden jobId return same response
const invalidResponse = await GET('/api/v1/jobs/invalid-uuid');
const forbiddenResponse = await GET('/api/v1/jobs/other-user-job');

expect(invalidResponse.status).toBe(forbiddenResponse.status);
expect(invalidResponse.body.errorCode).toBe(forbiddenResponse.body.errorCode);
```

### Test 3: Response Shape Validation
```typescript
// Success responses should not include error fields
const response = await GET('/api/v1/jobs/valid-id');
expect(response.body).not.toHaveProperty('error');
expect(response.body).not.toHaveProperty('errorCode');
```

---

## Conclusion

The output delivery API has **strong access control enforcement** but **weak error response design** that enables information disclosure attacks. The core security properties (state-based gating, per-user authorization, authentication) are properly implemented. However, the system violates its own threat model principles through verbose error messages.

**Action Required Before Production:**
1. Implement opaque error codes (remove all verbose messages)
2. Standardize response schemas across all endpoints
3. Prevent enumeration attacks through unified error responses

**Expected Impact:** After remediation, the API will be production-ready for zero-knowledge delivery with no information disclosure via error channels.

---

## Appendix: Test Coverage Gaps

### Missing Tests
1. Cross-user access attempts (should return opaque error)
2. Results access on non-SUCCEEDED jobs (should be indistinguishable from invalid jobId)
3. Response shape validation against schema
4. Error code consistency across all endpoints
5. Timing attack tests (verify all paths take consistent time)

### Recommended Test Framework
- Use `jest` with type checking
- Create fixture factories for test jobs and users
- Test response shapes with TypeScript interfaces
- Verify HTTP semantics (status codes, header values)
