# RED TEAM REVIEW: Upload Protocol & API Gateway
**Date:** 2026-01-04  
**Scope:** API Gateway `/upload` endpoint + Client upload module  
**Perspective:** Hostile clients, plaintext uploads, gateway behavior only  

---

## EXECUTIVE SUMMARY

The upload protocol is **intentionally crypto-blind** with explicit acceptance of plaintext uploads. Gateway focuses on opaque binary handling, size limits, and idempotency. Review identifies **0 blockers** but documents critical acceptance criteria and minor operational gaps.

---

## FINDINGS BY CATEGORY

### 1. ENCRYPTED PAYLOAD ASSUMPTIONS

#### Finding: NO ASSUMPTIONS ✅
**Status:** `ACCEPTABLE`

**Evidence:**
- Gateway treats payloads as **opaque bytes only** (upload.ts:23-24)
- No inspection of payload contents (upload-envelope.md:33-36)
- No validation of structure or format (upload-envelope.md:33)
- Specification explicitly permits plaintext uploads (upload-envelope.md:44-45)

**Code Review:**
```typescript
// upload.ts lines 35-50
const payloadBuffer = req.body;  // No inspection
const storageResult = await storageLayer.store({
  blobId,
  clientRequestId,
  payloadBytes: payloadBuffer,   // Passed as opaque bytes
});
```

**Risk Assessment:**
- ✅ Hostile client can upload plaintext undetected
- ✅ No decryption attempt or validation
- ✅ Server makes zero cryptographic claims

**Threat Model Alignment:**
Explicitly accepted per upload-envelope.md:
> "Plaintext uploads: Hostile or misconfigured clients may upload unencrypted payloads. The server cannot and will not detect or prevent this."

**Verdict:** Implementation matches specification. No blocker.

---

### 2. PAYLOAD BYTES LOGGING

#### Finding: POSSIBLE EXPOSURE IN ERROR PATHS 🟡
**Status:** `DEFERRED` (low likelihood, operational hardening needed)

**Evidence:**

**Upload Handler (upload.ts:28-51):**
- Line 35: `const payloadBuffer = req.body;` - Accessed but NOT logged directly
- Line 42-47: Error catch block calls `next(error)` - passes to Express error handler
- No logging statement in upload handler itself ✅

**Search for explicit payload logging:**
```
0 results for "logging payload bytes"
```

**Potential Risk Vectors:**

1. **Express error handler (implied by `next(error)`)**
   - Handler not reviewed (implementation incomplete)
   - May serialize full `req.body` in error logs
   - HIGH RISK if error handler logs request details

2. **Storage layer (blobStore.ts:8-30)**
   - Line 17: `bytes: Buffer.from(bytes)` - stores opaque buffer
   - No logging in blobStore itself ✅

3. **Middleware (authentication)**
   - `authenticateRequest` imported but not found in codebase
   - May log headers/body for audit
   - UNKNOWN RISK

**Code Locations to Check:**
- [ ] `/api-gateway/auth/middleware.ts` - NOT FOUND (critical gap)
- [ ] Express error handler middleware - NOT FOUND (critical gap)
- [ ] Any request logging middleware (morgan, bunyan, etc.) - NOT REVIEWED

**Impact:** 
If error handler or logging middleware serializes `req.body` on exception, plaintext payloads could leak to logs.

**Verdict:** Implementation appears safe **as shown**, but incomplete codebase prevents full assessment. **Deferred** pending review of:
- Auth middleware implementation
- Global error handler
- Request logging configuration

**Recommendations:**
```typescript
// In any error handler:
// ❌ AVOID
console.error("Upload failed:", req.body);  // Dumps payload
console.error("Request:", req);              // Includes body

// ✅ PREFER  
console.error("Upload failed:", {
  status: error.status,
  blobId: error.blobId,
  clientRequestId: error.clientRequestId,
  // Do NOT include req.body
});
```

---

### 3. METADATA LEAKS

#### Finding: ACCEPTABLE WITH OPERATIONAL NOTES ✅
**Status:** `ACCEPTABLE`

**What Gateway Returns (upload.ts:45-48):**
```typescript
res.status(201).json({
  blobId: storageResult.blobId,        // Server-generated UUID
  clientRequestId,                      // Echo of client header
  uploadedBytes: payloadBuffer.length,  // Byte count
});
```

**Leaked Information:**
1. **uploadedBytes** - Exact payload size (CONFIRMED LEAK)
2. **clientRequestId** - Echo of client-provided header (EXPECTED)
3. **blobId** - Server-generated reference (ACCEPTABLE)

