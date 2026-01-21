# End-to-End Job Execution: Phase-1.5 Environment

## Overview

This document describes a complete end-to-end (E2E) flow through the Rythmiq One Phase-1.5 system:

1. **Document Upload** → blob stored, job created
2. **Job Enqueued** → state transitions to QUEUED
3. **Worker Processes** → OCR + schema transformation
4. **Schema Fetched** → transformer loads schema definition from database
5. **Output Artifact Written** → results persisted
6. **Client Retrieves** → results returned to authenticated user

---

## Prerequisites

### Environment Setup

```bash
# 1. Set up API Gateway (port 3000)
npm install
npm run build
PORT=3000 npm start

# 2. Set up Worker (same environment)
npm run build
npm run worker

# 3. Database: PostgreSQL (configured via DATABASE_URL)
# 4. Authentication: JWT public key configured (JWT_PUBLIC_KEY env var)
```

### Configuration

Required environment variables:
- `DATABASE_URL`: PostgreSQL connection string
- `JWT_PUBLIC_KEY`: Public key for request authentication
- `PORT`: API Gateway port (default: 3000)
- `NODE_ENV`: production or development

---

## API Endpoints

### 1. Upload Document

**Endpoint**: `POST /upload`

**Headers**:
```
Content-Type: application/octet-stream
Content-Length: <bytes>
x-client-request-id: <uuid>
Authorization: Bearer <jwt-token>
```

**Body**: Raw binary document (encrypted payload, server does not inspect contents)

**Expected Response** (201 Created or 200 OK if idempotent):
```json
{
  "blobId": "550e8400-e29b-41d4-a716-446655440000",
  "jobId": "660e8400-e29b-41d4-a716-446655440001",
  "clientRequestId": "user-req-12345",
  "uploadedBytes": 4096
}
```

**Example curl**:
```bash
BLOB_ID="550e8400-e29b-41d4-a716-446655440000"
CLIENT_REQ_ID="user-req-12345"
JWT_TOKEN="eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..."

curl -X POST http://localhost:3000/upload \
  -H "Content-Type: application/octet-stream" \
  -H "x-client-request-id: ${CLIENT_REQ_ID}" \
  -H "Authorization: Bearer ${JWT_TOKEN}" \
  --data-binary @document.pdf \
  | jq .
```

**Job State After Upload**:
- Initial: `CREATED`
- Immediate transition: `QUEUED` (automatically enqueued)

---

### 2. Check Job Status

**Endpoint**: `GET /jobs/:jobId`

**Headers**:
```
Authorization: Bearer <jwt-token>
```

**Expected Response** (200 OK):
```json
{
  "jobId": "660e8400-e29b-41d4-a716-446655440001",
  "state": "QUEUED",
  "retries": 0,
  "createdAt": "2026-01-07T14:32:15.000Z",
  "updatedAt": "2026-01-07T14:32:15.000Z",
  "error": null
}
```

**Example curl**:
```bash
JOB_ID="660e8400-e29b-41d4-a716-446655440001"
JWT_TOKEN="eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..."

curl -X GET http://localhost:3000/jobs/${JOB_ID} \
  -H "Authorization: Bearer ${JWT_TOKEN}" \
  | jq .
```

**State Transitions During Processing**:
```
QUEUED → RUNNING → SUCCEEDED
         (worker picks up)
```

**If Error**:
```json
{
  "state": "FAILED",
  "error": "SCHEMA_NOT_FOUND"
}
```

---

### 3. Processing Pipeline (Worker)

When worker calls `getNextQueued()`, it processes the job through these stages:

#### Stage 1: Fetch Blob
- Read encrypted document from blob storage
- Pass bytes to OCR adapter (no decryption by server)

#### Stage 2: OCR
- Extract text from document
- Possible errors:
  - `OCR_TIMEOUT` (non-retryable)
  - `OCR_UNSUPPORTED_FORMAT` (non-retryable)
  - `OCR_PROCESSING_ERROR` (retryable)

#### Stage 3: Normalize Text
- Normalize extracted text (whitespace, case, etc.)
- Output: `Record<string, string>`

#### Stage 4: Fetch Schema
- Query schema database for `schemaId` and `schemaVersion`
- Default: `schemaId="invoice"`, `schemaVersion="v1"`
- Possible errors:
  - `SCHEMA_NOT_FOUND` (non-retryable)
  - `SCHEMA_ID_MISSING` (non-retryable)

