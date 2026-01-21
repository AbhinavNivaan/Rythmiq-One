# OCR + SCHEMA PIPELINE RED TEAM REVIEW — EXECUTIVE SUMMARY

**Date:** 4 January 2026 | **Status:** 🔴 DO NOT MERGE (3 Blockers)

---

## VERDICT

```
┌─────────────────────────────────────────┐
│  FINDINGS CLASSIFICATION                │
├─────────────────────────────────────────┤
│  🔴 BLOCKERS (Must fix):            3   │
│  🟠 DEFERRED (Production only):      3   │
│  🟢 ACCEPTABLE (OK as-is):           3   │
└─────────────────────────────────────────┘
```

---

## THE 3 BLOCKERS (Stop the build until fixed)

### 🔴 BLOCKER-1: Plaintext Error Messages Leak in API
**Problem:** Error messages flow from processors → job state → API response  
**Example:** `error: "OCR failed: Unrecognized file format"` returned to client  
**Risk:** Stack traces, debug info, schema structure revealed  
**Files:** [engine/cpu/worker.ts](engine/cpu/worker.ts#L327), [engine/jobs/jobStore.ts](engine/jobs/jobStore.ts#L51), [api-gateway/routes/jobs.ts](api-gateway/routes/jobs.ts#L35)  
**Fix:** Use opaque error codes (e.g., `OCR_UNSUPPORTED_FORMAT`), never raw messages

---

### 🔴 BLOCKER-2: Transform Failures Silent (Marked as "Ambiguous")
**Problem:** When a schema transform function crashes, it's marked as "ambiguous" not fatal  
**Example:**
```
Transform: parseInt(value)  // crashes on "123abc"
Result: { success: false, ambiguous: true }  // Should be FAILURE, not ambiguous
```
**Risk:** Corrupted documents accepted with missing critical fields  
**File:** [engine/transform/schemaTransform.ts](engine/transform/schemaTransform.ts#L120-L126)  
**Fix:** Distinguish TRANSFORM_ERROR from AMBIGUOUS, fail on errors

---

### 🔴 BLOCKER-3: Retry Policy Can't Identify Non-Retryable Errors
**Problem:** No way to tell retry policy "this error should not be retried"  
**Example:** Unsupported PDF format → job retries 3x unnecessarily  
**Risk:** Resource waste, no fast-fail for invalid documents  
**File:** [engine/jobs/retryPolicy.ts](engine/jobs/retryPolicy.ts#L80) defaults to `retryable: true`  
**Fix:** Implement structured error codes with `retryable` flag

---

## ACCEPTABLE (No action needed)

| Issue | Why OK |
|-------|--------|
| **A-1: OCR stub nondeterminism** | Only in test stub, production OCR will be deterministic |
| **A-2: Offset map complexity** | Not in critical path, defensive design is fine |
| **A-3: Runtime ambiguity detection** | Works correctly, caller can decide action |

---

## DEFERRED (Plan for production)

| Issue | Action | Priority |
|-------|--------|----------|
| **D-1: No OCR quality threshold** | Add confidence check before returning results | Medium |
| **D-2: Job idempotency race condition** | Use DB unique constraint + INSERT OR IGNORE | Medium |
| **D-3: No retry wall-clock cap** | Monitor 90s retry overhead, tune in production | Low |

---

## IMPACT BY COMPONENT

```
Component              Determinism  Leakage  Silent Failures  Retry Safety
───────────────────────────────────────────────────────────────────────────
OCRAdapter             ✓            ❌ B-1   ⚠️ B-3          ❌ B-3
normalizeText          ✓            ✓        ✓               N/A
schemaTransform        ✓            ✓        ❌ B-2          N/A
worker.ts             ✓            ❌ B-1   ✓               ❌ B-3
retryPolicy           ✓            ✓        ✓               ❌ B-3
jobStore              ✓            ⚠️ B-1   ✓               ✓
API routes            ✓            ❌ B-1   ✓               ✓
```

---

## ATTACK SCENARIOS

### Scenario 1: Plaintext Leak (B-1)
```
1. Attacker uploads malformed PDF
2. OCR throws: Error("Invalid PDF: magic bytes [0x00, 0x01, 0x02] not recognized")
3. Message stored in job.failureReason
4. Attacker calls GET /jobs/{jobId}
5. Response contains: { error: "Invalid PDF: magic bytes [0x00, 0x01, 0x02]..." }
6. Attacker learns system's validation rules, OCR lib internals
```

### Scenario 2: Corrupted Document Accepted (B-2)
```
1. OCR extracts: { amount_text: "123abc" }
2. Schema transform has: transform: (v) => parseInt(v[0])
3. Function crashes, marked as "ambiguous"
4. Document accepted with empty/null amount field
5. Downstream billing system uses default $0.00
6. Attacker gets free service
```

### Scenario 3: Retry Hammer (B-3)
```
1. Attacker uploads 100 PDFs with unsupported format (BMP)
2. Each job: 3 retry attempts × 30s = 90s overhead
3. System wastes CPU on guaranteed failures
4. 100 jobs × 90s = 2.5 hours of unnecessary processing
5. DoS via invalid document upload
```

---

## REMEDIATION ROADMAP

### Phase 1: Implement Structured Errors (1-2 days)
```
✓ Create ProcessingError class with error codes
✓ Update OCRAdapter to throw ProcessingError
✓ Update schema transformer to throw ProcessingError
✓ Update worker to sanitize errors (code only, not message)
```

### Phase 2: Fix Transform Failure Handling (1 day)
```
✓ Add failure types to applyRule (MISSING vs. AMBIGUOUS vs. TRANSFORM_ERROR)
✓ Make transform errors terminal (non-retryable)
✓ Update transformer.transform() to propagate failures
```

### Phase 3: Fix Retry Policy (1 day)
```
✓ Default classify() to retryable: false
✓ Match on error.code (ProcessingError), not message
✓ Add comprehensive test coverage
```

### Phase 4: Testing & Validation (2 days)
```
✓ Run new test suites (B-1, B-2, B-3 coverage)
✓ Verify no regressions
✓ Code review and sign-off
```

**Total: 5-6 days to fix all blockers**

---

## FILES CREATED BY RED TEAM

1. [RED_TEAM_OCR_SCHEMA_REVIEW.md](RED_TEAM_OCR_SCHEMA_REVIEW.md) — Full detailed analysis (6000 words)
2. [RED_TEAM_OCR_SCHEMA_QUICK_REFERENCE.md](RED_TEAM_OCR_SCHEMA_QUICK_REFERENCE.md) — 1-page reference
3. [RED_TEAM_OCR_SCHEMA_TEST_PLAN.md](RED_TEAM_OCR_SCHEMA_TEST_PLAN.md) — Complete test coverage spec

---

## NEXT STEPS

**For Engineering Team:**
1. Review [RED_TEAM_OCR_SCHEMA_QUICK_REFERENCE.md](RED_TEAM_OCR_SCHEMA_QUICK_REFERENCE.md) (5 min read)
2. Review [RED_TEAM_OCR_SCHEMA_REVIEW.md](RED_TEAM_OCR_SCHEMA_REVIEW.md) (30 min for details)
3. Implement fixes in this order:
   - Create `engine/errors.ts` with ProcessingError
   - Update all processors to throw ProcessingError
   - Update worker.ts to sanitize errors
   - Update retryPolicy.ts for structured classification
   - Add test suite from [RED_TEAM_OCR_SCHEMA_TEST_PLAN.md](RED_TEAM_OCR_SCHEMA_TEST_PLAN.md)

**For Security Team:**
- Flag: Plaintext leakage in logs (check for console.log of extracted text)
- Flag: Retry policy may DoS on attacker-uploaded invalid documents
- Recommend: Audit all error messages in production before merge

**For Leadership:**
- Status: Code quality is good, determinism is solid, architecture is sound
- Issue: 3 non-trivial security bugs must be fixed
- Timeline: 5-6 days to remediation + testing
- Recommendation: Do not merge until blockers resolved

---

## KEY QUOTES FROM REVIEW

> "The OCR + schema transformation pipeline is **well-structured and deterministic** but contains several issues ranging from **critical to acceptable**."

> "**Never pass raw error messages to job state.** Generate opaque error codes + safe messages."

> "When a transformation function throws, the error is swallowed and reported as 'ambiguous' rather than a hard failure. This conflates two distinct failure modes."

> "Default to **non-retryable** for unknown errors (fail fast)"

---

## CHECKLIST FOR MERGE

- [ ] All 3 blockers fixed and tested
- [ ] Test suite passes (TC-1.1 through TC-5.3)
- [ ] No plaintext in job state or API responses
- [ ] Transform errors are terminal (not retried)
- [ ] Error codes used everywhere (never raw messages)
- [ ] Security team sign-off
- [ ] Code review by 2+ engineers

---

**Review Conducted By:** Red Team  
**Date:** 4 January 2026  
**Scope:** CPU-only OCR + schema transformation pipeline  
**Verdict:** 🔴 **BLOCKER** — Do not merge until issues resolved

For questions or clarifications, see the detailed review documents.
