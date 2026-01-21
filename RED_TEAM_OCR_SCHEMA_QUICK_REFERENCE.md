# RED TEAM REVIEW: QUICK REFERENCE

## Status: 🔴 3 BLOCKERS 🟠 3 DEFERRED 🟢 3 ACCEPTABLE

---

## BLOCKERS (Must Fix)

### B-1: Plaintext Error Leakage 🔴
- **Where:** Error messages flow from processors → job state → API response
- **What:** "OCR failed: Unrecognized file format" stored as `failureReason` and returned to client
- **Risk:** Stack traces, plaintext messages, schema structure revealed
- **Fix:** Use opaque error codes only, sanitize before persistence

### B-2: Silent Transform Failures 🔴
- **Where:** [schemaTransform.ts](engine/transform/schemaTransform.ts#L120-L126)
- **What:** Transform function crashes marked as "ambiguous" (not hard failure)
- **Risk:** Corrupted documents accepted, downstream uses wrong defaults
- **Fix:** Separate TRANSFORM_ERROR from AMBIGUOUS, fail on transform crashes

### B-3: Retry Classification Broken 🔴
- **Where:** [retryPolicy.ts](engine/jobs/retryPolicy.ts#L50-L80)
- **What:** No way to identify non-retryable errors (defaults to retryable=true)
- **Risk:** Invalid documents (unsupported format) retried 3x unnecessarily
- **Fix:** Implement structured error codes, default to non-retryable

---

## ACCEPTABLE (OK as-is)

| Finding | Why OK |
|---------|--------|
| **A-1: OCR Stub Nondeterminism** | Stub only, not production |
| **A-2: Offset Map Complexity** | Defensive design, not critical path |
| **A-3: Runtime Ambiguity** | Detected correctly, caller can decide |

---

## DEFERRED (Plan for production)

| Finding | Action |
|---------|--------|
| **D-1: OCR Quality Threshold** | Add confidence check before returning results |
| **D-2: Job Idempotency Race** | Use DB unique constraint (single-process OK now) |
| **D-3: Retry Wall-Clock Cap** | Monitor 90s retry overhead, tune in prod |

---

## IMPACT MATRIX

| Component | Determinism | Silent Failures | Leakage | Retry Safety |
|-----------|-------------|-----------------|---------|--------------|
| OCRAdapter | ✓ (stub) | ⚠️ (no error codes) | ❌ (throws raw errors) | ❌ (no retry flag) |
| normalizeText | ✓ | ✓ | ✓ | N/A |
| schemaTransform | ✓ | ❌ (B-2) | ⚠️ (could appear in transform fn) | N/A |
| worker.ts | ✓ | ✓ | ❌ (B-1 propagates) | ❌ (B-3 classifies wrong) |
| retryPolicy | ✓ | ✓ | ✓ | ❌ (B-3) |
| jobStore | ✓ | ✓ | ⚠️ (B-1 persists) | ✓ |
| API routes | ✓ | ✓ | ❌ (B-1 returns) | ✓ |

---

## REMEDIATION PRIORITY

**Phase 1 (Before Merge):**
1. B-1: Define ProcessingError with error codes
2. B-2: Add failure types to applyRule
3. B-3: Fix retryPolicy to use error codes

**Phase 2 (Production Hardening):**
4. D-1: Add OCR confidence threshold
5. D-2: Implement DB idempotency
6. D-3: Monitor and tune retry delays

---

## CODE FLOW WITH ISSUES MARKED

```
Upload Document
    ↓
OCRAdapter.extractText()
    ├─ ❌ B-1: Throws Error("OCR failed: ...") — should throw ProcessingError
    └─ ❌ B-3: No error code, retryPolicy can't classify
         ↓
worker.processor()
    ├─ normalizeText() ✓
    ├─ schemaTransform()
    │  └─ ❌ B-2: Transform fn error marked ambiguous (not fatal)
    └─ ❌ B-1: Error message passed as-is to retry logic
         ↓
retryPolicy.decide()
    └─ ❌ B-3: Defaults to retryable=true for unknown errors
         ↓
queue.scheduleRetry() OR queue.markFailed()
    └─ ❌ B-1: Raw error message persisted in failureReason
         ↓
API GET /jobs/:jobId
    └─ ❌ B-1: Returns failureReason to client (may contain plaintext)
```

---

## TEST COVERAGE NEEDED

```
✗ Test B-1: Verify error codes used, not messages
✗ Test B-2: Verify transform errors fail job (not ambiguous)
✗ Test B-3: Verify OCR_UNSUPPORTED not retried
✗ Test B-3: Verify HTTP 500 is retried
✗ Test roundtrip: Valid doc → success with artifacts
✗ Test roundtrip: Corrupt OCR → terminal failure (not 3x retry)
✗ Test roundtrip: Corrupt transform → terminal failure
```

---

## FILES TO MODIFY

1. **Create:** `engine/errors.ts` — Define ProcessingError and error codes
2. **Modify:** [engine/cpu/ocrAdapter.ts](engine/cpu/ocrAdapter.ts) — Throw ProcessingError
3. **Modify:** [engine/transform/schemaTransform.ts](engine/transform/schemaTransform.ts) — Add failure types
4. **Modify:** [engine/jobs/retryPolicy.ts](engine/jobs/retryPolicy.ts) — Use error codes, default non-retryable
5. **Modify:** [engine/cpu/worker.ts](engine/cpu/worker.ts) — Sanitize errors before persistence
6. **Modify:** [api-gateway/routes/jobs.ts](api-gateway/routes/jobs.ts) — Return error codes not messages

---

## SIGN-OFF

**Review Date:** 4 January 2026  
**Scope:** CPU-only OCR + Schema Transform (deterministic path)  
**Verdict:** 🔴 DO NOT MERGE — Fix 3 blockers first

See [RED_TEAM_OCR_SCHEMA_REVIEW.md](RED_TEAM_OCR_SCHEMA_REVIEW.md) for full details.
