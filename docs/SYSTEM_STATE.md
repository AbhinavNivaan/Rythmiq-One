# Rythmiq One — System Architecture & State Document

**Document Date:** February 14, 2026  
**Last Updated:** February 14, 2026  
**Author:** Engineering Team  
**Classification:** Internal Technical Reference  
**Status:** Active & Maintained

---

## Document Purpose & Usage

This document serves as the **single source of truth** for Rythmiq One's current system architecture, component interactions, and deployment state. It is designed to be **continuously maintained** and updated as the system evolves.

### Audience
- Engineers onboarding to the project
- Returning team members needing context
- Infrastructure & DevOps teams
- Technical decision-makers

### Maintenance Guidelines
- **Update frequency:** After any architectural change, deployment, or migration
- **Versioning:** Document date reflects last update (see "Last Updated" above)
- **Change tracking:** Use git history for detailed change logs
- **Format consistency:** Follow existing sections when adding new content

---

## 1. System Overview

### Mission
Rythmiq One is a **document processing platform** that helps students prepare photos, signatures, and documents meeting exact requirements for competitive exam portals (NEET, JEE, CAT, etc.).

### Core Workflow
```
User captures image → Mobile app → API Gateway → Worker processes → Results stored → User downloads
```

### Technology Stack Summary
| Layer | Technology | Version |
|-------|-----------|---------|
| **Mobile** | React Native (Expo) | Latest |
| **Backend API** | FastAPI (Python) | 0.100+ |
| **Processing Worker** | Python (Camber) | 3.10+ |
| **Database** | Supabase (PostgreSQL) | 15+ |
| **Storage** | DigitalOcean Spaces | S3-compatible |
| **Auth** | Supabase Auth | JWT-based |
| **Infrastructure** | Google Cloud Run | Serverless |
| **OCR Engine** | PaddleOCR | 3.4.0 |

---

## 2. Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    EXTERNAL SYSTEMS                              │
├─────────────────────────────────────────────────────────────────┤
│  DigitalOcean Spaces (S3)  │  Supabase (Auth + DB)  │ Camber   │
└─────────────────────────────────────────────────────────────────┘
                    ▲              ▲                      ▲
                    │              │                      │
        ┌───────────┴──────────────┴──────────────────────┴────────┐
        │                  API GATEWAY                             │
        │  FastAPI (Port 8000)                                     │
        │  ├── Routes: /jobs, /schemas, /webhooks, /health        │
        │  ├── Middleware: Auth, Rate Limit, Correlation ID       │
        │  └── Handlers: Job submission, polling, status tracking  │
        └───────────┬──────────────────────────────────────────────┘
                    │
                    ├─────────────────────────┐
                    │                         │
        ┌───────────▼──────┐      ┌──────────▼────────┐
        │  MOBILE APP      │      │ WORKER (Camber)   │
        │  React Native    │      │ CPU Processing    │
        │  (Expo)          │      │ ├─ OCR           │
        │                  │      │ ├─ Quality Score │
        │  ├─ Capture      │      │ ├─ Enhancement   │
        │  ├─ Auth         │      │ ├─ Adaptation    │
        │  ├─ Download     │      │ └─ Validation    │
        │  └─ UI           │      │                  │
        └──────────────────┘      └──────────────────┘
