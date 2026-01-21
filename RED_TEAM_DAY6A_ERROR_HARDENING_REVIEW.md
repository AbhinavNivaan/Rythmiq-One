# RED TEAM DAY-6A ERROR HARDENING REVIEW
**Date:** 2026-01-06  
**Reviewer:** Red Team  
**Scope:** Error handling implementation hardening review

---

## EXECUTIVE SUMMARY

**STATUS: ⚠️ ONE CRITICAL BLOCKER IDENTIFIED**

The Day-6A error hardening fixes successfully address most security concerns around error leakage. However, **one critical vulnerability remains** that allows attackers to enumerate valid job IDs and infer job states through timing and error analysis.

---

## VERIFICATION RESULTS

### ✅ 1. NO VERBOSE VALIDATION ERRORS
**Status:** PASS

**Finding:** All validation errors properly sanitized
- Upload validation uses `sendValidationError()` with internal-only messages
- Messages like `"Content-Length ${contentLength} exceeds maximum size of ${MAX_UPLOAD_SIZE}"` are logged server-side only (line 103, upload.ts)
- Client receives only: `{ "errorCode": "INVALID_REQUEST" }`
- Auth errors sanitized via `sendAuthError()` - no token details exposed
- Framework errors caught and mapped to canonical schema

**Evidence:**
```typescript
// upload.ts lines 85-88
return sendValidationError(
  res,
  `Invalid Content-Type: expected '${ACCEPTED_CONTENT_TYPE}', got '${contentType}'`
);

// validationErrors.ts lines 30-40
export function sendValidationError(res: Response, message?: string): Response {
  if (message) {
    console.warn('[VALIDATION_ERROR]', message);  // Server-side only
  }
  return res.status(SANITIZED_VALIDATION_ERROR.statusCode).json({
    errorCode: SANITIZED_VALIDATION_ERROR.errorCode,  // Client sees this only
  });
}
```

---

### ✅ 2. ALL ERRORS USE UNIFORM OPAQUE SCHEMA
**Status:** PASS

**Finding:** Canonical schema enforced globally
- All error responses conform to: `{ "errorCode": "ERROR_CODE" }`
- Global error handler enforces schema (errorHandler.ts)
- Non-ApiError exceptions mapped to `INTERNAL_ERROR`
- No stack traces, messages, or framework objects exposed
- HTTP status codes set separately, not in response body

**Evidence:**
```typescript
// errorHandler.ts lines 62-67
if (isApiError(err)) {
  return res.status(err.statusCode).json({
    errorCode: err.errorCode,  // Only errorCode sent
  });
}

// errorHandler.ts lines 70-72
res.status(500).json({
  errorCode: 'INTERNAL_ERROR',  // Generic fallback
});
```

---

### 🚨 3. JOB ENUMERATION VIA ERROR DIFFERENCES
**Status:** FAIL - CRITICAL BLOCKER

**Vulnerability:** Timing-based job enumeration attack vector

**Attack Scenario:**
1. Attacker authenticates as UserA
2. Attacker tries to access JobB owned by UserB
3. Attacker can distinguish between:
   - JobB exists (owned by someone else) → Database query returns record → userId check fails → 404
   - JobB doesn't exist → Database query returns null → 404
   - JobB exists AND owned by UserA → 200 with job data

**Problematic Code:**
```typescript
// jobs.ts lines 16-19
const job = await jobStore.getJob(jobId);

if (!job || job.userId !== userId) {
  throwApiError('JOB_NOT_AVAILABLE', 404);
}
```

**Why This Is Dangerous:**
- Database query timing reveals whether job exists
- Attacker can probe job ID space to find valid jobs
- Combined with state leakage (below), reveals job lifecycle

**Recommended Fix:**
```typescript
// Use userId-scoped query to prevent enumeration
const job = await jobStore.getJobForUser(jobId, userId);

if (!job) {
  throwApiError('JOB_NOT_AVAILABLE', 404);
}
```

This ensures database query is scoped to userId from the start, preventing timing-based enumeration.

---

### 🚨 4. JOB STATE LEAKAGE
**Status:** FAIL - CRITICAL BLOCKER

**Vulnerability:** Results endpoint leaks job state information

**Problematic Code:**
```typescript
// results.ts lines 16-19
const job = await jobStore.getJob(jobId);

if (!job || job.userId !== userId || job.state !== 'SUCCEEDED') {
  throwApiError('JOB_NOT_AVAILABLE', 404);
}
```

**Attack Scenario:**
1. UserA submits JobA (state: PENDING)
2. UserA polls GET /jobs/JobA/results
3. Response: 404 JOB_NOT_AVAILABLE
4. After processing completes (state: SUCCEEDED)
5. UserA polls GET /jobs/JobA/results
6. Response: 200 with results

**Information Leaked:**
- Attacker can infer job state by monitoring when 404 → 200 transition occurs
- Combined with job enumeration, attacker can track processing lifecycle of jobs they don't own
- Timing analysis reveals processing duration