**Risk Assessment:**

| Metadata | Leaks | Impact | Accepted? |
|----------|-------|--------|-----------|
| Payload size | YES | Reveals document length, enables inference attacks on content | ✅ YES |
| Content-Type | NO | Stripped to single value (application/octet-stream) | — |
| Request headers | NO | Only clientRequestId echoed | — |
| Timestamps | NO | Not exposed in response | — |
| Content hash | NO | Not computed/exposed | — |

**Design Rationale (upload-envelope.md):**
> "clientRequestId enables client-driven idempotency"  
> "Opaque handling: The server's crypto-blindness is a feature, not a limitation"

**Threat Model Acceptance:**
The specification explicitly accepts that:
- Server cannot verify encryption
- Server makes no cryptographic assumptions
- Payload size is visible to gateway (due to streaming HTTP model)

**Real-world Impact:**
Size alone provides limited value without other context:
- ~150-5000 bytes: typical encrypted document
- >100 MB: large media, multi-document batch
Requires additional side-channel data (timing, frequency, IP) for exploitation.

**Verdict:** Metadata leaks are inherent to HTTP and documented. No blocker.

---

### 4. MISSING AUTH & SIZE CHECKS

#### Finding: AUTH INCOMPLETE; SIZE CHECKS PRESENT ⚠️
**Status:** `BLOCKER` (auth middleware missing) + `ACCEPTABLE` (size)

---

#### 4a. AUTHENTICATION

**Status:** `BLOCKER`

**Code Review (upload.ts:27):**
```typescript
router.post(
  '/upload',
  authenticateRequest,  // ← Middleware referenced
  validateUploadRequest,
  async (req: Request, res: Response, next: NextFunction) => {
```

**Implementation Status:**
```
Import: import { authenticateRequest } from '../auth/middleware';
Location: /api-gateway/auth/middleware.ts
Status: NOT FOUND IN CODEBASE ❌
```

**Red Team Perspective:**
If middleware is missing:
- ✅ Gateway will fail with import error (caught at startup)
- ❌ Endpoint accepts any authenticated client (per middleware implementation)
- ❌ No bearer token, API key, or session validation visible

**Critical Questions:**
1. Does `authenticateRequest` exist? (Not in workspace)
2. What auth mechanism enforces? (Unknown)
3. What happens if middleware is missing? (Runtime error at startup)

**Expected Behavior (from code pattern):**
Middleware should:
```typescript
function authenticateRequest(req: Request, res: Response, next: NextFunction) {
  const authHeader = req.headers['authorization'];
  
  if (!authHeader) {
    return res.status(401).json({ error: 'Unauthorized' });
  }
  
  // Verify token/session...
  // If valid: next()
  // If invalid: res.status(403).json({ error: 'Forbidden' })
}
```

**Hostile Client Scenario:**
If auth middleware is missing or not enforcing:
- Unauthenticated attacker can POST to /upload
- Upload 100 MB of junk to exhaust storage
- Generate new blobIds indefinitely
- Trigger downstream processing of plaintext payloads

**Verdict:** **BLOCKER** - Authentication middleware must be:
1. Implemented in codebase
2. Enforcing valid credentials
3. Returning 401/403 on auth failure

---

#### 4b. SIZE CHECKS

**Status:** `ACCEPTABLE`

**Validation Implementation (upload.ts:72-94):**

| Check | Implementation | Enforced? |
|-------|-----------------|-----------|
| Content-Type | `contentType !== ACCEPTED_CONTENT_TYPE` (line 76) | ✅ YES (400 error) |
| Content-Length | `contentLength > MAX_UPLOAD_SIZE` (line 88) | ✅ YES (413 error) |
| Content-Length required | `contentLength === 0` check (line 82) | ✅ YES (411 error) |
| clientRequestId required | `!clientRequestId` check (line 96) | ✅ YES (400 error) |
| clientRequestId non-empty | `clientRequestId.trim() === ''` (line 104) | ✅ YES (400 error) |

**Limit Value (upload.ts:11):**
```typescript
const MAX_UPLOAD_SIZE = 100 * 1024 * 1024;  // 100 MB
```

**Header Validation Timing:**
- Validation occurs BEFORE payload is buffered ✅
- Middleware chain: `authenticateRequest` → `validateUploadRequest` → handler