```

---

## 3. Component Architecture

### 3.1 Mobile Application (`app-v2/`)

**Purpose:** User-facing client for document capture, enhancement, and download

**Key Components:**
- **Screens** (`app/`): Navigation structure via Expo Router
  - Auth screens: Login, signup, onboarding
  - Main tabs: Capture, documents, settings
  - Processing UI: Job submission and polling
  
- **Services** (`services/`):
  - `api.ts`: HTTP client for backend communication
  - `biometric.ts`: Fingerprint/face authentication
  - `download.ts`: File management and download handling
  - Storage services for document persistence

- **Hooks** (`hooks/`):
  - `useSessionTimeout`: Auto-logout on inactivity
  - `useCachedImage`: Image caching optimization
  - `useOptimisticUpdate`: UI updates before server confirmation

- **Components** (`components/`):
  - DevSandboxBanner: Development environment indicator
  - UI components: Buttons, modals, forms, cards

**Technology:**
- Framework: Expo (React Native)
- State: Context API (see `contexts/AuthContext.tsx`)
- Build: EAS (Expo Application Services)
- Platforms: iOS, Android, Web (Expo Web)

**Configuration:**
- `app.json`: Expo app manifest
- `eas.json`: EAS build configuration
- `tsconfig.json`: TypeScript configuration
- `babel.config.js`: JavaScript transpilation

---

### 3.2 Backend API (`app/api/`)

**Purpose:** REST API gateway for job submission, status tracking, and schema management

**Architecture:**

```
app/api/
├── main.py              # FastAPI app factory
├── config.py            # Settings management (env vars)
├── errors.py            # Exception definitions
├── middleware/          # Request/response processors
│   ├── auth.py         # JWT validation
│   ├── logging.py      # Request logging
│   └── correlation.py  # Request tracing
├── db/                 # Database layer
│   ├── client.py       # Supabase connection
│   ├── models.py       # ORM definitions
│   └── queries.py      # Query builders
├── routes/             # API endpoints
│   ├── health.py       # /health checks
│   ├── jobs.py         # /jobs endpoints
│   ├── schemas.py      # /schemas endpoints
│   └── webhooks.py     # Webhook handlers
├── services/           # Business logic
│   ├── job_service.py  # Job orchestration
│   ├── camber_client.py# Camber integration
│   └── spaces_client.py# DigitalOcean Spaces I/O
└── requirements.txt    # Python dependencies
```

**Key Endpoints:**
| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/jobs` | Submit new document for processing |
| GET | `/jobs/{job_id}` | Check job status |
| GET | `/jobs/{job_id}/result` | Retrieve processed results |
| GET | `/schemas` | List all portal schemas |
| POST | `/webhooks/camber` | Receive Camber job completion |
| GET | `/health` | Health check |

**Key Features:**
- **Rate Limiting:** Per-user/IP limits via middleware
- **Authentication:** JWT tokens from Supabase
- **Correlation IDs:** Request tracing across services
- **Error Handling:** Structured error responses with codes
- **Logging:** JSON-formatted structured logs

---

### 3.3 Processing Worker (`worker/`)

**Purpose:** CPU-bound document processing executed on Camber infrastructure

**Execution Model:**
- **Trigger:** FastAPI submits job to Camber via `camber job create`
- **Input:** JSON payload via STDIN
- **Processing:** Single-shot, no retries, no state
- **Output:** JSON result to STDOUT
- **Contract:** Always exits with code 0 (success or handled failure)

**Architecture:**

```
worker/
├── worker.py           # Main STDIN→STDOUT handler
├── models.py           # Data structures
├── errors.py           # Error definitions & codes
├── server.py           # Local HTTP server (dev only)
├── requirements.txt    # Dependencies
├── bootstrap.sh        # Camber execution setup
├── ocr/                # OCR pipeline
│   ├── paddle.py      # PaddleOCR initialization
│   ├── quality.py     # Quality scoring (Laplacian variance)
│   └── extraction.py  # Text & confidence extraction
├── processors/         # Processing stages
│   ├── enhance.py     # Image enhancement
│   ├── adapt.py       # Schema-based adaptation
│   └── validate.py    # Quality threshold checks
└── storage/            # External I/O
    └── spaces_client.py# DigitalOcean Spaces interaction
```