**Recommended Fix:**
Return same error regardless of state:
```typescript
const job = await jobStore.getJobForUser(jobId, userId);

if (!job) {
  throwApiError('JOB_NOT_AVAILABLE', 404);
}

if (job.state !== 'SUCCEEDED') {
  throwApiError('JOB_NOT_AVAILABLE', 404);  // Same error, no state info leaked
}
```

---

## ADDITIONAL OBSERVATIONS

### ⚠️ Minor Issue: Verbose Validation Messages in Code
**Severity:** Low (informational)

While validation messages are correctly hidden from clients, the verbose internal messages could be improved:

```typescript
// upload.ts line 103
`Content-Length ${contentLength} exceeds maximum size of ${MAX_UPLOAD_SIZE}`
```

**Concern:** Logs reveal internal limits (100MB)
**Risk:** Low - only visible in server logs, not client responses
**Recommendation:** Sanitize even internal messages to avoid accidental leakage via log aggregation tools

---

### ✅ Positive Finding: Auth Error Handling
**Status:** PASS

Auth middleware properly sanitizes JWT errors:
```typescript
// middleware.ts lines 51-58
const message =
  error instanceof jwt.TokenExpiredError
    ? 'Token has expired'
    : error instanceof jwt.JsonWebTokenError
      ? 'Invalid token signature'
      : 'Token verification failed';

return sendAuthError(res, message);
```

Client never sees specific JWT error details. ✅

---

### ✅ Positive Finding: Framework Error Sanitization
**Status:** PASS

Framework errors (body parser, JSON parse errors) properly caught and mapped:
```typescript
// validationErrors.ts lines 70-77
if (
  err.type === 'entity.parse.failed' ||
  err.message?.includes('content-type') ||
  err.message?.includes('Content-Type') ||
  err.message?.includes('payload') ||
  err.message?.includes('Payload')
) {
  console.warn('[FRAMEWORK_ERROR]', err.message);
  return res.status(400).json({ errorCode: 'INVALID_REQUEST' });
}
```

No framework implementation details exposed. ✅

---

## BLOCKERS SUMMARY

### 🔴 BLOCKER 1: Job Enumeration Attack
**File:** [api-gateway/routes/jobs.ts](api-gateway/routes/jobs.ts#L16)  
**Issue:** `jobStore.getJob(jobId)` allows timing-based enumeration  
**Impact:** Attacker can discover valid job IDs across all users  
**Fix:** Implement `jobStore.getJobForUser(jobId, userId)` with userId-scoped query

### 🔴 BLOCKER 2: Job State Leakage
**File:** [api-gateway/routes/results.ts](api-gateway/routes/results.ts#L18)  
**Issue:** Error response changes based on job state, leaking lifecycle information  
**Impact:** Attacker can infer job processing states  
**Fix:** Return identical error for all non-accessible states

---

## RECOMMENDED FIXES

### Fix 1: Implement User-Scoped Job Queries
```typescript
// engine/jobs/jobStore.ts
async getJobForUser(jobId: string, userId: string): Promise<Job | null> {
  return this.jobs.get(jobId)?.userId === userId 
    ? this.jobs.get(jobId) ?? null 
    : null;
}
```

### Fix 2: Update Jobs Route
```typescript
// api-gateway/routes/jobs.ts
const job = await jobStore.getJobForUser(jobId, userId);

if (!job) {
  throwApiError('JOB_NOT_AVAILABLE', 404);
}
```

### Fix 3: Update Results Route
```typescript
// api-gateway/routes/results.ts
const job = await jobStore.getJobForUser(jobId, userId);

if (!job) {
  throwApiError('JOB_NOT_AVAILABLE', 404);
}

if (job.state !== 'SUCCEEDED') {
  throwApiError('JOB_NOT_AVAILABLE', 404);
}
```

---

## VERIFICATION CHECKLIST

After fixes applied:
- [ ] Verify timing indistinguishable for non-existent vs unauthorized jobs
- [ ] Verify results endpoint returns same error for PENDING and unauthorized jobs
- [ ] Test enumeration attack: probe random job IDs, confirm no info leakage
- [ ] Test state inference: monitor results endpoint, confirm no lifecycle leakage
- [ ] Validate all errors still conform to canonical schema

---

## CONCLUSION

**DEPLOYMENT DECISION: DO NOT DEPLOY**

The error handling schema is well-designed and mostly implemented correctly. However, the two critical blockers around job enumeration and state leakage must be resolved before production deployment.

**Estimated Fix Time:** 2-4 hours  
**Re-review Required:** Yes, after fixes applied

---

## SEVERITY CLASSIFICATION

| Issue | Severity | Status | Exploitability |
|-------|----------|--------|----------------|
| Verbose validation errors | ✅ FIXED | PASS | N/A |
| Uniform error schema | ✅ FIXED | PASS | N/A |
| Job enumeration | 🔴 CRITICAL | BLOCKER | HIGH |
| Job state leakage | 🔴 CRITICAL | BLOCKER | MEDIUM |

**OVERALL STATUS: BLOCKED - 2 CRITICAL ISSUES**
