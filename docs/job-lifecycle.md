# Job Lifecycle Specification

## Overview

This document defines the state machine for document processing jobs in the system. Jobs are CPU-based document processing tasks that are crypto-blind and follow a strict lifecycle with explicit state transitions.

---

## Job States

### State Definitions

| State | Type | Description |
|-------|------|-------------|
| **CREATED** | Non-terminal | Job has been created but not yet submitted to the queue |
| **QUEUED** | Non-terminal | Job is waiting in the processing queue |
| **RUNNING** | Non-terminal | Job is actively being processed |
| **SUCCEEDED** | Terminal | Job completed successfully |
| **FAILED** | Terminal | Job failed permanently (non-retryable or max retries exhausted) |
| **RETRYING** | Non-terminal | Job is scheduled for retry after a transient failure |

### State Classification

**Terminal States** (processing cannot continue):
- `SUCCEEDED` — successful completion
- `FAILED` — permanent failure

**Non-Terminal States** (job lifecycle is active):
- `CREATED` — initial state
- `QUEUED` — awaiting processing
- `RUNNING` — active processing
- `RETRYING` — awaiting retry attempt

---

## Valid State Transitions

```
CREATED → QUEUED
  Trigger: Job submission
  
QUEUED → RUNNING
  Trigger: Processing begins
  
RUNNING → SUCCEEDED
  Trigger: Processing completed successfully
  
RUNNING → FAILED
  Trigger: Unrecoverable error or max retries exceeded
  
RUNNING → RETRYING
  Trigger: Transient/retryable error and retries remaining
  
RETRYING → QUEUED
  Trigger: Retry delay elapsed
  
QUEUED → FAILED
  Trigger: Resource exhaustion or cancellation
```

### Invalid Transitions

The following transitions are **not allowed**:
- Direct state reversions (e.g., `QUEUED → CREATED`)
- Backward progression (e.g., `SUCCEEDED → QUEUED`)
- Transitions from terminal states (except system cleanup)
- `RUNNING → QUEUED` (without retry)
- `CREATED → RUNNING` (must go through QUEUED)

---

## Failure Handling

### Retryable Failures

Failures that may succeed on retry:
- Transient system errors (e.g., temporary resource unavailable)
- Timeout or deadline exceeded
- Queue overload
- Temporary external dependency unavailable

**Action**: Transition to `RETRYING`, then back to `QUEUED` after backoff delay

### Non-Retryable Failures

Failures that will not benefit from retry:
- Invalid input document (corrupted, unsupported format)
- Job validation failure
- Processing timeout (permanent, not transient)
- Configuration error
- Resource limits exceeded (quota, file size, complexity)

**Action**: Transition directly to `FAILED` (terminal)

---

## Retry Policy

### Simple Max Retry Policy

```
Maximum Retries: 3
Backoff Strategy: Fixed 1-second delay
Retry Condition: Error is classified as retryable AND retry count < max
```

### Retry Count Tracking

Each job maintains:
- `retryCount`: Current number of completed retry attempts (0 initially)
- `maxRetries`: Maximum allowed retries (constant = 3)
- `lastError`: Error message/code from most recent failure

### Retry Transition Logic

```
IF error_is_retryable AND retryCount < maxRetries:
  retryCount += 1
  state = RETRYING
  schedule_retry_after(1 second)
ELSE:
  state = FAILED  // terminal
```

---

## State Machine Diagram

```
┌─────────┐
│ CREATED │
└────┬────┘
     │ submit()
     ▼
┌─────────┐
│ QUEUED  │
└────┬────┘
     │ start_processing()
     ▼
┌─────────────┐
│   RUNNING   │
└──┬──────┬──┘
   │      │
   │      └─── transient_error() ──────┐
   │                                   │
   │ success()                     ┌───────────┐
   │                               │ RETRYING  │
   │                               └─────┬─────┘
   │                                     │ retry_eligible()
   │                                     │ retryCount < maxRetries
   │                                     │ wait 1 second
   │                                     ▼
   │                               ┌─────────┐
   │                               │ QUEUED  │
   │                               └────┬────┘
   │                                    │ restart_processing()
   │                                    ▼
   │          ┌──────────────────────┌─────────┐
   │          │                      │ RUNNING │
   │          │                      └────┬────┘
   │          │ (retry loop)             │
   │          └──────────────────────────┘
   │
   │ terminal_error() OR
   │ (transient_error() AND retryCount >= maxRetries)
   │
   ▼
┌──────────┐
│ FAILED   │ (terminal)
└──────────┘

   success()
   ▼
┌──────────────┐
│ SUCCEEDED    │ (terminal)
└──────────────┘
```

---

## Job Metadata

Every job carries:

| Field | Type | Mutable | Notes |
|-------|------|---------|-------|
| `jobId` | UUID | No | Unique identifier, immutable |
| `state` | State | Yes | Current lifecycle state |
| `createdAt` | Timestamp | No | Job creation time |
| `startedAt` | Timestamp | Yes | When processing began (null until RUNNING) |
| `completedAt` | Timestamp | Yes | When job reached terminal state (null until SUCCEEDED/FAILED) |
| `retryCount` | Integer | Yes | Number of retry attempts (0–3) |
| `maxRetries` | Integer | No | Always 3 for this policy |
| `lastError` | String | Yes | Most recent error message (null on success) |
| `errorType` | Enum | Yes | RETRYABLE or TERMINAL (null on success) |

---

## Guarantees

### Safety Properties

- **No duplicate processing**: Once `RUNNING`, a job will not be assigned to another worker until it fails and retries
- **Bounded retries**: Maximum 3 automatic retry attempts
- **Terminal finality**: `SUCCEEDED` and `FAILED` states are permanent
- **No orphaned jobs**: Every job reaches a terminal state or is explicitly cancelled

### Ordering Guarantees

- Jobs progress forward through states (never backward except retry restart)
- State transitions are atomic
- Retry backoff prevents immediate re-queue storm

---

## Examples

### Successful Processing

```
CREATED → QUEUED → RUNNING → SUCCEEDED (no errors)
```

### Failure with Successful Retry

```
CREATED
  → QUEUED
    → RUNNING (transient error: timeout)
      → RETRYING (retryCount = 1)
        → QUEUED (after 1 second)
          → RUNNING (retry attempt 1)
            → SUCCEEDED ✓
```

### Failure Exhausting Retries

```
CREATED
  → QUEUED
    → RUNNING (transient error: temporary unavailable)
      → RETRYING (retryCount = 1)
        → QUEUED
          → RUNNING (transient error again)
            → RETRYING (retryCount = 2)
              → QUEUED
                → RUNNING (transient error again)
                  → RETRYING (retryCount = 3)
                    → QUEUED
                      → RUNNING (transient error, but retryCount >= maxRetries)
                        → FAILED (non-retryable, exhausted retries) ✗
```

### Non-Retryable Failure

```
CREATED
  → QUEUED
    → RUNNING (invalid document format)
      → FAILED ✗ (non-retryable, no retry attempt)
```

---

## Notes

- This specification is **payload-agnostic**: job state transitions do not depend on document content, encryption state, or schema validation
- **CPU-only**: No GPU scheduling states exist in this model
- **Processing-blind**: The system does not distinguish between document types, processing algorithms, or OCR details
- **Cancellation**: Explicit cancellation is not modeled here; treat as out-of-band operation transitioning to `FAILED`