**Processing Pipeline:**
1. **Payload Parsing:** Validate JSON input, extract parameters
2. **Artifact Retrieval:** Download source image from Spaces
3. **Quality Assessment:** Calculate sharpness (Laplacian variance)
4. **OCR Extraction:** PaddleOCR for text & confidence scores
5. **Image Enhancement:** Quality improvement (contrast, noise reduction)
6. **Schema Adaptation:** Resize/compress to target portal specs
7. **Result Generation:** Create master (encrypted) + preview outputs
8. **Artifact Upload:** Store results back to Spaces
9. **Result Return:** Output JSON with status, metrics, artifact paths

**Error Handling:**
- All errors caught and returned as valid JSON (not exceptions)
- Error codes: `PAYLOAD_MISSING`, `ARTIFACT_INVALID`, `OCR_FAILED`, etc.
- Processing stage tracking for debugging
- No unhandled exceptions ever raised to Camber

**Dependencies:**
- `paddleocr`: OCR engine
- `opencv-python`: Image processing
- `boto3`: S3/Spaces client
- `Pillow`: Image manipulation
- `numpy/scipy`: Numerical operations

---

### 3.4 Database (`db/` & Supabase)

**Purpose:** Persistent storage for users, jobs, documents, and metadata

**Schema Highlights:**
- `users`: User accounts, auth data
- `jobs`: Job records with status tracking
- `documents`: Master document versions
- `artifacts`: Output artifact references
- `webhooks`: Webhook endpoint configurations

**Features:**
- Row-Level Security (RLS) for multi-tenancy
- Real-time subscriptions (for live status updates)
- JWT authentication integration
- Audit logs for compliance

**Connection:**
- Via Supabase client in API service
- Environment: `SUPABASE_URL`, `SUPABASE_KEY`
- SSL enforced in production

---

### 3.5 Storage (`DigitalOcean Spaces`)

**Purpose:** S3-compatible object storage for documents, master files, and previews

**Structure:**
```
nyc3.digitaloceanspaces.com/rythmiq-one/
├── input/              # Uploaded user documents
│   └── {user_id}/{job_id}/source.jpg
├── output/             # Preview results
│   └── {user_id}/{job_id}/preview.jpg
├── master/             # Encrypted master versions
│   └── {user_id}/{document_id}/master.enc
└── temp/               # Temporary processing files
    └── {job_id}/*
```

**Access:**
- Via boto3 with AWS S3v4 signature
- Credentials: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`
- Endpoint: `https://nyc3.digitaloceanspaces.com`
- Region: `nyc3`

**Policies:**
- Input/output buckets: Public read (authenticated URLs)
- Master bucket: Private (server-only access)
- Lifecycle: Auto-delete temp files after 7 days

---

### 3.6 Camber Integration

**Purpose:** Scalable, on-demand CPU processing infrastructure

**Job Submission:**
```bash
camber job create \
  --engine base \
  --size SMALL \
  --image python:3.10 \
  --stash stash://user/repo/tag/ \
  --cmd "pip install -r requirements.txt && echo '{}' | python worker.py"
```

**Execution:**
- Base engine (no GPU)
- Single-core CPU allocation
- ~1.5GB memory for PaddleOCR
- Typical runtime: 10-30 seconds per document

**Webhook Callback:**
- Camber posts job completion to `/webhooks/camber`
- Payload includes: `job_id`, `status`, `output`, `exit_code`
- API updates database and notifies client

**Stash Repository:**
- Location: `stash://abhinavprakash15151692/rythmiq-worker-v2/`
- Contents: Worker code + dependencies
- Updated via: `camber stash push`

---

## 4. Data Flow

### 4.1 Document Processing Flow

