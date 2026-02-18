# RED TEAM REVIEW: OCR + SCHEMA TRANSFORMATION PIPELINE (CPU)

**Date:** 4 January 2026  
**Scope:** CPU-only OCR adapter and schema transformation (deterministic processing only)  
**Focus:** Silent failures, nondeterminism, schema ambiguity, plaintext leakage, retry safety

---

## EXECUTIVE SUMMARY

The OCR + schema transformation pipeline is **well-structured and deterministic** but contains several issues ranging from **critical to acceptable**. The most severe finding is **plaintext leakage in error messages** that bubble through the system. Schema handling is robust but contains one ambiguity case that needs explicit rules.

---

## FINDINGS

### 🔴 BLOCKER-1: Plaintext Error Messages Leak in Job State & API

**Severity:** BLOCKER  
**Location:** 
- [engine/cpu/worker.ts](engine/cpu/worker.ts#L331-L340) - Error message stored directly in job state
- [engine/jobs/jobStore.ts](engine/jobs/jobStore.ts#L51) - `failureReason` can contain sensitive plaintext
- [api-gateway/routes/jobs.ts](api-gateway/routes/jobs.ts#L35) - `failureReason` returned in API response

**Description:**

When OCR or schema transformation fails, error messages are persisted to job state and returned to clients:

```typescript
// worker.ts, line 327-333
const message = error instanceof Error ? error.message : String(error);
const decision = this.retryPolicy.decide(running.attempt, error);
const reason = decision.reason ?? message;
// ...
const failed = await this.queue.markFailed(running.jobId, reason);
```

```typescript
// jobs.ts (API), line 35
...(job.failureReason && { error: job.failureReason }),
```

**Attack Scenario:**
1. Malicious user uploads PDF that triggers OCR error
2. OCR or downstream processor throws error with embedded plaintext context
3. Error message (containing sensitive details or stack traces) persists in `failureReason`
4. API endpoint returns `failureReason` to client
5. Error logs may also capture plaintext

**Risk:**
- Stack traces may contain file paths, configuration values, or debug data
- Plaintext "missing required field" messages reveal schema structure
- Document content may appear in transformation error messages

**Remediation:**
1. **Never pass raw error messages to job state.** Generate opaque error codes + safe messages.
2. **Sanitize error reasons** before persisting or returning to client.
3. **Log detailed errors only internally** with PII/plaintext redaction.
4. **Return generic messages to API** (e.g., "PROCESSING_FAILED" instead of "Invoice number field missing").

**Example Fix:**
```typescript
const failed = await this.queue.markFailed(
  running.jobId, 
  'OCR_PROCESSING_ERROR'  // Opaque code only
);

// API returns:
error: { code: 'PROCESSING_FAILED', message: 'Unable to process document' }
```

---

### 🔴 BLOCKER-2: Silent Failure Path in Schema Transformation

**Severity:** BLOCKER  
**Location:** [engine/transform/schemaTransform.ts](engine/transform/schemaTransform.ts#L95-L150)

**Description:**

The `applyRule` method can fail silently without proper error propagation:

```typescript
// Line 120-126: Transformation failure marked as "ambiguous" but not fatal
if (rule.transform) {
  try {
    transformedValue = rule.transform(sourceValues);
  } catch {
    transformationFailed = true;
    return {
      success: false,
      value: undefined,
      confidence: 0,
      ambiguous: true,  // ⚠️ Ambiguous vs. Hard Failure
    };
  }
}
```

**Problem:** When a transformation function throws, the error is swallowed and reported as "ambiguous" rather than a hard failure. This conflates two distinct failure modes:

1. **Ambiguous:** Multiple valid interpretations (acceptable, low confidence OK)
2. **Hard Failure:** Transform function error (unacceptable, should fail the entire job)

```typescript
// transform() aggregates failures without distinguishing them:
const success = missing.length === 0;  // Line 77
```

A caller cannot distinguish:
- "Field is legitimately ambiguous (best effort OK)" 
- "Field transformation crashed (document is corrupted)"

**Attack Scenario:**
1. Schema defines `transform` for amount field: `(values) => parseInt(values[0])`
2. OCR extracts garbled text: "123abc"
3. Transform fails silently, marked as "ambiguous"
4. Document accepted with missing critical field
5. Downstream processing assumes valid amount, processes with zeros or nulls

**Risk:**
- Corrupted documents accepted without error
- Downstream systems may use incorrect defaults
- Hard failures masked as soft ambiguities

**Remediation:**
1. **Separate ambiguity detection from transform failures:**
   ```typescript
   return {
     success: false,
     failure: 'TRANSFORM_ERROR',  // vs. 'MISSING' or 'AMBIGUOUS'
     error: error.message,
     confidence: 0,
   };
   ```
2. **Reject documents with transform errors** (not optional).
3. **Return detailed failure reason** so caller can decide retry vs. terminal.

---

### 🟡 BLOCKER-3: Inconsistent Error Code Usage in Retry Policy

**Severity:** BLOCKER  
**Location:** [engine/jobs/retryPolicy.ts](engine/jobs/retryPolicy.ts#L50-L75)

**Description:**

Retry classification uses inconsistent patterns for error detection:

```typescript
// Non-retryable codes (line 25)
const NON_RETRYABLE_CODES = new Set(['VALIDATION_ERROR', 'AUTH_ERROR', 'NOT_FOUND', 'BAD_REQUEST']);

// But retryPolicy.classify() checks:
if (parsed.nonRetryable === true) { ... }  // Flag-based
if (RETRYABLE_STATUS_CODES.has(parsed.status)) { ... }  // HTTP status-based
if (NON_RETRYABLE_CODES.has(String(parsed.code))) { ... }  // Code string-based
```

**Problem:**

1. **Inconsistent error sources:** Workers throw `Error` objects with messages, not structured error codes
2. **No bridge from thrown errors to retry logic:** 
   - OCRAdapter throws `new Error('OCR failed: ...')` 
   - Schema transformer throws in transform function
   - Worker catches and passes to `retryPolicy.decide()`
   - RetryPolicy has no way to identify these as non-retryable

3. **Default to retryable:** Line 80 returns `retryable: true` for unknown errors
   ```typescript
   return { retryable: true, reason: parsed.message, code: parsed.code };
   ```

**Attack Scenario:**
1. OCR consistently fails for invalid PDF format (UNSUPPORTED_FORMAT)
2. Thrown as: `new Error('Unrecognized file format')`
3. RetryPolicy cannot identify this as non-retryable
4. Job retries 3x, wasting CPU and time
5. Eventually fails with unnecessary retry overhead

**Risk:**
- Invalid documents retried endlessly
- Resource waste on retry cycles
- No deterministic failure classification

**Remediation:**
1. **Define structured error types** with explicit retry classification:
   ```typescript
   interface ProcessingError extends Error {
     code: 'OCR_UNSUPPORTED_FORMAT' | 'OCR_CORRUPT' | 'SCHEMA_TRANSFORM_ERROR';
     retryable: boolean;
   }
   ```
2. **Throw structured errors from adapters/transformers:**
   ```typescript
   throw new ProcessingError('...', {
     code: 'OCR_UNSUPPORTED_FORMAT',
     retryable: false
   });
   ```
3. **Match retry policy on error codes, not messages**
4. **Default to non-retryable** for unknown errors (fail fast)

---

### 🟠 ACCEPTABLE-1: Nondeterminism in OCR Stub

**Severity:** ACCEPTABLE (Stub implementation, not production)  
**Location:** [engine/cpu/ocrAdapter.ts](engine/cpu/ocrAdapter.ts#L300-L330)

**Description:**

The OCR stub uses `Date.now()` which is nondeterministic:

```typescript
const startTime = Date.now();
// ... processing ...
const processingTime = Date.now() - startTime;
```

Also, page count is derived from data length:
```typescript
const pageCount = Math.max(1, (data.length % 5) + 1);
```

**Why This Is Acceptable:**
- This is a **stub implementation** for testing
- `processingTime` is metadata, not processed data
- Page count determinism only matters for actual PDF parsing
- Production OCR engine will provide real page metadata

**Production Concern:**
When integrating real OCR (Tesseract, EasyOCR):
1. Ensure OCR always produces same output for same input
2. Never use current time for confidence scores
3. Never use external randomness in field extraction

---

### 🟠 ACCEPTABLE-2: Offset Map Complexity in Text Normalization

**Severity:** ACCEPTABLE (Defensive design)  
**Location:** [engine/transform/normalizeText.ts](engine/transform/normalizeText.ts#L115-L180)

**Description:**

The offset map maintenance through multiple transformations is complex and could introduce offset drift:

```typescript
// Unicode normalization rebuilds offset map from scratch
// Each transformation (removeZeroWidth, normalizeLineBreaks, etc.) 
// generates new offset maps and chains them
```

**Why This Is Acceptable:**
- Offset maps are **not used in the critical path** (OCR → schema)
- Maps are **for traceability**, not decision-making
- Complexity is **defensive** (no silent offset errors)
- Tests would catch offset drift quickly

**Improvement (if used downstream):**
- Add offset map validation tests
- Consider snapshot testing of offset maps for edge cases

---

### 🟠 ACCEPTABLE-3: Schema Ambiguity Not Enforced at Rule Definition

**Severity:** ACCEPTABLE (Mitigated by downstream handling)  
**Location:** [engine/transform/schemaTransform.ts](engine/transform/schemaTransform.ts#L120-L125)

**Description:**

Ambiguity detection is runtime-only:

```typescript
// Ambiguity detected only during transform:
const ambiguous =
  !rule.transform && sourceValues.length > rule.sourceFields.length;
```

Problem: If multiple source fields contain values but rule has no transform, it's ambiguous. But this is only detected **after transformation attempt**, not at schema definition time.

Example schema that will be ambiguous:
```typescript
addField('invoiceNumber', 'invoice_number')  // No explicit rule
// If OCR produces both 'invoice_number' AND 'invoice_id', 
// transformation is ambiguous but not caught at schema build time
```

**Why This Is Acceptable:**
1. **Detection works at runtime** (correct values still produced)
2. **Result clearly marks ambiguous** (`result.ambiguous` array)
3. **Caller can decide** (retry with better rules, or accept with low confidence)
4. **Schema builder could be enhanced** but current approach is safe

---

### 🟡 DEFERRED-1: No Validation of OCR Confidence Scores

**Severity:** DEFERRED  
**Location:** [engine/cpu/ocrAdapter.ts](engine/cpu/ocrAdapter.ts#L334-L346)

**Description:**

OCR adapter returns confidence scores without validation:

```typescript
const confidence = Math.floor((hash.charCodeAt(0) % 100) + 80) / 100; // 0.80-0.99
```

No mechanism to:
1. **Reject low-confidence pages** before schema transformation
2. **Propagate confidence** to schema transformer
3. **Enforce minimum quality threshold** before returning to user

**Risk:**
- Low-confidence OCR text → incorrect schema extraction → corrupted output
- No quality gate before persistence

**Recommendation (Deferred):**
1. Add OCR quality threshold (e.g., reject < 75% confidence pages)
2. Pass page confidence to schema transformer
3. Weight schema field confidence by OCR confidence
4. Fail job if overall quality < threshold

---

### 🟡 DEFERRED-2: Race Condition in Job Idempotency Map

**Severity:** DEFERRED (Single-process only)  
**Location:** [engine/jobs/jobStore.ts](engine/jobs/jobStore.ts#L67-L85)

**Description:**

Job creation is idempotent but has race condition window:

```typescript
const existingJobId = this.jobIdempotencyMap.get(idempotencyKey);
if (existingJobId !== undefined) {
  return { jobId: existingJobId, isNewJob: false };
}
// ⚠️ Race: New request arrives here for same idempotency key
const jobId = uuidv4();
```

**Why Deferred:**
- Single-process in-memory implementation
- Not visible in async environment without concurrency
- Production DB-backed implementation must handle this with transactions

**Action for Production:**
- Use database unique constraint on `(userId, clientRequestId)`
- INSERT OR IGNORE pattern with RETURNING clause
- Or implement mutex on idempotency key

---

### 🟡 DEFERRED-3: No Bounds on Retry Delays

**Severity:** DEFERRED  
**Location:** [engine/jobs/retryPolicy.ts](engine/jobs/retryPolicy.ts#L85-L95)

**Description:**

While max delay is capped, there's no backoff cap at wall-clock time:

```typescript
const raw = this.baseDelayMs * 2 ** (nextAttemptNumber - 1);
return Math.min(raw, this.maxDelayMs);  // Caps to 30s
```

With 3 retries at 30s each = 90 seconds of retry overhead per job. For high-volume systems, this could be inefficient.

**Why Deferred:**
- 30s max delay is reasonable for document processing
- Early termination on non-retryable errors (once fixed per BLOCKER-3)
- Can be tuned per deployment

---

## SUMMARY TABLE

| ID | Finding | Severity | Category | Status |
|---|---|---|---|---|
| B-1 | Plaintext error leakage | BLOCKER | Plaintext leak | Must fix |
| B-2 | Silent transform failures | BLOCKER | Silent failure | Must fix |
| B-3 | Inconsistent retry classification | BLOCKER | Retry safety | Must fix |
| A-1 | Nondeterminism in stub | ACCEPTABLE | Determinism | OK (stub) |
| A-2 | Offset map complexity | ACCEPTABLE | Robustness | OK |
| A-3 | Runtime ambiguity detection | ACCEPTABLE | Schema handling | OK |
| D-1 | No OCR quality threshold | DEFERRED | Quality gates | Plan for prod |
| D-2 | Job idempotency race condition | DEFERRED | Idempotency | Fix for production DB |
| D-3 | No retry wall-clock cap | DEFERRED | Retry tuning | Monitor in prod |

---

## REQUIRED ACTIONS (BLOCKERS)

### Action 1: Implement Error Code System
- [ ] Define `ProcessingError` interface with retryable flag
- [ ] Update `OCRAdapter` to throw `ProcessingError` (not generic `Error`)
- [ ] Update schema transformer to throw `ProcessingError`
- [ ] Update worker.ts to catch and classify by error code, not message
- [ ] Sanitize error messages before persisting to `failureReason`

### Action 2: Separate Transform Failures from Ambiguity
- [ ] Add `failure` field to rule application result (TRANSFORM_ERROR vs. MISSING vs. AMBIGUOUS)
- [ ] Update schema transformer to require explicit decision on transform failures
- [ ] Return structured failure reason to worker
- [ ] Fail job (non-retryable) on transform errors

### Action 3: Fix Retry Policy Classification
- [ ] Change default classification to `retryable: false`
- [ ] Implement error code matching, not message parsing
- [ ] Add comprehensive test coverage for all error paths

---

## IMPLEMENTATION CHECKLIST

```markdown
# Blocking Issues (Must Complete Before Production)

- [ ] **B-1: Error Plaintext Leakage**
  - [ ] Define error code enum (OCR_UNSUPPORTED, OCR_CORRUPT, SCHEMA_TRANSFORM_ERROR, etc.)
  - [ ] Create ProcessingError class with retryable flag
  - [ ] Update ocrAdapter to throw ProcessingError with codes
  - [ ] Update normalizeText and schemaTransform to throw ProcessingError
  - [ ] Update worker.ts to sanitize errors before job state persistence
  - [ ] Return generic codes to API (never raw error messages)
  - [ ] Update API endpoint to return { code, message } not { failureReason }
  - [ ] Audit logs for plaintext leakage (check console.* calls)

- [ ] **B-2: Transform Failure Handling**
  - [ ] Add 'failure' enum to applyRule return type
  - [ ] Distinguish TRANSFORM_ERROR from MISSING or AMBIGUOUS
  - [ ] Update transform() to propagate failure types
  - [ ] Update worker.ts to treat transform errors as terminal (non-retryable)
  - [ ] Test: Verify corrupted transform functions don't cause silent passes

- [ ] **B-3: Retry Classification**
  - [ ] Default classify() to { retryable: false }
  - [ ] Match on error.code (ProcessingError), not error.message
  - [ ] Test: Verify OCR_UNSUPPORTED is not retried
  - [ ] Test: Verify HTTP 5xx errors are retried
  - [ ] Test: Verify malformed JSON errors are not retried

# Acceptable (Monitor, No Immediate Action)

- [ ] **A-1: OCR Stub Nondeterminism** - Acceptable, stub only
- [ ] **A-2: Offset Map Complexity** - Add unit tests for offset tracking
- [ ] **A-3: Runtime Ambiguity** - Document in schema builder

# Deferred (Production Checklist)

- [ ] **D-1: OCR Quality Threshold** - Add confidence check before persistence
- [ ] **D-2: Job Idempotency DB Race** - Use DB unique constraint + INSERT OR IGNORE
- [ ] **D-3: Retry Wall-Clock Cap** - Monitor retry overhead in production
```

---

## APPENDIX: Code Examples for Remediation

### Example 1: Structured Error Handling

```typescript
// Define error types
enum ProcessingErrorCode {
  OCR_UNSUPPORTED_FORMAT = 'OCR_UNSUPPORTED_FORMAT',
  OCR_CORRUPT_DATA = 'OCR_CORRUPT_DATA',
  OCR_PROCESSING_FAILED = 'OCR_PROCESSING_FAILED',
  SCHEMA_TRANSFORM_ERROR = 'SCHEMA_TRANSFORM_ERROR',
  SCHEMA_MISSING_REQUIRED = 'SCHEMA_MISSING_REQUIRED',
}

class ProcessingError extends Error {
  constructor(
    message: string,
    public code: ProcessingErrorCode,
    public retryable: boolean
  ) {
    super(message);
    this.name = 'ProcessingError';
  }
}

// Usage in OCRAdapter
if (!detectedFormat) {
  throw new ProcessingError(
    'Unrecognized file format',
    ProcessingErrorCode.OCR_UNSUPPORTED_FORMAT,
    false  // Non-retryable
  );
}

// Usage in worker
try {
  const result = await this.processor(sourceBytes, running.userId);
} catch (error) {
  const decision = this.retryPolicy.decide(running.attempt, error);
  // Now retryPolicy.classify() uses error.code and error.retryable flag
}
```

### Example 2: Transform Failure Handling

```typescript
interface RuleApplicationResult {
  success: boolean;
  value: any;
  confidence: number;
  failure?: 'MISSING' | 'AMBIGUOUS' | 'TRANSFORM_ERROR';
  error?: string;
}

private applyRule(...): RuleApplicationResult {
  // ...
  if (rule.transform) {
    try {
      transformedValue = rule.transform(sourceValues);
    } catch (err) {
      return {
        success: false,
        value: undefined,
        confidence: 0,
        failure: 'TRANSFORM_ERROR',  // Explicit failure type
        error: `Transform function failed: ${err instanceof Error ? err.message : String(err)}`,
      };
    }
  }
  // ...
}

public transform(normalized: NormalizedText): TransformResult {
  // ...
  for (const [targetField, rule] of Object.entries(this.schema.fields)) {
    const result = this.applyRule(targetField, rule, normalized);
    
    if (result.success) {
      structured[targetField] = result.value;
      confidence[targetField] = result.confidence;
    } else if (result.failure === 'TRANSFORM_ERROR') {
      // Treat as unrecoverable—caller should NOT retry
      throw new ProcessingError(
        result.error,
        ProcessingErrorCode.SCHEMA_TRANSFORM_ERROR,
        false  // Non-retryable
      );
    } else if (rule.required) {
      missing.push(targetField);
    }
  }
}
```

### Example 3: Sanitized Error Messages

```typescript
// In worker.ts
catch (error) {
  let decision;
  let publicMessage: string;

  if (error instanceof ProcessingError) {
    decision = this.retryPolicy.decide(running.attempt, error);
    publicMessage = sanitizeErrorMessage(error.code);  // Use code, not message
  } else {
    // Unknown error—treat as non-retryable by default
    decision = { shouldRetry: false, ... };
    publicMessage = 'PROCESSING_FAILED';
  }

  if (decision.shouldRetry) {
    const nextVisibleAt = new Date(Date.now() + decision.delayMs);
    await this.queue.scheduleRetry(running.jobId, nextVisibleAt, publicMessage);
  } else {
    await this.queue.markFailed(running.jobId, publicMessage);  // Code only
  }
}

function sanitizeErrorMessage(code: ProcessingErrorCode): string {
  const codeMap: Record<ProcessingErrorCode, string> = {
    [ProcessingErrorCode.OCR_UNSUPPORTED_FORMAT]: 'UNSUPPORTED_FORMAT',
    [ProcessingErrorCode.OCR_CORRUPT_DATA]: 'CORRUPT_DATA',
    [ProcessingErrorCode.OCR_PROCESSING_FAILED]: 'OCR_FAILED',
    [ProcessingErrorCode.SCHEMA_TRANSFORM_ERROR]: 'SCHEMA_ERROR',
    [ProcessingErrorCode.SCHEMA_MISSING_REQUIRED]: 'INCOMPLETE_DATA',
  };
  return codeMap[code] || 'UNKNOWN_ERROR';
}
```

---

## SIGN-OFF

**Red Team:** Security Review  
**Date:** 4 January 2026  
**Status:** 3 BLOCKERS, 3 ACCEPTABLE, 3 DEFERRED

**Recommendation:** Do not merge to production until BLOCKERS are resolved.

---
