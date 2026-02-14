# Rythmiq One — Project State

> **Last Updated**: 13 February 2026
> **Purpose**: Single source of truth for project state, constraints, and implementation history.
> **Rule**: READ THIS FILE FIRST before any implementation session.

---

## What Rythmiq One Does

One-tap document preparation for Indian competitive exam portals (NEET, JEE, UPSC, SSC, IBPS, RRB). Students take photos/signatures → the system enhances, validates, and adapts them to exact portal specifications → students download portal-ready files.

---

## Current Architecture (What Is Actually Running)

| Component | Technology | Port | Status |
|-----------|-----------|------|--------|
| **Mobile App** | React Native Expo v54, TypeScript, expo-router | Expo Dev Client | ✅ Active (`app-v2/`) |
| **Backend API** | Python FastAPI, uvicorn | 8000 | ✅ Active (`app/api/`) |
| **Execution Backend** | Mock Camber (in-process) | — | ✅ Active (`EXECUTION_BACKEND=local`) |
| **Database** | Supabase (PostgreSQL + PostgREST) | — | ✅ Active (`qpixafvazayfjamgywbb.supabase.co`) |
| **File Storage** | DigitalOcean Spaces (S3-compatible) | — | ✅ Active (`rythmiq-one-artifacts.sgp1`) |
| **Auth** | Dev Sandbox Mode (bypassed) | — | ✅ Active (`DEV_SANDBOX_ENABLED=true`) |

### What Is NOT Running / Legacy

| Component | Technology | Notes |
|-----------|-----------|-------|
| TypeScript Express API Gateway | Node.js, Express, port 3000 | `api-gateway/server.ts` — **LEGACY, NOT USED**. Root `package.json` still references it but `uvicorn` is what runs. |
| TypeScript Worker | Node.js | `worker/entrypoint.ts` — **LEGACY, NOT USED**. Python workers (`worker.py`, `main.py`) exist but are NOT invoked by mock Camber either. |
| Real Camber execution | Camber Cloud | `api.camber.cloud` does NOT exist as a REST API. Camber only supports CLI and Python SDK. See Hard Constraints below. |

---

## ⛔ Hard Constraints (READ BEFORE IMPLEMENTING)

These are empirically verified facts. Do NOT implement anything that violates these.

### Camber Cloud Platform

| Constraint | Evidence | Source |
|------------|----------|--------|
| **`api.camber.cloud` does NOT exist** | DNS resolution fails. Platform has no REST API. | [CAMBER_PLATFORM_GUIDE.md, line 926](docs/CAMBER_PLATFORM_GUIDE.md) |
| **Camber only supports CLI (`camber job create`) or Python SDK (`camber.mpi`)** | Documented and verified | [CAMBER_PLATFORM_GUIDE.md](docs/CAMBER_PLATFORM_GUIDE.md) |
| **No `apt-get` on BASE engine** | Permission denied, cannot install system packages | [CAMBER_PLATFORM_EVALUATION.md](docs/CAMBER_PLATFORM_EVALUATION.md) |
| **No Docker support on BASE engine** | Docker only available on higher-tier engines | [CAMBER_PLATFORM_EVALUATION.md](docs/CAMBER_PLATFORM_EVALUATION.md) |
| **rembg: NOT viable on Camber** | 90s/job, U2Net model (176MB) re-downloads every job | [CAMBER_PLATFORM_EVALUATION.md](docs/CAMBER_PLATFORM_EVALUATION.md) |
| **PaddleOCR: platform error on Camber** | Failed during evaluation | [CAMBER_PLATFORM_EVALUATION.md](docs/CAMBER_PLATFORM_EVALUATION.md) |
| **~80% of billed time is pip install overhead** | 65s total, 14s actual processing | [CAMBER_EXECUTION_BEHAVIOR_REPORT.md](docs/CAMBER_EXECUTION_BEHAVIOR_REPORT.md) |
| **Concurrent job limit: ~4-6** | Additional jobs queue with 1-3 min delay | [CAMBER_EXECUTION_BEHAVIOR_REPORT.md](docs/CAMBER_EXECUTION_BEHAVIOR_REPORT.md) |
| **No long-running workers** | Each job is ephemeral, fresh environment | [CAMBER_PLATFORM_EVALUATION.md](docs/CAMBER_PLATFORM_EVALUATION.md) |
| **Viable paths on Camber: Pillow, OpenCV, PyMuPDF, img2pdf only** | Tested and confirmed | [CAMBER_PLATFORM_EVALUATION.md](docs/CAMBER_PLATFORM_EVALUATION.md) |