**Header Spoofing Protection:**
```typescript
const contentLength = parseInt(req.headers['content-length'] || '0', 10);
```
- Reads from HTTP header (client-provided)
- Does NOT stream-based length check (potential gap)
- Node.js/Express does enforce header via streaming limits, but gateway relies on header

**Potential Attack:**
```http
POST /upload HTTP/1.1
Content-Length: 50  # Claim 50 bytes
x-client-request-id: test

[SEND 1000000000 BYTES] # Attack: stream 1GB despite header
```

**Mitigation Status:**
- Express default has stream limits (varies by version)
- No explicit byte-counting in handler code
- Should add `maxRequestSize` middleware:
```typescript
app.use(express.raw({ limit: '100mb', type: 'application/octet-stream' }));
```

**Verdict:** Size checks present but could be hardened. `ACCEPTABLE` with caveat that streaming limits must be configured in Express setup (not shown).

---

### 5. IDEMPOTENCY FLAWS

#### Finding: POTENTIAL REPLAY & DUPLICATION ISSUES 🟡
**Status:** `DEFERRED` (depends on storage implementation)

**Specified Mechanism (upload-envelope.md:38-39):**
> "clientRequestId enables client-driven idempotency"  
> "Server MUST deduplicate by clientRequestId on retry"

**Code Review:**

**Gateway Handler (upload.ts:35-50):**
```typescript
const clientRequestId = req.headers['x-client-request-id'] as string;
const blobId = uuidv4();  // ← Always generates NEW UUID

const storageResult = await storageLayer.store({
  blobId,
  clientRequestId,
  payloadBytes: payloadBuffer,
});
```

**Problem Analysis:**

1. **No Deduplication Check**
   - Gateway does NOT check if `clientRequestId` was previously uploaded
   - Every request with same `clientRequestId` creates NEW `blobId`
   - Violates idempotency requirement

2. **Storage Layer (blobStore.ts:15-26)**
   ```typescript
   put(bytes: Buffer, metadata: BlobMetadata, blobId?: string): string {
     const id = blobId || randomUUID();
     this.store.set(id, { bytes, metadata });
     return id;
   }
   ```
   - Accepts `blobId` (provided by gateway)
   - No lookup by `clientRequestId`
   - No duplicate detection

3. **Metadata Structure (blobStore.ts:6-11)**
   ```typescript
   interface BlobMetadata {
     size: number;
     userId: string;
     timestamp: number;
   }
   ```
   - Does NOT include `clientRequestId`
   - Cannot deduplicate on retrieval

**Threat Model:**
- **Honest client retries:** Same upload generates multiple blobIds
- **Hostile client:** Can spam same `clientRequestId` to create storage exhaustion
- **Example:**
  ```
  Request 1: POST /upload, clientRequestId=ABC, body=1MB
    → Returns blobId=UUID-1
  Request 2: POST /upload, clientRequestId=ABC, body=1MB (retry)
    → Returns blobId=UUID-2  ❌ SHOULD return UUID-1
  ```

**Expected Correct Behavior:**
```typescript
// Pseudocode - what SHOULD happen
async function handleUpload(req, res) {
  const clientRequestId = req.headers['x-client-request-id'];
  
  // Check if we've already processed this request
  const existing = await storage.lookupByClientRequestId(clientRequestId);
  if (existing) {
    return res.status(200).json({  // 200, not 201 (already exists)
      blobId: existing.blobId,
      clientRequestId,
      uploadedBytes: existing.size,
    });
  }
  
  // Process new request
  const blobId = generateUUID();
  await storage.store({
    blobId,
    clientRequestId,  // ← MUST STORE THIS
    payloadBytes,
  });
  
  return res.status(201).json({ blobId, clientRequestId, uploadedBytes });
}
```

**Assessment:**

| Scenario | Current Behavior | Spec Requirement | Compliant? |
|----------|------------------|------------------|-----------|
| Honest client, normal upload | Creates 1 blobId | Same | ✅ |
| Honest client, retries | Creates N blobIds | Should return same | ❌ |
| Hostile client, spam retries | Creates 1000 blobIds | Reject duplicates | ❌ |
| Network timeout, auto-retry | Duplicate uploads | Idempotent recovery | ❌ |

**Storage Exhaustion Attack:**
```bash
for i in {1..10000}; do
  curl -X POST http://gateway/upload \
    -H "x-client-request-id: attack-123" \
    -H "Content-Type: application/octet-stream" \
    -H "Content-Length: 100000000" \
    --data-binary @payload.bin
done
```
Result: 1 TB stored with 10,000 identical copies (one per upload).

