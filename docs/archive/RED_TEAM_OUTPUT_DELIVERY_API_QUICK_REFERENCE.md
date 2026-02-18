# Red Team Output Delivery API Review - Executive Summary

**Date:** 5 January 2026  
**Reviewer:** Red Team Security Lead  
**Status:** Complete

---

## Findings at a Glance

| Category | Status | Finding |
|----------|--------|---------|
| **State-based result gating** | ✅ ACCEPTABLE | Results properly restricted to SUCCEEDED state; enforcement verified |
| **Authentication** | ✅ ACCEPTABLE | JWT tokens enforced; all routes protected by middleware |
| **Per-user authorization** | ✅ ACCEPTABLE | Ownership checks in place; 403 returned on mismatch |
| **Plaintext OCR exposure** | ✅ ACCEPTABLE | OCR text never exposed; response shapes sanitized |
| **Internal path exposure** | ✅ ACCEPTABLE | No blobId, artifactId, or internal identifiers in API responses |
| **Error response opacity** | ❌ **BLOCKER** | Verbose error messages leak system state and enable enumeration |
| **Response shape stability** | ❌ **BLOCKER** | Inconsistent error schemas; missing opaque error codes |

---

## Critical Issues

### BLOCKER #1: Error Responses Enable Enumeration

**Problem:**
```typescript
// This response reveals the jobId doesn't exist
res.status(404).json({
  error: 'Not Found',
  message: `Job not found: ${jobId}`,  // ← LEAKS
});

// But this reveals it exists (and user can't access)
res.status(403).json({
  error: 'Forbidden',
  message: 'Access denied to this job',  // ← DIFFERENT
});
```

**Attack:** Attacker can enumerate jobIds by observing different error messages.

**Fix:** Return identical response for both cases:
```typescript
res.status(404).json({
  errorCode: 'RESOURCE_NOT_FOUND',
  statusCode: 404,
});
```

**Affected Files:**
- [api-gateway/routes/results.ts](api-gateway/routes/results.ts)
- [api-gateway/routes/jobs.ts](api-gateway/routes/jobs.ts)

### BLOCKER #2: Verbose Validation Errors Leak API Details

**Problem:**
```typescript
res.status(413).json({
  error: 'Payload Too Large',
  message: `Upload exceeds maximum size of ${MAX_UPLOAD_SIZE} bytes`,  // ← LEAKS upload limit
});
```

**Attack:** Attacker discovers system limits, content types, and validation rules through error messages.

**Fix:** Use opaque error codes:
```typescript
res.status(413).json({
  errorCode: 'PAYLOAD_TOO_LARGE',
  statusCode: 413,
});
```

**Affected File:** [api-gateway/routes/upload.ts](api-gateway/routes/upload.ts)

### BLOCKER #3: Inconsistent Response Schemas

**Problem:** No standardized error response format across endpoints.

**Current:**
- Some use `{ error: '...', message: '...' }`
- No `errorCode` field for opaque error identification
- No schema validation in TypeScript

**Fix:** Enforce single schema:
```typescript
interface ErrorResponse {
  errorCode: string;
  statusCode: number;
  // No other fields
}
```

**Scope:** All routes in [api-gateway/routes/](api-gateway/routes/)

---

## Properly Implemented Features ✅

### 1. State-Based Result Gating
Results accessible **only when `job.state === 'SUCCEEDED'`**. All other states return 404.

**Evidence:** [api-gateway/routes/results.ts](api-gateway/routes/results.ts#L34-L39)

### 2. Per-User Authorization
Every request checks `job.userId === authenticatedUserId` before returning data.

**Evidence:** [api-gateway/routes/results.ts](api-gateway/routes/results.ts#L24-L28) and [api-gateway/routes/jobs.ts](api-gateway/routes/jobs.ts#L24-L28)

### 3. Mandatory Authentication
All endpoints protected by `authenticateRequest` middleware requiring valid JWT token.

**Evidence:** [api-gateway/auth/middleware.ts](api-gateway/auth/middleware.ts)

### 4. No Plaintext OCR in Responses
Success response omits all dangerous fields (rawOCR, plaintext, blobId).

**Evidence:** [api-gateway/routes/results.ts](api-gateway/routes/results.ts#L40-L46)

### 5. Opaque Artifact Storage
Artifact storage treats all data as opaque; no content inspection.

**Evidence:** [engine/storage/artifactStore.ts](engine/storage/artifactStore.ts)

---

## Requirement Compliance

### Requirement 1: Results Accessible Only When SUCCEEDED
✅ **COMPLIANT** – Proper state validation enforced.

### Requirement 2: Authentication & Per-User Authorization
✅ **COMPLIANT** – Both enforced correctly.

### Requirement 3: No Plaintext OCR or Internal Paths
✅ **COMPLIANT** – Success responses sanitized. 
⚠️ **WARNING** – Error responses leak state (see BLOCKER #1).

### Requirement 4: Error Responses Use Opaque Codes Only
❌ **NOT COMPLIANT** – Verbose messages violate requirement.

**Current:** `{ error: '...', message: '...' }`  
**Required:** `{ errorCode: '...', statusCode: ... }`

### Requirement 5: Response Shapes Stable for UI
⚠️ **PARTIALLY COMPLIANT** – Success shapes stable, error shapes inconsistent.

---

## Implementation Effort

| Task | Effort | Risk | Files |
|------|--------|------|-------|
| Add opaque error codes | 1-2 hours | Low | 4 files |
| Standardize error response schema | 1 hour | Low | Type definitions |
| Add test coverage | 2-3 hours | Low | New test files |
| Verify enumeration prevention | 1 hour | Low | Integration tests |

**Total:** 5-7 hours  
**Risk Level:** Low (fixes only add constraints, no behavior changes)

---

## Recommended Action Items

### Immediate (Before Production)
1. [ ] Implement opaque error codes in all endpoints
2. [ ] Standardize error response schema
3. [ ] Add integration tests for enumeration prevention
4. [ ] Verify no verbose messages in error responses

### Optional (Post-Launch)
1. [ ] Consider abstracting state names (expose user-facing states instead of internal ones)
2. [ ] Add rate limiting to prevent brute-force enumeration
3. [ ] Implement request logging to audit enumeration attempts

---

## References

- **Full Review:** [RED_TEAM_OUTPUT_DELIVERY_API_REVIEW.md](RED_TEAM_OUTPUT_DELIVERY_API_REVIEW.md)
- **Threat Model:** [security/threat-model.md](security/threat-model.md)
- **API Routes:** [api-gateway/routes/](api-gateway/routes/)
- **Job Storage:** [engine/jobs/jobStore.ts](engine/jobs/jobStore.ts)
- **Auth Middleware:** [api-gateway/auth/middleware.ts](api-gateway/auth/middleware.ts)

---

## Classification Summary

- **BLOCKERS:** 2 (error response design)
- **ACCEPTABLE:** 5 (core security controls)
- **DEFERRED:** 0 (all issues actionable)

**Overall Assessment:** ✅ Core access controls are strong. ❌ Error response design must be fixed before production due to information disclosure via error channels.
