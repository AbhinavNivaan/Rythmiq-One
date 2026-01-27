# Rythmiq One — Project Handoff Document
## Session Date: January 26, 2026

---

## Executive Summary

This document captures all significant architectural changes and implementations made during today's development session. The work focused on three major areas:

1. **DigitalOcean Spaces Storage Architecture** — A complete storage layer for artifact management
2. **Camber Worker Integration** — CPU-based document processing with webhook callbacks
3. **API Gateway Enhancements** — Service layer improvements and webhook handling

---

## Table of Contents

1. [DigitalOcean Spaces Storage Architecture](#1-digitalocean-spaces-storage-architecture)
2. [Worker Infrastructure](#2-worker-infrastructure)
3. [Camber Webhook Integration](#3-camber-webhook-integration)
4. [Database Schema Updates](#4-database-schema-updates)
5. [Configuration & Environment](#5-configuration--environment)
6. [Testing & Verification](#6-testing--verification)
7. [Known Issues & Next Steps](#7-known-issues--next-steps)
8. [File Manifest](#8-file-manifest)

---

## 1. DigitalOcean Spaces Storage Architecture

### Overview
Implemented a production-ready DigitalOcean Spaces integration using boto3 with S3v4 signatures. The architecture enforces strict path validation to prevent security vulnerabilities.

### Key Components

#### 1.1 Shared Path Validation (`shared/path_validation.py`)
**Single Source of Truth** for all storage path logic. Both API and Worker import from this module.

```
Storage Path Structure:
├── raw/{user_id}/{job_id}/{timestamp}_{filename}.enc    # User uploads
├── master/{user_id}/{document_id}/{document_id}.enc     # Processed master docs
└── output/{user_id}/{job_id}/{timestamp}_output.zip.enc # Final deliverables
```

**Security Features:**
- UUIDv4 validation for user_id, job_id, document_id
- No absolute paths (rejects leading `/`)
- No path traversal (`..` patterns blocked)
- No null bytes
- Filename sanitization (alphanumeric + `._-` only)
- Maximum 128 character filename length

#### 1.2 API Storage Service (`app/api/services/storage.py`)
Handles presigned URL generation for client-side uploads/downloads.

**Key Methods:**
| Method | Purpose | Expiry |
|--------|---------|--------|
| `generate_upload_url()` | Presigned PUT for uploads | Configurable (default 1hr) |
| `generate_download_url()` | Presigned GET for downloads | Configurable (default 1hr) |
| `generate_output_download_url()` | ZIP download URLs | 24 hours |
| `fetch_object()` | Direct S3 GET | N/A |
| `upload_object()` | Direct S3 PUT | N/A |
| `object_exists()` | HEAD check | N/A |

#### 1.3 Worker Spaces Client (`worker/storage/spaces_client.py`)
Worker-specific implementation with explicit artifact source validation.

**Critical Design Decision:**
```python
def validate_artifact_source(artifact_url, raw_path) -> Literal["url", "path"]:
    """
    EXACTLY ONE source must be provided. Both or neither = error.
    This prevents silent footguns with ambiguous artifact sources.
    """
```

---

## 2. Worker Infrastructure

### Overview
Complete CPU-based document processing pipeline implemented with strict execution contracts.

### Execution Contract (HARD REQUIREMENTS)
- Read **exactly one** JSON payload from STDIN
- Produce **exactly one** JSON payload to STDOUT
- Exit with code **0** on success OR handled failure
- **NEVER** crash the process
- **NEVER** throw unhandled exceptions
- No global state, no threads, no retries, no daemons

### Processing Pipeline

```
FETCH → DECODE → QUALITY → ENHANCE → OCR → SCHEMA → UPLOAD
  │        │        │         │       │       │        │
  └── Download artifact from Spaces (signed URL or path)
           └── Decode image bytes to OpenCV array
                    └── CPU-only quality metrics (Laplacian, histogram)
                              └── Orientation correction, denoising, CLAHE
                                       └── PaddleOCR text extraction
                                               └── Resize, DPI, compression
                                                        └── Upload master + preview
```

### Key Files

| File | Purpose |
|------|---------|
| `worker/worker.py` | Main entry point, orchestrates pipeline |
| `worker/models.py` | Frozen dataclass contracts for I/O |
| `worker/errors.py` | Structured error handling with codes |
| `worker/processors/quality.py` | Laplacian variance, histogram analysis |
| `worker/processors/ocr.py` | PaddleOCR integration (CPU-only) |
| `worker/processors/enhancement.py` | CLAHE, denoising, orientation |
| `worker/processors/schema.py` | Pixel-perfect resize, compression loop |

### Input Payload Contract

```json
{
  "job_id": "uuid-v4",
  "user_id": "uuid-v4",
  "portal_schema": {
    "id": "schema-uuid",
    "name": "NEET 2026",
    "version": 1,
    "schema_definition": {
      "target_width": 200,
      "target_height": 230,
      "target_dpi": 200,
      "max_kb": 100,
      "filename_pattern": "{job_id}",
      "output_format": "jpeg",
      "quality": 85
    }
  },
  "input": {
    "artifact_url": "https://...",  // OR
    "raw_path": "raw/user/job/file.enc",
    "mime_type": "image/jpeg",
    "original_filename": "photo.jpg"
  },
  "storage": {
    "bucket": "rythmiq-production",
    "region": "nyc3",
    "endpoint": "https://nyc3.digitaloceanspaces.com"
  }
}
```

### Output Payload Contract

**Success:**
```json
{
  "status": "success",
  "job_id": "uuid-v4",
  "quality_score": 0.87,
  "warnings": ["Low OCR confidence: 0.65"],
  "artifacts": {
    "master_path": "master/user/job/job.enc",
    "preview_path": "output/user/job/preview.jpg"
  },
  "metrics": {
    "ocr_confidence": 0.65,
    "processing_ms": 2340
  }
}
```

**Failure:**
```json
{
  "status": "failed",
  "job_id": "uuid-v4",
  "error": {
    "code": "OCR_TIMEOUT",
    "stage": "ocr",
    "message": "OCR processing exceeded timeout",
    "retryable": true
  }
}
```

### Error Code Reference

| Code | Stage | Retryable | Description |
|------|-------|-----------|-------------|
| `PAYLOAD_MISSING` | init | No | Empty STDIN |
| `PAYLOAD_INVALID` | init | No | Malformed JSON |
| `FETCH_FAILED` | fetch | No | HTTP error downloading |
| `FETCH_TIMEOUT` | fetch | **Yes** | Download timeout |
| `DECODE_FAILED` | decode | No | Image decode failure |
| `OCR_FAILED` | ocr | No | PaddleOCR error |
| `OCR_TIMEOUT` | ocr | **Yes** | OCR processing timeout |
| `SCHEMA_FAILED` | schema | No | Resize/compression error |
| `SIZE_EXCEEDED` | schema | No | Cannot meet max_kb |
| `UPLOAD_FAILED` | upload | **Yes** | S3 PUT error |

---

## 3. Camber Webhook Integration

### Overview
Bidirectional integration with Camber for async job execution.

### Architecture Flow

```
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│   Client App    │      │   API Gateway   │      │  Camber Worker  │
└────────┬────────┘      └────────┬────────┘      └────────┬────────┘
         │                        │                        │
         │ POST /jobs            │                        │
         │───────────────────────>│                        │
         │                        │ Submit to Camber      │
         │                        │───────────────────────>│
         │                        │                        │
         │ 202 Accepted          │                        │
         │<───────────────────────│                        │
         │                        │                        │
         │                        │         (Processing)   │
         │                        │                        │
         │                        │ POST /internal/webhooks/camber
         │                        │<───────────────────────│
         │                        │                        │
         │                        │ 200 OK                │
         │                        │───────────────────────>│
         │                        │                        │
         │ Poll GET /jobs/{id}   │                        │
         │───────────────────────>│                        │
         │                        │                        │
         │ 200 (completed)       │                        │
         │<───────────────────────│                        │
```

### Webhook Endpoint: `POST /internal/webhooks/camber`

**Authentication:**
- Header: `X-Webhook-Secret: {WEBHOOK_SECRET}`
- Constant-time HMAC comparison to prevent timing attacks

**Request Body:**
```json
{
  "camber_job_id": "camber-internal-id",
  "job_id": "uuid-v4",
  "status": "success" | "failed",
  "result": { /* Worker STDOUT content */ }
}
```

**Key Features:**
1. **Idempotent** — Safe to replay; jobs in terminal states are acknowledged silently
2. **State Machine Enforcement** — Only `processing → completed` or `processing → failed`
3. **Output Packaging** — On success, creates ZIP of artifacts in `output/`
4. **Error Details Preserved** — Failed job error details stored in `jobs.error_details`

### Camber Service Client (`app/api/services/camber.py`)

```python
class CamberService:
    """Async client for Camber worker API."""
    
    async def submit_job(job_id: UUID, payload: dict) -> str:
        """Submit job, returns camber_job_id."""
    
    async def get_job_status(camber_job_id: str) -> dict:
        """Poll status from Camber."""
```

**Timeout Configuration:**
- Connect: 5 seconds
- Read: 30 seconds
- Write: 30 seconds
- Pool: 5 seconds

---

## 4. Database Schema Updates

### New Migration: `db/migrations/001_phase2a_schema.sql`

**Tables Created:**

| Table | Purpose |
|-------|---------|
| `portal_schemas` | Versioned transformation rules (NEET 2026, JEE, etc.) |
| `jobs` | Async execution units with state machine |
| `documents` | Canonical output + portal transformations |
| `user_credits` | Credit balance for billing |
| `cpu_usage` | Per-stage CPU consumption (append-only audit log) |
| `metrics` | Operational observability (90-day retention) |

**Job States:**
```
pending → processing → completed
                    └→ failed
```

**Row Level Security (RLS):**
- All tables have RLS enabled and forced
- Users can only access their own data
- `portal_schemas` read-only for authenticated users
- `metrics`, `cpu_usage` backend-only (service_role)

**Seed Data:**
- 5 realistic portal schemas (NEET 2026, JEE Main 2026, Aadhaar Update, Passport India, College Generic)

---

## 5. Configuration & Environment

### Environment Variables

#### API Gateway (Python/FastAPI)

| Variable | Description | Required |
|----------|-------------|----------|
| `SUPABASE_URL` | Supabase project URL | Yes |
| `SUPABASE_ANON_KEY` | Supabase anon key | Yes |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role | Yes |
| `SUPABASE_JWT_SECRET` | JWT secret for validation | Yes |
| `DO_SPACES_ENDPOINT` | e.g., `https://nyc3.digitaloceanspaces.com` | Yes |
| `DO_SPACES_REGION` | e.g., `nyc3` | Yes |
| `DO_SPACES_BUCKET` | e.g., `rythmiq-production` | Yes |
| `DO_SPACES_ACCESS_KEY` | Spaces access key | Yes |
| `DO_SPACES_SECRET_KEY` | Spaces secret key | Yes |
| `CAMBER_API_URL` | Camber API endpoint | Yes |
| `CAMBER_API_KEY` | Camber API key | Yes |
| `WEBHOOK_SECRET` | Secret for webhook auth | Yes |
| `SERVICE_ENV` | `dev` / `staging` / `prod` | No (default: dev) |

#### Worker (Python)

| Variable | Description | Required |
|----------|-------------|----------|
| `SPACES_ENDPOINT` | e.g., `https://nyc3.digitaloceanspaces.com` | Yes |
| `SPACES_REGION` | e.g., `nyc3` | Yes |
| `SPACES_BUCKET` | e.g., `rythmiq-production` | Yes |
| `SPACES_KEY` | Worker access key | Yes |
| `SPACES_SECRET` | Worker secret key | Yes |

### Template File: `touch.env`
A reference template with all required variables (using placeholder values).

---

## 6. Testing & Verification

### Manual Testing Checklist

- [ ] **Storage Path Validation**
  - [ ] Valid paths pass validation
  - [ ] Path traversal (`..`) rejected
  - [ ] Absolute paths rejected
  - [ ] Invalid UUIDs rejected

- [ ] **Presigned URLs**
  - [ ] Upload URL works with PUT
  - [ ] Download URL works with GET
  - [ ] Expired URLs return 403

- [ ] **Worker Pipeline**
  - [ ] Valid payload produces success result
  - [ ] Missing `job_id` produces `PAYLOAD_INVALID`
  - [ ] Network errors produce `FETCH_FAILED`
  - [ ] Corrupt images produce `DECODE_FAILED`

- [ ] **Webhook Integration**
  - [ ] Missing secret returns 401
  - [ ] Invalid secret returns 401
  - [ ] Valid success webhook updates job to `completed`
  - [ ] Duplicate webhooks handled idempotently

### Test Payload Example

```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "user_id": "12345678-1234-1234-1234-123456789012",
  "portal_schema": {
    "id": "schema-001",
    "name": "NEET 2026",
    "version": 1,
    "schema_definition": {
      "target_width": 200,
      "target_height": 230,
      "target_dpi": 200,
      "max_kb": 100,
      "filename_pattern": "{job_id}",
      "output_format": "jpeg",
      "quality": 85
    }
  },
  "input": {
    "artifact_url": "https://nyc3.digitaloceanspaces.com/rythmiq-dev/test.jpg?...",
    "mime_type": "image/jpeg",
    "original_filename": "passport_photo.jpg"
  },
  "storage": {
    "bucket": "rythmiq-dev",
    "region": "nyc3",
    "endpoint": "https://nyc3.digitaloceanspaces.com"
  }
}
```

---

## 7. Known Issues & Next Steps

### Known Issues

1. **API Server Startup** — `uvicorn` fails to start; needs dependency check
2. **PaddleOCR Models** — Must be pre-downloaded in Docker build for fast cold start
3. **Encryption** — Storage paths reference `.enc` files but encryption layer not yet implemented

### Next Steps (Priority Order)

1. **[P0] Fix API Server** — Resolve import/dependency issues
2. **[P0] End-to-End Test** — Full job submission → processing → webhook → completion
3. **[P1] Client-Side Encryption** — Implement AES-256-GCM encryption/decryption
4. **[P1] Credit System** — Wire up `user_credits` and `cpu_usage` tracking
5. **[P2] Observability** — Add Prometheus metrics, structured logging to `metrics` table
6. **[P2] Docker Optimization** — Multi-stage build for smaller worker image

---

## 8. File Manifest

### New Files Created

#### Shared Module
- `shared/__init__.py` — Package init
- `shared/path_validation.py` — Storage path validation (SINGLE SOURCE OF TRUTH)

#### API Services
- `app/api/services/storage.py` — DigitalOcean Spaces presigned URL service
- `app/api/services/camber.py` — Camber API client (job submission, status)
- `app/api/services/packaging.py` — In-memory ZIP packaging for outputs
- `app/services/__init__.py` — Service layer package
- `app/services/storage.py` — Alternative Spaces client (with path validation imports)

#### API Routes
- `app/api/routes/webhooks.py` — Camber webhook endpoint

#### Worker Core
- `worker/worker.py` — Main entry point
- `worker/models.py` — Frozen dataclass I/O contracts
- `worker/errors.py` — Structured error handling

#### Worker Processors
- `worker/processors/__init__.py` — Package exports
- `worker/processors/quality.py` — CPU-only quality assessment
- `worker/processors/ocr.py` — PaddleOCR integration
- `worker/processors/enhancement.py` — Image enhancement pipeline
- `worker/processors/schema.py` — Schema adaptation (resize, DPI, compression)

#### Worker Storage
- `worker/storage/spaces_client.py` — Worker Spaces client
- `worker/storage/spaces_example.py` — Integration example

#### Infrastructure
- `worker/Dockerfile.cpu` — CPU worker Docker image
- `db/migrations/001_phase2a_schema.sql` — Database schema migration
- `touch.env` — Environment variable template
- `camber-app.json` — Camber app configuration

### Modified Files
- `app/api/config.py` — Added Spaces and Camber settings
- `api-gateway/server.ts` — Environment validation, `spaces` store type
- Various `__pycache__` files (auto-generated)

---

## Contact & Handoff Notes

**Session Summary:**
- Complete storage architecture with security-first path validation
- Full worker pipeline from artifact fetch to output upload
- Camber webhook integration with idempotent handling
- Database schema with RLS and seed data

**Immediate Attention Required:**
1. API server startup failure needs debugging
2. End-to-end test required before any deployment

**Documentation Location:**
- This file: `/PROJECT_HANDOFF_2026_01_26.md`
- Deployment docs: `/DEPLOYMENT.md`, `/WORKER_DEPLOYMENT.md`
- Red team reviews: `/RED_TEAM_*.md`

---

*Document generated: January 26, 2026*
*Session duration: ~6 hours*