**Verdict:** **DEFERRED** - Idempotency implementation is incomplete. Requires:
1. Store `clientRequestId` in blob metadata
2. Add lookup-by-clientRequestId query
3. Return 200 (not 201) for duplicate requests
4. Return same `blobId` for retries

This is a **functional gap**, not a security blocker, but enables DoS.

---

## SUMMARY TABLE

| Finding | Category | Status | Severity | Action |
|---------|----------|--------|----------|--------|
| No encryption assumptions | Encrypted Payloads | ✅ ACCEPTABLE | N/A | None |
| Error handler payload logging | Payload Logging | 🟡 DEFERRED | Medium | Review error handler impl |
| Metadata size leaks | Metadata | ✅ ACCEPTABLE | Low | Document in threat model |
| Missing auth middleware | Authentication | 🔴 BLOCKER | Critical | Implement middleware |
| Size limit checks | Size Checks | ✅ ACCEPTABLE | N/A | Harden with `maxRequestSize` |
| No deduplication by clientRequestId | Idempotency | 🟡 DEFERRED | Medium | Implement idempotency tracking |

---

## BLOCKER ISSUES (MUST FIX)

### Blocker #1: Missing Authentication Middleware
**File:** `api-gateway/auth/middleware.ts` (NOT FOUND)  
**Impact:** Any client can upload without credentials  
**Fix Required:** Implement and enforce authentication before accepting uploads

---

## ACCEPTABLE FINDINGS (WORKING AS DESIGNED)

### Acceptable #1: Opaque Payload Handling ✅
Gateway correctly treats payloads as opaque binary with zero inspection.

### Acceptable #2: Size Limit Enforcement ✅
100 MB limit is validated before buffering payload.

### Acceptable #3: Metadata Leaks ✅
Payload size leakage is inherent to HTTP streaming and explicitly accepted in threat model.

---

## DEFERRED ISSUES (FUTURE HARDENING)

### Deferred #1: Payload Bytes in Error Logs
**Risk:** Error handler may serialize full request body  
**Mitigation:** Implement structured logging that excludes `req.body`  
**Timeline:** Before production deployment

### Deferred #2: Idempotency Not Implemented
**Risk:** Retries create duplicate uploads, enabling storage exhaustion  
**Mitigation:** Track `clientRequestId` and deduplicate uploads  
**Timeline:** Before retry-heavy clients (mobile, flaky networks) are deployed

---

## THREAT ACTOR CAPABILITIES

Given **hostile clients** and **plaintext uploads:**

| Attack | Feasible? | Detection? | Mitigation |
|--------|-----------|-----------|------------|
| Upload plaintext | ✅ YES | NO | Not gateway responsibility |
| Exhaust storage (100 retries) | ✅ YES | Monitoring | Implement idempotency |
| DoS with large payloads | ✅ YES (unless rate-limited) | HTTP 413 | Rate limiting on clientRequestId |
| Log exfiltration | ⚠️ MAYBE | Log review | Sanitize error logs |
| SSRF via malformed binary | ✅ LOW | No parsing | Gateway opaque design prevents this |

---

## RECOMMENDATIONS

### Immediate (Before Launch)
1. **Implement auth middleware** - Prevent unauthenticated uploads
2. **Review error handling** - Ensure no payload logging in errors/exceptions
3. **Verify Express config** - Confirm `maxRequestSize` limit is enforced

### Short-term (Sprint 1)
4. **Implement idempotency** - Deduplicate by `clientRequestId`
5. **Add structured logging** - Exclude sensitive data from logs
6. **Document actual threat model** - Update upload-envelope.md with realized scope

### Future (Nice-to-have)
7. **Rate limiting** - Limit uploads per user/IP
8. **Audit trails** - Log uploads with `clientRequestId` for forensics
9. **Blob lifecycle** - Implement retention/cleanup policies

---

## CONCLUSION

The upload protocol design is **fundamentally sound** - crypto-blindness is intentional and correct. Gateway correctly avoids payload inspection.

**Critical gaps are operational, not architectural:**
- ✅ Zero cryptographic assumptions (correct design)
- ❌ Authentication middleware missing (implementation incomplete)
- ⚠️ Idempotency not implemented (functional, not security)
- ⚠️ Error logging needs audit (likely safe but unverified)

**Verdict:** **1 BLOCKER, 2 DEFERRED, 0 ARCHITECTURAL FLAWS**

Proceed with fixes before production.