#### Stage 5: Transform to Schema
- Load `SchemaDefinition` from database
- Transform normalized fields to schema structure
- Validate output against schema
- Possible errors:
  - `TRANSFORM_ERROR` (non-retryable)
  - `VALIDATION_ERROR` (non-retryable)
  - `CONFIDENCE_ERROR` (retryable or non-retryable)

#### Stage 6: Write Output Artifact
- Persist schema output as JSON artifact
- Persist OCR artifact
- Update job record with artifact IDs and quality score

---

### 4. Expected State: Processing

While worker is processing:
```bash
curl http://localhost:3000/jobs/${JOB_ID} -H "Authorization: Bearer ${JWT_TOKEN}" | jq '.state'
# Output: "RUNNING"
```

Worker logs output:
```
[14:32:16] Job <jobId> started (attempt 1/4)
[14:32:18] OCR extraction complete
[14:32:18] Normalization complete
[14:32:19] Schema loaded: invoice@v1
[14:32:19] Transformation complete
[14:32:20] Output artifact written
[14:32:20] Job <jobId> succeeded
```

---

### 5. Retrieve Results

**Endpoint**: `GET /jobs/:jobId/results`

**Headers**:
```
Authorization: Bearer <jwt-token>
```

**Expected Response** (200 OK):
```json
{
  "jobId": "660e8400-e29b-41d4-a716-446655440001",
  "schemaOutput": {
    "invoice_number": "INV-2024-001",
    "invoice_date": "2024-01-15",
    "total_amount": "1500.00",
    "vendor_name": "ACME Corp"
  },
  "confidence": {
    "invoice_number": 0.95,
    "invoice_date": 0.88,
    "total_amount": 0.92,
    "vendor_name": 0.91
  },
  "qualityScore": 0.89
}
```

**Example curl**:
```bash
JOB_ID="660e8400-e29b-41d4-a716-446655440001"
JWT_TOKEN="eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..."

curl -X GET http://localhost:3000/jobs/${JOB_ID}/results \
  -H "Authorization: Bearer ${JWT_TOKEN}" \
  | jq .
```

**Availability**:
- Results only available after job state = `SUCCEEDED`
- Returns 404 if job in progress or failed
- Returns 404 if user does not own job

---

## Complete End-to-End Flow

### Request Sequence

```
Client                          API Gateway              Worker              Database
  │                                  │                      │                    │
  ├─ POST /upload ─────────────────>│                      │                    │
  │  (binary blob)                  │                      │                    │
  │                                 ├─ Store blob ────────────────────────────>│
  │                                 │                      │                    │
  │                                 ├─ Create job ────────────────────────────>│
  │                                 │  state: CREATED      │                    │
  │                                 │                      │                    │
  │                                 ├─ Transition: ───────────────────────────>│
  │                                 │  CREATED → QUEUED    │                    │
  │                                 │                      │                    │
  │<─ 201 Created ─────────────────┤                      │                    │
  │  {blobId, jobId}                │                      │                    │
  │                                 │                      │                    │
  ├─ GET /jobs/{jobId} ───────────>│                      │                    │
  │                                 ├─ Get job state ──────────────────────────>│
  │<─ 200 OK ──────────────────────┤                      │                    │
  │  state: "QUEUED"                │                      │                    │
  │                                 │                      │                    │
  │                    (Worker polls or subscription)       │                    │
  │                                 │   ┌─ getNextQueued() │                    │
  │                                 │<──┘                  │                    │
  │                                 │                      ├─ Fetch blob ────>│
  │                                 │                      │<─ Retrieve ────┤
  │                                 │                      │                │
  │                                 ├─ Transition: ───────────────────────>│
  │                                 │  QUEUED → RUNNING    │                │
  │                                 │                      │                │
  │                                 │                      ├─ OCR extract   │
  │                                 │                      ├─ Normalize     │
  │                                 │                      │                │
  │                                 │                      ├─ Fetch schema ───>│
  │                                 │                      │<─ SchemaDef ──────┤
  │                                 │                      │                │
  │                                 │                      ├─ Transform     │
  │                                 │                      ├─ Validate      │
  │                                 │                      │                │
  │                                 │                      ├─ Write output ────>│
  │                                 │                      │  artifact      │
  │                                 │                      │<─ artifact_id ────┤
  │                                 │                      │                │
  │                                 ├─ Update job ────────────────────────>│
  │                                 │  state: SUCCEEDED    │                │
  │                                 │  results populated   │                │
  │                                 │                      │                │
  ├─ GET /jobs/{jobId} ───────────>│                      │                │
  │                                 ├─ Get job state ──────────────────────>│
  │<─ 200 OK ──────────────────────┤                      │                │
  │  state: "SUCCEEDED"             │                      │                │
  │                                 │                      │                │
  ├─ GET /jobs/{jobId}/results ───>│                      │                │
  │                                 ├─ Get job + results ───────────────────>│
  │<─ 200 OK ──────────────────────┤                      │                │
  │  {schemaOutput, confidence}     │                      │                │
```