```
1. USER CAPTURE
   ├─ Mobile app captures image/signature
   ├─ Basic validation (size, format)
   └─ Uploads to Spaces input bucket

2. JOB SUBMISSION
   ├─ User selects target portal (schema)
   ├─ Mobile app POSTs to /jobs
   ├─ API validates request + auth
   └─ Creates job record in database

3. WORKER PROCESSING
   ├─ API submits to Camber: camber job create
   ├─ Camber downloads worker code from stash
   ├─ Worker reads job payload from STDIN
   ├─ Worker downloads source from Spaces
   ├─ Worker processes (OCR, enhance, adapt)
   ├─ Worker uploads results to Spaces
   └─ Worker outputs JSON result to STDOUT

4. COMPLETION HANDLING
   ├─ Camber posts webhook to /webhooks/camber
   ├─ API updates job status in database
   ├─ Client polls /jobs/{job_id} for completion
   └─ Results available for download

5. USER DOWNLOAD
   ├─ Mobile app requests /jobs/{job_id}/result
   ├─ API returns artifact URLs + metadata
   ├─ Mobile app downloads from Spaces
   └─ User receives portal-ready files
```

---

## 5. Deployment Architecture

### 5.1 Production Deployment

**Mobile App:**
- Platform: Expo (EAS)
- Builds: iOS (TestFlight), Android (Play Store), Web
- Distribution: Over-the-air updates via Expo

**API Server:**
- Platform: Google Cloud Run (serverless)
- Container: Docker (from `Dockerfile.cloudrun`)
- Region: `asia-south1` (Asia South)
- Scaling: Automatic (0-N replicas)
- Port: 8000

**Worker:**
- Platform: Camber (on-demand)
- Execution: Triggered by API via `camber job create`
- Code: Stored in Camber stash
- Lifecycle: Single-shot (no persistence)

**Infrastructure as Code:**
- Build config: `cloudbuild.yaml`
- Docker: `Dockerfile.cloudrun` (API)
- Worker Docker: `worker/Dockerfile.production`
- Kubernetes: Not used (Cloud Run)

### 5.2 Development Environment

**Local Setup:**
1. Python venv for API: `.venv/`
2. Node environment for mobile: `node_modules/`
3. Camber CLI for worker testing
4. Docker Desktop for containerization

**Running Locally:**
```bash
# Terminal 1: API Server
source .venv/bin/activate
uvicorn app.api.main:app --reload --port 8000

# Terminal 2: Mobile App
cd app-v2
npm start

# Terminal 3: Worker (manual test)
cd worker
echo '{}' | python worker.py
```

**Environment Variables:**
- `.env` file (git-ignored, see `docs/env.example`)
- Loaded by `app.api.config.py`
- Key vars:
  - `SUPABASE_URL`, `SUPABASE_KEY`: Database
  - `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`: Spaces
  - `CAMBER_STASH`: Worker code location
  - `SERVICE_ENV`: `dev` / `staging` / `prod`

---

## 6. Key Integrations

### 6.1 Supabase
- **Role:** User database, auth, metadata
- **Type:** Managed PostgreSQL
- **Connection:** Via Supabase client SDK
- **Auth:** JWT tokens (email/password)

### 6.2 DigitalOcean Spaces
- **Role:** Document storage
- **Type:** S3-compatible object storage
- **Connection:** boto3 with AWS signatures
- **Usage:** Input uploads, output storage, master archives

### 6.3 Camber
- **Role:** Scalable processing backend
- **Type:** On-demand CPU/GPU infrastructure
- **Connection:** CLI + STDIN/STDOUT contract
- **Usage:** Document OCR, enhancement, adaptation

### 6.4 Google Cloud Run
- **Role:** API hosting
- **Type:** Serverless container execution
- **Connection:** Docker image deployment
- **Usage:** REST API gateway

---

## 7. Security & Compliance

### 7.1 Authentication
- **Mobile:** Supabase JWT (email + password)
- **API:** Bearer token validation on every request
- **Database:** Row-level security (user isolation)

### 7.2 Data Encryption
- **In Transit:** HTTPS/TLS everywhere
- **At Rest:** 
  - Master documents encrypted before Spaces upload
  - Database SSL connections
  - Worker credentials via environment

### 7.3 Error Handling
- **No stack traces** to clients (structured error codes)
- **Internal logging** includes full context (server-side only)
- **Sensitive data** (keys, paths) never logged

