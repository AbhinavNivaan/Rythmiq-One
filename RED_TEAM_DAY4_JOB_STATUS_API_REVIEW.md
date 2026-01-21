# Red Team Review: Day-4 Job Status API Patch
**Date:** 4 January 2026  
**Scope:** GET /jobs/{jobId} endpoint + Auth + Job state exposure  
**Reviewer Perspective:** Hostile client attempting to:
1. Access jobs without authentication
2. Access other users' jobs
3. Extract encrypted/sensitive data from responses

---

## EXECUTIVE SUMMARY

The Day-4 job status API patch implements **GET /jobs/{jobId}** with proper authorization controls. Review reveals **0 CRITICAL BLOCKERS**, but identifies one **CRITICAL AUTHENTICATION STUB** that must be addressed before production.

**Verdict:** ✅ **ARCHITECTURE SOUND** | ⚠️ **AUTH IMPLEMENTATION IS STUB** | ⚠️ **ONE MEDIUM BLOCKER**

---

## VERIFICATION CHECKLIST

### ✅ 1. GET /jobs/{jobId} Endpoint Exists
**Status:** `PASS`

**Evidence:**
- File: [api-gateway/routes/jobs.ts](api-gateway/routes/jobs.ts#L8-L45)
- Endpoint: `GET /:jobId` on Router
- HTTP method: Correct
- Route pattern: Correct (`:jobId` parameter extraction)

---

### ⚠️ 2. Authentication + Per-User Authorization Enforced
**Status:** `PARTIALLY PASS` (Auth flow correct, but implementation is STUB)

#### 2a. Authentication Middleware Applied
**Status:** `PASS`

**Evidence:**
```typescript
// jobs.ts:8
router.get(
  '/:jobId',
  authenticateRequest,  // ✅ Middleware applied BEFORE handler
  async (req: Request, res: Response, next: NextFunction) => {
```

✅ Authentication middleware is **required** before handler can execute

#### 2b. Per-User Authorization Check
**Status:** `PASS` (Implementation correct)

**Evidence:**
```typescript
// jobs.ts:13-15
const userId = (req as AuthenticatedRequest).userId as string;
const job = await jobStore.getJob(jobId);

// jobs.ts:23-28
if (job.userId !== userId) {
  res.status(403).json({
    error: 'Forbidden',
    message: 'Access denied to this job',
  });
  return;  // ✅ Early return prevents data leakage
}
```

✅ **Per-user authorization enforced correctly:**
- Compares `job.userId` against `req.userId`
- Returns 403 Forbidden on mismatch
- No fallthrough (early return)
- No conditional data exposure

#### 2c. Authentication Implementation Status: **STUB ⚠️**
**Status:** `BLOCKER - STUB IMPLEMENTATION`

**Evidence:**
```typescript
// auth/middleware.ts:30-31
// Stub: In production, validate token and extract user identity
// For now, assume token is valid and extract userId from token
(req as AuthenticatedRequest).userId = token;
```

**CRITICAL ISSUE:** Token is treated as userId directly without validation
- ❌ No token signature verification
- ❌ No token expiration check
- ❌ No claims validation
- ❌ No cryptographic binding

**Attack Vector:**
```
Attacker sends:  Authorization: Bearer alice
                 ↓
Middleware extracts: userId = "alice"
                 ↓
Attacker reads: job.userId === "alice"
                 ↓
Result: Attacker impersonates alice without credentials
```

**Impact:** Any attacker can impersonate any user by claiming their userId in the Bearer token.

---

### ✅ 3. Job State Reflects Worker Execution
**Status:** `PASS`

#### 3a. Worker Execution Updates State
**Status:** `PASS`

**Evidence:**
- File: [engine/cpu/worker.ts](engine/cpu/worker.ts#L60-L140)
- State transitions implemented:
  - `CREATED → QUEUED` (enqueue)
  - `QUEUED → RUNNING` (markRunning)
  - `RUNNING → SUCCEEDED` (markSucceeded)
  - `RUNNING → FAILED` (markFailed)
  - `RUNNING → RETRYING` (scheduleRetry)
  - `RETRYING → QUEUED` (promoteReadyRetries)

✅ Worker correctly updates job state via `transitionJobState()`

#### 3b. Job State Returned in API Response
**Status:** `PASS`

**Evidence:**
```typescript
// jobs.ts:35-40
res.status(200).json({
  jobId: job.jobId,        // ✅ Identifier only
  state: job.state,        // ✅ Worker-updated state
  retries: job.retries,    // ✅ Retry count from jobStore
  createdAt: job.createdAt,
  updatedAt: job.updatedAt,
  ...(job.failureReason && { error: job.failureReason }),
});
```

✅ Response returns **current state** from jobStore  
✅ State reflects worker execution because:
- jobStore maintains single source of truth
- Worker calls transitionJobState()
- API reads from same jobStore

---

### ✅ 4. No Payload or Crypto Data Exposed
**Status:** `PASS` (Zero sensitive fields returned)

#### 4a. Fields Returned in Response
**Status:** `PASS - MINIMAL DATA`

```typescript
{
  jobId: "uuid",              // ✅ Opaque identifier
  state: "RUNNING",           // ✅ Job lifecycle state only
  retries: 1,                 // ✅ Retry count
  createdAt: "2026-01-04...", // ✅ Timestamp
  updatedAt: "2026-01-04...", // ✅ Timestamp
  error?: "failure reason"    // ✅ Generic message only
}
```

✅ **Sensitive fields NOT returned:**
- ❌ No `blobId` (reference to encrypted payload)
- ❌ No `payload` (encrypted data)
- ❌ No `resultArtifactId` (processing output)
- ❌ No decryption keys (UMK, DEK)
- ❌ No processing internals
- ❌ No cryptographic material

#### 4b. What's NOT Exposed
**Status:** `PASS`

| Field | Returned? | Why Safe |
|-------|-----------|----------|
| `blobId` | ❌ NO | References encrypted upload; not needed for status |
| `resultArtifactId` | ❌ NO | Artifact reference withheld correctly |
| UMK | ❌ NO | Crypto key never touches API |
| DEK | ❌ NO | Crypto key never touches API |
| Payload bytes | ❌ NO | Stored in blobStore, not leaked |
| Error details | ⚠️ LIMITED | Only `failureReason` returned as string |
| Processing internals | ❌ NO | State enum only, no impl details |

✅ **Threat model alignment:**
- API is crypto-blind (matches specification)
- Zero assumption of encryption state
- Cannot verify or inspect payload
- No keys transmitted to API layer

---

## SECURITY ANALYSIS

### Attack Scenarios

#### Scenario 1: Unauthenticated Access
**Attack:** `GET /jobs/{jobId}` without Bearer token

**Current Defense:**
```typescript
if (!authHeader || !authHeader.startsWith('Bearer ')) {
  res.status(401).json({ error: 'Unauthorized', ... });
  return;  // ✅ Blocked
}
```
✅ **PASS**: Unauthenticated requests rejected

**Status:** ✅ BLOCKED

---

#### Scenario 2: Cross-User Access
**Attack:** User A tries to read User B's job

**Current Defense:**
```typescript
if (job.userId !== userId) {
  res.status(403).json({ error: 'Forbidden', ... });
  return;  // ✅ Blocked before any data returned
}
```
✅ **PASS**: Per-user authorization enforced

**But:** Auth is a stub (see 2c above) - token validation missing

**Status:** ⚠️ **PASS (AUTHORIZATION LOGIC) / BLOCKER (TOKEN VALIDATION)**

---

#### Scenario 3: Payload Data Extraction
**Attack:** Attacker reads job status to infer encrypted payload properties

**What can attacker infer?**
- ❌ **Payload bytes:** Not exposed
- ❌ **Blob ID:** Not returned
- ❌ **Processing result:** Not returned  
- ❌ **Decryption keys:** Not exposed
- ✅ **Job state:** PUBLIC (by design)
- ✅ **Retry count:** PUBLIC (by design)
- ⚠️ **Failure reason:** Generic message only

**Data Leakage Assessment:**
```
Response payload:
{
  jobId: "f47ac10b-58cc-4372-a567-0e02b2c3d479",  // Opaque ref
  state: "SUCCEEDED",                              // State only
  retries: 0,                                      // Retry count
  createdAt: "2026-01-04T10:30:00Z",              // Timestamp
  updatedAt: "2026-01-04T10:31:00Z",              // Timestamp
}
```

✅ **No crypto data exposed**  
✅ **No payload bytes exposed**  
✅ **No artifact references exposed**

**Status:** ✅ PASS

---

#### Scenario 4: Blob ID / Artifact ID Enumeration
**Attack:** Attacker tries to read job status to discover blobId or artifactId

**Current Response:**
```typescript
// jobs.ts:35-40
res.status(200).json({
  jobId: job.jobId,        // ✅ Only this identifier returned
  state: job.state,
  retries: job.retries,
  createdAt: job.createdAt,
  updatedAt: job.updatedAt,
});
```

✅ **PASS**: blobId and resultArtifactId are NOT returned

**Status:** ✅ PASS

---

### Code Review: Response Construction

**File:** [api-gateway/routes/jobs.ts](api-gateway/routes/jobs.ts#L35-L40)

```typescript
res.status(200).json({
  jobId: job.jobId,                                    // Line 36
  state: job.state,                                    // Line 37
  retries: job.retries,                               // Line 38
  createdAt: job.createdAt,                           // Line 39
  updatedAt: job.updatedAt,                           // Line 40
  ...(job.failureReason && { error: job.failureReason }), // Line 41
});
```

**What's in jobStore.Job interface?**
```typescript
export interface Job {
  jobId: string;
  blobId: string;        // ❌ NOT in response
  userId: string;        // ❌ NOT in response
  state: JobState;
  createdAt: Date;
  updatedAt: Date;
  retries: number;
  failureReason?: string;
}
```

✅ **Verification:** `blobId` and `userId` present in jobStore but **intentionally omitted** from API response

---

## BLOCKER ANALYSIS

### 🔴 BLOCKER #1: Authentication Token Validation Missing

**Severity:** `CRITICAL`  
**File:** [api-gateway/auth/middleware.ts](api-gateway/auth/middleware.ts#L30-L31)  
**Impact:** Authentication bypass; any client can impersonate any user

**Current Implementation:**
```typescript
// Stub: In production, validate token and extract user identity
// For now, assume token is valid and extract userId from token
(req as AuthenticatedRequest).userId = token;
```

**Attack:**
```
$ curl -H "Authorization: Bearer alice" http://api/jobs/job-123
→ userId = "alice" (no validation)
→ Can read alice's job even if attacker is bob
```

**Requirement:**
The token MUST be validated before extracting userId. Options:
1. **JWT verification** - Validate signature + exp claims
2. **Session token lookup** - Validate token against session store
3. **OAuth/OIDC** - Delegate to auth provider

**Fix Priority:** 🔴 **MUST FIX BEFORE PRODUCTION**

---

### 🟡 MEDIUM: Failure Reason May Leak Processing Details

**Severity:** `MEDIUM`  
**File:** [api-gateway/routes/jobs.ts](api-gateway/routes/jobs.ts#L41)  
**Impact:** Information disclosure; attacker infers job processing details

**Current Implementation:**
```typescript
...(job.failureReason && { error: job.failureReason }),
```

**Risk:** If failureReason contains implementation details:
- ❌ "Decryption failed: invalid nonce" → reveals crypto details
- ❌ "File format: XLSX not supported" → reveals supported formats
- ❌ "GPU processing timeout" → reveals infrastructure

**Recommendation:** Sanitize failureReason before returning
```typescript
// ✅ Generic errors
...(job.failureReason && { 
  error: job.state === 'FAILED' ? 'Processing failed' : undefined 
}),
```

**But:** Current implementation is **acceptable** if:
- failureReason only contains generic messages
- Processing engine never exposes crypto details in failure reasons

**Status:** 🟡 **DEFERRED - Verify processing engine doesn't leak details**

---

## AUDIT TRAILS & OBSERVABILITY

**Status:** Not reviewed in scope; see [docs/job-lifecycle.md](docs/job-lifecycle.md) for state machine guarantees.

---

## THREAT MODEL ALIGNMENT

**Reference:** [security/threat-model.md](security/threat-model.md)

The job status API correctly implements:

| Property | Requirement | Status |
|----------|-------------|--------|
| Crypto blindness | API makes zero crypto assumptions | ✅ PASS |
| Zero key exposure | No keys transmitted in API | ✅ PASS |
| Per-user isolation | Users can only read own jobs | ✅ PASS (auth stub aside) |
| Payload opacity | No payload bytes in response | ✅ PASS |
| State transparency | Job state is readable by owner | ✅ PASS |

---

## SUMMARY

### Verification Results

| Requirement | Status | Finding |
|------------|--------|---------|
| GET /jobs/{jobId} exists | ✅ PASS | Endpoint implemented correctly |
| Auth enforced | ⚠️ PASS/BLOCKER | Authorization logic correct; token validation is stub |
| Per-user authorization | ✅ PASS | 403 Forbidden on user mismatch |
| Job state reflects worker | ✅ PASS | jobStore updated via transitionJobState() |
| No payload exposed | ✅ PASS | blobId, resultArtifactId, keys all omitted |
| No crypto data exposed | ✅ PASS | Zero cryptographic material in response |

### Blockers Identified

| ID | Issue | Severity | Fix Required |
|----|-------|----------|--------------|
| B1 | Auth token validation is stub | CRITICAL | Implement JWT/session validation |
| B2 | Failure reason may leak details | MEDIUM | Sanitize error messages (deferred if messages are generic) |

---

## VERDICT

**ARCHITECTURE:** ✅ Sound  
**AUTHORIZATION LOGIC:** ✅ Correct  
**DATA EXPOSURE:** ✅ Minimal and safe  
**AUTH IMPLEMENTATION:** 🔴 STUB (blocker)

### Can Deploy?
❌ **NO** - Auth token validation must be implemented first

### Blocking Issues
1. **[api-gateway/auth/middleware.ts](api-gateway/auth/middleware.ts#L30-L31)** - Token validation stub must be replaced with real validation

### Recommendations
1. Implement token validation (JWT or session-based)
2. Verify processing engine doesn't leak sensitive details in failureReason
3. Add request logging for audit trail (exclude response bodies in logs)
4. Test cross-user access with valid tokens - ensure 403 returned

---

## REFERENCES

- **Job Lifecycle:** [docs/job-lifecycle.md](docs/job-lifecycle.md)
- **Threat Model:** [security/threat-model.md](security/threat-model.md)
- **Upload API Review:** [RED_TEAM_REVIEW_UPLOAD.md](RED_TEAM_REVIEW_UPLOAD.md)