### Current Code

| Constraint | Detail |
|------------|--------|
| **Mock Camber does NOT process images** | `mock_camber_client.py` returns hardcoded dummy data (`field_1: mock_value_1`). No worker pipeline is invoked. |
| **`db/schema.sql` is STALE** | Jobs table and portal_schemas table definitions in `schema.sql` do not match what the API code actually uses. Migration `003` is the real portal_schemas source. The jobs table was manually altered in Supabase. |
| **Three conflicting portal schema sources** | `db/schema.sql` (5 year-specific schemas), migration `003` (13 generic schemas), `schemas/portal_schemas.json` (14 schemas including `aadhaar_photo`). Migration `003` is what's in the live database. |
| **Three Python worker entrypoints** | `worker.py`, `main.py`, and `job_handler.py` all do similar things with different models. None are invoked in current dev setup. |
| **TypeScript and Python stacks coexist** | Root `package.json` points to TypeScript Express gateway. Actual running backend is Python FastAPI. This causes confusion. |
| **`CAMBER_PRODUCTION_DEPLOYMENT.md` references non-existent `api.camber.cloud`** | This root-level document is MISLEADING. It was written as an aspirational guide before platform limitations were discovered. |

---

## Current Dev Environment

### How to Start

```bash
# Backend (Python FastAPI)
cd "/Users/abhinav/Rythmiq One"
source .venv/bin/activate
uvicorn app.api.main:app --host 0.0.0.0 --port 8000

# Mobile App (Expo)
cd "/Users/abhinav/Rythmiq One/app-v2"
npm start

# For webhook testing (optional)
ngrok http 8000
```

### Key Environment Variables (.env)

| Variable | Current Value | Notes |
|----------|--------------|-------|
| `EXECUTION_BACKEND` | `local` | Uses mock Camber. `camber` option broken (no REST API). |
| `SERVICE_ENV` | `dev` | Enables dev sandbox, skips webhook signature verification |
| `DEV_SANDBOX_ENABLED` | `true` | Bypasses JWT auth when `X-Dev-Sandbox: true` header sent |
| `CAMBER_API_URL` | `https://api.camber.cloud` | ⚠️ Does NOT work. Placeholder only. |
| `WEBHOOK_BASE_URL` | `https://brainlike-ha-abstruse.ngrok-free.dev` | Ngrok tunnel (ephemeral, changes each session) |

### Dev Sandbox Mode

When enabled (`DEV_SANDBOX_ENABLED=true` + `SERVICE_ENV=dev`):
- Mobile app sends `X-Dev-Sandbox: true` header
- Backend returns static user (`00000000-0000-0000-0000-000000000001`)
- Storage uploads go to `dev-sandbox/` prefix with 24h TTL
- Webhook signature verification is skipped
- Orange "🧪 Dev Sandbox Mode" banner shows in mobile app

### API Endpoints (FastAPI, port 8000)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/health` | No | Health check |
| GET | `/health/detailed` | No | Detailed health with dev sandbox status |
| POST | `/auth/signup` | No | User registration |
| POST | `/auth/login` | No | User login |
| POST | `/auth/refresh` | No | Token refresh |
| GET | `/auth/me` | JWT | Current user info |
| POST | `/auth/logout` | JWT | Logout |
| GET | `/schemas` | JWT | List portal schemas |
| GET | `/schemas/portals` | JWT | List schemas (mobile alias) |
| POST | `/jobs` | JWT | Create processing job |
| GET | `/jobs` | JWT | List user's jobs |
| GET | `/jobs/{job_id}` | JWT | Get job status |
| GET | `/jobs/{job_id}/result` | JWT | Get job result |
| POST | `/adapt` | JWT | Adapt document to schema |
| GET | `/adapt/{job_id}` | JWT | Get adaptation result |
| POST | `/internal/webhooks/camber` | HMAC | Webhook callback from Camber/mock |

### Database (Supabase)

**Live tables** (verified in use by API code):
- `portal_schemas` — 13 schemas (from migration 003), UUID PK, `name` UNIQUE, `schema_definition` JSONB
- `jobs` — UUID PK, `user_id`, `portal_schema_version_id`, `status` (pending/processing/completed/failed), `input_metadata` JSONB, `portal_output` JSONB