### 7.4 Rate Limiting
- Per-user limits on job submission
- Per-IP limits on auth endpoints
- Implemented via middleware

---

## 8. Monitoring & Observability

### 8.1 Logging
- **Format:** JSON structured logs (timestamp, level, logger, message)
- **Collection:** Cloud Logging (Google Cloud)
- **Retention:** 30 days default
- **Levels:** DEBUG (dev), INFO (prod)

### 8.2 Metrics & Alerts
- **Cloud Run metrics:** CPU, memory, request latency, error rate
- **Alerting:** Google Cloud Alerting (TBD: thresholds)
- **Custom metrics:** Job processing time, queue depth, worker success rate

### 8.3 Error Tracking
- **Worker errors:** JSON error responses (no exceptions)
- **API errors:** Exception handlers + structured logging
- **Mobile errors:** Client-side error reporting (TBD)

---

## 9. Known Limitations & Constraints

| Item | Constraint | Impact |
|------|-----------|--------|
| **Worker CPU** | Single-core only | ~10-30s per document |
| **OCR Models** | Downloaded at first run | ~10-15s cold start |
| **Spaces** | NYC3 region only | Latency for APAC users |
| **Concurrent Jobs** | Per-user limits (TBD) | Prevents abuse |
| **Master Encryption** | Symmetric (server holds key) | Key management risk |
| **Webhook Timeout** | Camber default | Missed callbacks possible |

---

## 10. Recent Changes & Version History

| Date | Component | Change | Impact |
|------|-----------|--------|--------|
| 2026-01-30 | Worker | Camber integration complete | Prod-ready processing |
| 2026-01-15 | API | Webhook handler added | Async job completion |
| 2025-12-01 | Mobile | React Native upgrade | Latest Expo support |
| TBD | - | - | - |

---

## 11. Future Roadmap (High-Level)

- [ ] GPU worker support (faster OCR)
- [ ] Webhook retries with exponential backoff
- [ ] Master document key management (KMS integration)
- [ ] Mobile offline-first caching
- [ ] Advanced schema validation (field-level rules)
- [ ] Performance optimization (PaddleOCR pre-baking)

---

## 12. Contact & References

**Document Owner:** Engineering Team  
**Last Review:** February 14, 2026  
**Next Review Due:** May 14, 2026

**Related Documentation:**
- [README.md](../README.md) — Project overview
- [STARTUP_GUIDE.md](../STARTUP_GUIDE.md) — Quick start
- [PHASE1_REAL_CAMBER_INTEGRATION_HANDOFF.md](./PHASE1_REAL_CAMBER_INTEGRATION_HANDOFF.md) — Camber implementation details
- [ENV_REFERENCE.md](../ENV_REFERENCE.md) — Environment variables
- [OPERATIONS_RUNBOOK.md](./OPERATIONS_RUNBOOK.md) — Deployment procedures

---

## 13. Editing This Document

### How to Update
1. Identify the section(s) needing updates
2. Edit directly (markdown format)
3. Update "Last Updated" date at top
4. Add entry to Section 10 (Recent Changes)
5. Commit with descriptive message: `docs: update SYSTEM_STATE.md - [brief description]`

### New Section Template
```markdown
### X.Y [Component/Feature Name]

**Purpose:** What it does  
**Technology:** Stack used  
**Location:** File/directory path  

**Key Details:**
- Point 1
- Point 2

**Configuration:** (if applicable)
- Config file paths
- Environment variables
```

### Things to Update When
- **New component added:** Add to Section 3 (Components)
- **Integration changed:** Update Section 6 (Integrations)
- **Deployment changed:** Update Section 5 (Deployment)
- **Bug fixed/limitation resolved:** Update Section 9 (Limitations)
- **New version released:** Add to Section 10 (Changes)

---

**END OF DOCUMENT**