---

## Error Handling & Transient Errors

### Retryable Errors

The system automatically retries failed jobs with exponential backoff:

| Error Code | Stage | Retryable | Max Attempts |
|------------|-------|-----------|--------------|
| `OCR_PROCESSING_ERROR` | OCR | Yes | 4 |
| `RESOURCE_UNAVAILABLE` | Any | Yes | 4 |
| `TEMPORARY_FAILURE` | Any | Yes | 4 |

**Retry Behavior**:
```
RUNNING → RETRYING (schedule with delay)
         ↓ (after delay)
      QUEUED → RUNNING (retry attempt)
```

**Example**:
```json
{
  "jobId": "660e8400-e29b-41d4-a716-446655440001",
  "state": "RETRYING",
  "retries": 1,
  "error": "OCR_PROCESSING_ERROR"
}
```

### Non-Retryable Errors

Job transitions directly to `FAILED` (terminal):

| Error Code | Stage | Cause |
|------------|-------|-------|
| `OCR_TIMEOUT` | OCR | Document too complex |
| `OCR_UNSUPPORTED_FORMAT` | OCR | Invalid file format |
| `SCHEMA_NOT_FOUND` | TRANSFORM | Schema not in database |
| `TRANSFORM_ERROR` | TRANSFORM | Transformation logic failed |
| `VALIDATION_ERROR` | TRANSFORM | Output validation failed |

**Example**:
```json
{
  "jobId": "660e8400-e29b-41d4-a716-446655440001",
  "state": "FAILED",
  "retries": 0,
  "error": "SCHEMA_NOT_FOUND",
  "updatedAt": "2026-01-07T14:32:35.000Z"
}
```

---

## Observed Behavior: Phase-1.5 Deployment

### Timing

Typical job lifecycle:
- **Upload**: 50–200 ms
- **Enqueue**: 10–50 ms
- **OCR**: 500–2000 ms (document-dependent)
- **Normalization**: 10–50 ms
- **Schema Fetch**: 50–150 ms
- **Transformation**: 100–500 ms
- **Output Write**: 50–200 ms
- **Total E2E**: 800–3500 ms (average: 1.5–2 seconds)

### Idempotency

The system is idempotent for both upload and job creation:
- Duplicate upload with same `clientRequestId` returns same `blobId` (status: 200)
- Duplicate job creation with same `blobId` returns same `jobId` (status: 200)

### Concurrency

- Single-process worker handles one job at a time
- Multiple clients can upload simultaneously (separate blob IDs)
- Job queue processes jobs sequentially by creation time

### State Visibility

Job state is observable at any time via `GET /jobs/:jobId`:
- Polling interval: recommended 2–5 seconds during processing
- Final state stable after terminal transition (SUCCEEDED or FAILED)

---

## Summary

The complete E2E flow demonstrates:

1. ✓ **Crypto-blind upload**: binary payload passes through without inspection
2. ✓ **Job lifecycle**: clean state machine from CREATED → QUEUED → RUNNING → SUCCEEDED
3. ✓ **Worker pipeline**: OCR → normalize → fetch schema → transform → validate → write output
4. ✓ **Schema integration**: database queries for schema definition and transformation
5. ✓ **Result retrieval**: authenticated access to structured output + confidence scores
6. ✓ **Error resilience**: retryable vs. non-retryable distinction with backoff
7. ✓ **User isolation**: jobs tied to userId, results accessible only to owner

---

## Testing Checklist

- [ ] Upload succeeds with valid JWT and binary payload
- [ ] Job created with correct state transitions
- [ ] Worker processes job through all stages
- [ ] Schema correctly loaded from database
- [ ] Output artifact contains expected structure
- [ ] Results include confidence scores and quality metrics
- [ ] Duplicate upload with same `clientRequestId` returns idempotent response
- [ ] Non-existent job returns 404
- [ ] Results unavailable until job state = SUCCEEDED
- [ ] Unauthorized request without JWT rejected
- [ ] Retry logic triggered on transient error (verify state = RETRYING, then QUEUED)