**Stale/legacy tables** (defined in `db/schema.sql` but may not match live DB):
- `users`, `documents`, `audit_log` — These table definitions in `schema.sql` predate the current API and may not reflect live Supabase state

---

## Known Issues & Technical Debt

| # | Issue | Severity | Detail |
|---|-------|----------|--------|
| 1 | Mock Camber returns dummy data | Medium | No actual image processing occurs. Jobs "complete" with hardcoded mock results. |
| 2 | `db/schema.sql` is out of sync | High | Does not match live Supabase schema. Jobs table missing columns API uses. Portal schemas table has wrong structure. |
| 3 | Three portal schema definitions disagree | High | `schema.sql` (5), migration 003 (13), `portal_schemas.json` (14). `aadhaar_photo` missing from DB. |
| 4 | Legacy TypeScript stack still in repo | Low | `api-gateway/`, `engine/`, TypeScript worker, root `package.json` — all unused but cause confusion. |
| 5 | Real Camber integration requires architecture change | High | Current `CamberService` class tries HTTP POST to non-existent API. Would need CLI wrapper or Python SDK. |
| 6 | Three Python worker entrypoints | Medium | `worker.py`, `main.py`, `job_handler.py` — unclear which is canonical. None are invoked. |
| 7 | `CAMBER_PRODUCTION_DEPLOYMENT.md` is misleading | Medium | References `api.camber.cloud` as real. Should be marked OUTDATED. |
| 8 | Webhook HMAC verification is dead code in dev | Low | Mock signs requests, but endpoint skips verification when `SERVICE_ENV=dev`. |

---

## Implementation History (Newest First)

### 2026-02-10 — Dev Sandbox Mode
- **What**: Auth bypass for local testing, storage TTL, visual indicators in mobile app
- **Files changed**: `app/api/config.py`, `app/api/auth/dependencies.py`, `app/api/services/storage.py`, `app/api/routes/health.py`, `app/api/routes/jobs.py`, `app/api/errors/handlers.py`, `app/api/db/client.py`, `app/api/routes/webhooks.py`, `app-v2/services/api.ts`, `app-v2/components/DevSandboxBanner.tsx`, `app-v2/app/(tabs)/dashboard.tsx`, `app-v2/.env`, `.env`
- **Decisions**: Using mock Camber because real Camber REST API doesn't exist
- **Fixes applied**: Logging `message` reserved keyword, `camber_job_id` column references removed, webhook auth bypass in dev, `output_metadata` → `portal_output`
- **Status**: ✅ Working — jobs complete end-to-end with mock data
- **Details**: [DEV_SANDBOX_SETUP.md](DEV_SANDBOX_SETUP.md)

### 2026-02-10 — Database Schema Fix
- **What**: Created migration 003 for portal_schemas, fixed jobs table in Supabase
- **Files changed**: `db/migrations/003_create_portal_schemas_complete.sql`
- **Decisions**: Jobs table manually altered in Supabase SQL editor (not captured in migration file)
- **Issues found**: PostgREST cache error PGRST205, jobs table had wrong columns
- **Status**: ✅ Working in live Supabase

### 2026-02-05 — Supabase Keep-Alive
- **What**: GitHub Actions workflow to prevent free-tier DB auto-pause
- **Files changed**: `.github/workflows/keep-supabase-alive.yml`
- **Git commit**: `df66e1c` (2026-02-05)
- **Status**: ✅ Committed, running

### 2026-01-31 — Camber Platform Evaluation
- **What**: Comprehensive benchmark of all processing paths on real Camber
- **Key findings**: Pillow/OpenCV/PyMuPDF viable. rembg NOT viable (90s/job). PaddleOCR platform error.
- **Decision**: Conditional GO for simple paths only
- **Status**: ✅ Complete — evaluation informs architecture
- **Details**: [CAMBER_PLATFORM_EVALUATION.md](docs/CAMBER_PLATFORM_EVALUATION.md)

### 2026-01-30 — Production Observability & Capacity Planning
- **What**: CPU metrics schema, error events tracking, load testing framework, Camber execution benchmarks
- **Key findings**: Worker processes documents in 13-15s actual time. 0.42s CPU per doc (77× better than estimated). 57× target volume capacity.
- **Decision**: GO for production capacity
- **Git commit**: `abe5501` (2026-01-30)
- **Status**: ✅ Benchmark complete. Metrics schemas ready but uncommitted to Supabase.
- **Details**: [PROJECT_HANDOFF_2026_01_30.md](PROJECT_HANDOFF_2026_01_30.md), [CAMBER_EXECUTION_BEHAVIOR_REPORT.md](docs/CAMBER_EXECUTION_BEHAVIOR_REPORT.md)

### 2026-01-30 — Real Camber Integration (Phase 1)
- **What**: Validated worker execution on real Camber BASE engine via CLI
- **Key findings**: 100% success rate across 18+ jobs. BASE engine works. DO Spaces I/O works. PaddleOCR initializes on CPU.
- **Method**: Used `camber job create --engine base` CLI (NOT REST API)
- **Git commit**: Part of `abe5501`
- **Status**: ✅ Execution validated. No webhook integration (used polling).
- **Details**: [PHASE1_REAL_CAMBER_INTEGRATION_HANDOFF.md](docs/PHASE1_REAL_CAMBER_INTEGRATION_HANDOFF.md)

### 2026-01-27 — Phase-2A Stabilization
- **What**: Fixed FastAPI boot failure, implemented local mock Camber, calibrated quality scoring, validated OCR confidence, verified schema adapters, implemented enhancement guardrails
- **Key findings**: Pydantic settings were instantiated at import time (fixed with `@lru_cache`). Quality threshold 0.80. OCR confidence threshold 0.70.
- **Git commit**: `a021f89` (2026-01-27)
- **Status**: ✅ System bootable and locally testable
- **Details**: [PROJECT_HANDOFF_2026_01_27_PHASE2A.md](PROJECT_HANDOFF_2026_01_27_PHASE2A.md)

### 2026-01-26 — Storage Architecture & Worker Implementation
- **What**: DigitalOcean Spaces integration, worker pipeline (FETCH→DECODE→QUALITY→ENHANCE→OCR→SCHEMA→UPLOAD), webhook callback pattern, mock Camber client
- **Git commit**: `63134e7` (2026-01-26)
- **Status**: ✅ Foundation complete
- **Details**: [PROJECT_HANDOFF_2026_01_26.md](PROJECT_HANDOFF_2026_01_26.md)

### 2026-01-25 — Python Worker Initial Implementation
- **What**: New Python worker for document processing with OCR, artifact fetching, schema transformation
- **Git commit**: `5744ef6` (2026-01-25)
- **Status**: ✅ Worker code exists but is NOT invoked by mock Camber

### 2026-01-22 — Initial TypeScript Backend & Heroku Deployment
- **What**: TypeScript Express API gateway, job store, Heroku deployment attempts
- **Git commits**: `0680cf2` through `ff75d84` (2026-01-22)
- **Status**: ⚠️ LEGACY — Replaced by Python FastAPI backend. TypeScript code still in repo.

### Pre-2026-01-22 — Red Team Security Reviews
- **What**: Security analysis of upload, job status, OCR schema, output delivery APIs
- **Key findings**: Error responses leak system state (blocker). Need opaque error codes.
- **Status**: ✅ Reviews complete. Remediation partially applied.
- **Details**: [RED_TEAM_INDEX.md](RED_TEAM_INDEX.md)

---

## Document Index

### ⚠️ Documents That Contain Outdated/Misleading Information

| Document | Issue |
|----------|-------|
| [CAMBER_PRODUCTION_DEPLOYMENT.md](CAMBER_PRODUCTION_DEPLOYMENT.md) | References `api.camber.cloud` as if it's a real REST API. It does NOT exist. Written before platform limitations were discovered. |
| [db/schema.sql](db/schema.sql) | Portal schemas and jobs table definitions do not match live Supabase schema. |
| [STARTUP_GUIDE.md](STARTUP_GUIDE.md) | References TypeScript/Express startup (`npm start`, `npm run worker`). Actual backend is Python/FastAPI. |
| [docs/e2e-run.md](docs/e2e-run.md) | Describes TypeScript E2E flow with `npm install` / `npm run build`. Not how the system works now. |
| [docs/OPERATIONS_RUNBOOK.md](docs/OPERATIONS_RUNBOOK.md) | References `api.rythmiq.one` and `cdn.rythmiq.one` — these do not exist. Aspirational. |
| [EXECUTION_BACKEND_IMPLEMENTATION.md](EXECUTION_BACKEND_IMPLEMENTATION.md) | Describes TypeScript execution backend selector. Actual selector is in Python (`app/api/services/camber.py`). |
| [DEPLOYMENT_INDEX.md](DEPLOYMENT_INDEX.md) | References TypeScript Dockerfiles and Heroku deployment. Not current deployment approach. |

### ✅ Documents That Are Current and Accurate

| Document | Content |
|----------|---------|
| [docs/CAMBER_PLATFORM_GUIDE.md](docs/CAMBER_PLATFORM_GUIDE.md) | Complete Camber reference. Correctly notes `api.camber.cloud` doesn't exist. |
| [docs/CAMBER_PLATFORM_EVALUATION.md](docs/CAMBER_PLATFORM_EVALUATION.md) | Benchmark results for processing paths on Camber. Data is valid. |
| [docs/CAMBER_EXECUTION_BEHAVIOR_REPORT.md](docs/CAMBER_EXECUTION_BEHAVIOR_REPORT.md) | Real execution measurements on Camber. Data is valid. |
| [docs/PHASE1_REAL_CAMBER_INTEGRATION_HANDOFF.md](docs/PHASE1_REAL_CAMBER_INTEGRATION_HANDOFF.md) | Accurate Phase 1 handoff. Evidence-based. |
| [PROJECT_HANDOFF_2026_01_26.md](PROJECT_HANDOFF_2026_01_26.md) | Accurate session handoff for storage + worker architecture. |
| [PROJECT_HANDOFF_2026_01_27_PHASE2A.md](PROJECT_HANDOFF_2026_01_27_PHASE2A.md) | Accurate session handoff for stabilization work. |
| [PROJECT_HANDOFF_2026_01_30.md](PROJECT_HANDOFF_2026_01_30.md) | Accurate session handoff for observability + capacity. |
| [DEV_SANDBOX_SETUP.md](DEV_SANDBOX_SETUP.md) | Current dev sandbox setup instructions. |
| [LOCAL_CAMBER_MOCK_INDEX.md](LOCAL_CAMBER_MOCK_INDEX.md) | Accurate mock Camber documentation. |
| [OCR_FIX_SUMMARY.md](OCR_FIX_SUMMARY.md) | PaddleOCR 2.x→3.x compatibility fix. Valid. |
| [RED_TEAM_INDEX.md](RED_TEAM_INDEX.md) | Security review index. Reviews are valid (against TypeScript code). |

---

## Git Commit History (Key Commits)

| Date | Hash | Description |
|------|------|-------------|
| 2026-02-05 | `df66e1c` | Supabase keep-alive (WRITE operation) |
| 2026-02-05 | `6ffcf90` | Supabase keep-alive (daily schedule) |
| 2026-01-30 | `abe5501` | CPU metrics collection |
| 2026-01-30 | `dddade2` | Infra health check fix |
| 2026-01-30 | `a55e94e` | Supabase keep-alive workflow |
| 2026-01-27 | `a021f89` | API, worker services, DB schema, testing |
| 2026-01-26 | `63134e7` | Schema validation and transformation |
| 2026-01-25 | `5744ef6` | Python worker implementation |
| 2026-01-22 | `0680cf2` | Initial commit (TypeScript stack) |

> **Note**: Most implementation work after 2026-01-30 was done in uncommitted sessions (dev sandbox, DB migrations, code fixes). These changes exist in the working tree but are not committed to git.

---

## What Needs To Happen Next (Unresolved)

1. **Decide on execution platform**: Camber requires CLI/SDK wrapper (not REST API). Alternatives: Modal Labs, Google Cloud Run, AWS Lambda, or keep using mock locally.
2. **Make mock Camber actually process images**: Currently returns hardcoded dummy data. Could invoke the worker pipeline locally for real processing without Camber.
3. **Reconcile portal schema sources**: Pick one source of truth between `schema.sql`, migration 003, and `portal_schemas.json`. Sync them.
4. **Clean up legacy TypeScript code**: Either remove `api-gateway/`, TypeScript workers, and root `package.json` scripts, or clearly mark them as legacy.
5. **Sync `db/schema.sql` with live Supabase**: Current file doesn't match the actual database.
6. **Commit uncommitted work**: Dev sandbox implementation, code fixes, and DB migration are not in git.
