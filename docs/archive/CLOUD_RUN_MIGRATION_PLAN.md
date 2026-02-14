# Rythmiq One — Cloud Run Migration Plan

> **Created**: 14 February 2026  
> **Status**: PROPOSAL — Not yet implemented  
> **Context**: Replacing Camber Cloud as the execution backend for document processing

---

## Table of Contents

1. [Why We're Leaving Camber](#why-were-leaving-camber)
2. [Platform Comparison](#platform-comparison)
3. [Why Google Cloud Run Wins](#why-google-cloud-run-wins)
4. [Cloud Run Deep Dive](#cloud-run-deep-dive)
5. [Architecture: Before & After](#architecture-before--after)
6. [Migration Plan](#migration-plan)
7. [Dockerfile Specification](#dockerfile-specification)
8. [Pricing Analysis](#pricing-analysis)
9. [Cold Start Strategy](#cold-start-strategy)
10. [Deployment Commands](#deployment-commands)
11. [Files That Need to Change](#files-that-need-to-change)
12. [Risk Assessment](#risk-assessment)

---

## Why We're Leaving Camber

Camber Cloud is an **HPC batch-compute platform** designed for scientific simulations, not a request-response processing service. Every limitation we've hit traces back to this fundamental mismatch.

### Verified Camber Limitations

| Limitation | Impact on Rythmiq | Evidence |
|------------|-------------------|----------|
| **No REST API** — `api.camber.cloud` does not exist | Cannot submit jobs from FastAPI backend via HTTP. Must use CLI or Python SDK. | DNS fails. Documented in `CAMBER_PLATFORM_GUIDE.md` line 926. |
| **No Docker support on BASE engine** | Cannot pre-bake dependencies into a container image | `CAMBER_PLATFORM_EVALUATION.md` |
| **No `apt-get` on BASE engine** | Cannot install system packages like Tesseract | `CAMBER_PLATFORM_EVALUATION.md` |
| **~80% of billed time is `pip install` overhead** | 65s total per job, only 14s actual processing. 51s wasted on re-installing packages every job. | `CAMBER_EXECUTION_BEHAVIOR_REPORT.md` |
| **rembg not viable** | 90s/job, 176MB U2Net model re-downloads every execution | `CAMBER_PLATFORM_EVALUATION.md` |
| **PaddleOCR platform error** | Cannot use PaddleOCR for text detection on Camber | `CAMBER_PLATFORM_EVALUATION.md` |
| **Concurrent job limit: ~4-6** | Additional jobs queue with 1-3 min delay | `CAMBER_EXECUTION_BEHAVIOR_REPORT.md` |
| **Ephemeral environments** | No warm containers, no caching, fresh `pip install` every job | Platform design |

### What Rythmiq Actually Needs

| Requirement | Camber Can Do? | Cloud Run Can Do? |
|-------------|:-:|:-:|
| HTTP POST to submit a job | ❌ | ✅ |
| Pre-baked Docker images with all dependencies | ❌ | ✅ |
| System packages (Tesseract, libGL) | ❌ | ✅ |
| rembg with pre-loaded U2Net model | ❌ | ✅ |
| PaddleOCR for text detection | ❌ | ✅ |
| Sub-20s response time | ❌ (65s) | ✅ (13-15s) |
| Scale to zero when idle | N/A | ✅ |
| Predictable per-request pricing | ❌ | ✅ |

---

## Platform Comparison

Seven alternatives were evaluated. Ranked by fit for Rythmiq's workload:

| # | Platform | Fit | Monthly Cost (1K docs/day) | Cold Start | Why / Why Not |
|---|----------|:---:|---------------------------:|:----------:|---------------|
| 🥇 | **Google Cloud Run** | ⭐⭐⭐⭐⭐ | **~$4** | 5-15s | Docker-based, scale-to-zero, HTTP native, generous free tier, Mumbai region |
| 🥈 | **AWS Lambda** | ⭐⭐⭐⭐ | ~$6 | 3-10s | 10GB container support, but 15-min timeout, complex IAM, no Mumbai advantage |
| 🥉 | **Modal Labs** | ⭐⭐⭐⭐ | ~$8 | 1-3s | Fastest cold start, Python-native, but newer platform, US-only regions |
| 4 | **Google Cloud Run Jobs** | ⭐⭐⭐ | ~$4 | 10-20s | Batch variant of Cloud Run, better for long jobs but overkill for 13s tasks |
| 5 | **AWS Fargate** | ⭐⭐⭐ | ~$15 | 30-60s | Always-on containers, predictable but more expensive, slow cold start |
| 6 | **EC2 (self-managed)** | ⭐⭐ | ~$8-30 | 0s (always on) | Full control, but ops burden (patching, scaling, monitoring) |
| 7 | **DigitalOcean Functions** | ⭐⭐ | ~$5 | 5-10s | Limited runtime, no Docker, max 512MB memory |
| 8 | **Railway / Render** | ⭐⭐ | ~$10-20 | 0-5s | Simple, but no scale-to-zero, always paying, no India region |

### Why Not AWS Lambda?

Lambda is the most common serverless choice, but Cloud Run edges it out for Rythmiq:

- **Container size**: Lambda allows 10GB images but charges more for large packages. Cloud Run has no practical size limit.
- **Timeout**: Lambda max 15 min (fine for Rythmiq's 13s jobs, but less headroom for future OCR-heavy workflows)
- **Pricing**: Cloud Run's free tier (2 million requests, 360K vCPU-seconds/month) is more generous than Lambda's (1M requests, 400K GB-seconds)
- **Simplicity**: Cloud Run is "just a Docker container that receives HTTP". No Lambda handler boilerplate, no API Gateway config, no IAM policies.
- **Region**: Both have Mumbai (`asia-south1` / `ap-south-1`), so latency is equal.

### Why Not EC2?

- **Ops burden**: Must manage OS patches, scaling policies, health checks, AMIs
- **Cost**: Minimum ~$8/month even idle (t3.micro). No scale-to-zero.
- **Overkill**: Rythmiq processes 13s jobs. A full VM is unnecessary.

---

## Why Google Cloud Run Wins

### The Pitch in One Line

> Cloud Run is "Docker container as a function" — you deploy a container, it receives HTTP requests, scales to zero when idle, and you pay only for actual compute time.

### Key Properties

| Property | Value | Rythmiq Relevance |
|----------|-------|-------------------|
| **Compute model** | Container-per-request | Each doc processing job gets its own container instance |
| **Max request timeout** | 3600s (1 hour) | Rythmiq jobs are 13-15s — massive headroom |
| **Max memory** | 32 GiB | Plenty for PaddleOCR + rembg models in memory |
| **Max vCPUs** | 8 | Pytesseract and OpenCV benefit from multi-core |
| **Container image size** | No practical limit | Can pre-bake all ML models (PaddleOCR ~200MB, U2Net ~176MB) |
| **Scale-to-zero** | Yes, by default | $0 when no students are using the app |
| **Concurrency** | 1-1000 per instance | Set to 1 for Rythmiq (each job is CPU-intensive, no sharing) |
| **Regions** | 30+ including `asia-south1` (Mumbai) | Low latency to Indian users |
| **HTTPS** | Automatic TLS | No cert management |
| **Auth** | Optional IAM, or just use bearer tokens | Simple API key auth works |

### Free Tier (Always Free, Not Trial)

| Resource | Monthly Free Allowance | Rythmiq Usage (1K docs/day) |
|----------|----------------------:|----------------------------:|
| Requests | 2,000,000 | ~30,000 |
| vCPU-seconds | 360,000 | ~45,000 (1.5 vCPU × 13s × 30K) |
| Memory GB-seconds | 360,000 | ~30,000 (1 GB × 13s × 30K) |
| Network egress | 1 GB | ~3 GB (exceeds free tier by ~$0.24) |

At 1K docs/day, Rythmiq stays **mostly within the free tier**. Estimated bill: **~$4/month** (primarily network egress and slight CPU overage).

---

## Cloud Run Deep Dive

### How a Request Flows

```
┌──────────────┐     HTTPS POST      ┌─────────────────────┐
│  FastAPI      │ ──────────────────→ │  Cloud Run Service  │
│  Backend      │                     │  (Docker container) │
│  (port 8000)  │ ←────────────────── │                     │
│               │     JSON response   │  Worker pipeline:   │
└──────────────┘                      │  FETCH → QUALITY →  │
                                      │  ENHANCE → OCR →    │
                                      │  SCHEMA → UPLOAD    │
                                      └─────────────────────┘
                                             │
                                             │ Upload result
                                             ▼
                                      ┌─────────────────────┐
                                      │  DigitalOcean Spaces │
                                      │  (S3-compatible)     │
                                      └─────────────────────┘
```

### Integration Pattern: Synchronous HTTP POST

Since Rythmiq jobs complete in 13-15 seconds (well under Cloud Run's 3600s timeout), we use the simplest pattern:

1. **FastAPI receives** `POST /jobs` from mobile app
2. **FastAPI calls** Cloud Run worker via HTTP POST with the job payload
3. **Cloud Run worker** runs the full pipeline (FETCH → QUALITY → ENHANCE → OCR → SCHEMA → UPLOAD)
4. **Worker returns** JSON result to FastAPI
5. **FastAPI writes** result to Supabase and returns to mobile app

**Why synchronous?** It eliminates webhooks, polling, and the entire callback complexity. The mobile app already waits for the job to complete (there's a loading screen). A 15-second HTTP request is perfectly fine for mobile UX.

> **Note**: This removes the need for the webhook endpoint (`POST /internal/webhooks/camber`), HMAC signing, ngrok tunnels, and the mock Camber's background task pattern. Major simplification.

### Concurrency Setting

Set **concurrency = 1** (one request per container instance). Each document processing job is CPU-bound and uses:
- Pillow / OpenCV for image enhancement
- PaddleOCR for text detection (CPU-intensive)
- rembg for background removal (U2Net inference)

Sharing a container between concurrent jobs would cause resource contention and unpredictable latencies.

Cloud Run will auto-scale by spinning up additional container instances for concurrent requests.

### Region Selection

**Recommended: `asia-south1` (Mumbai, India)**

| Factor | Detail |
|--------|--------|
| **Target users** | Indian students (NEET, JEE, UPSC, SSC, IBPS, RRB) |
| **Network latency** | ~20ms from major Indian cities to Mumbai |
| **Supabase** | Hosted in Singapore (`sgp1`) — ~40ms from Mumbai |
| **DO Spaces** | Hosted in Singapore (`sgp1`) — ~40ms from Mumbai |
| **Alternative** | `asia-southeast1` (Singapore) would co-locate with Supabase/Spaces but add ~60ms latency for Indian users |

Mumbai is the right choice. The 40ms to Singapore for Supabase/Spaces calls happens server-side, not on the user's device, and is negligible compared to the 13s processing time.

---

## Architecture: Before & After

### Before (Current — Mock Camber)

```
Mobile App ──POST /jobs──→ FastAPI (port 8000)
                              │
                              ├─→ Supabase: Create job (status: pending)
                              ├─→ MockCamberClient.submit_job()
                              │      │
                              │      └─→ Returns hardcoded dummy data
                              │          (field_1: mock_value_1, field_2: mock_value_2)
                              │          NO actual image processing
                              │
                              ├─→ Background task: POST webhook to self
                              ├─→ Webhook handler updates job in Supabase
                              └─→ Return job_id to mobile app

Mobile App ──GET /jobs/{id}──→ FastAPI ──→ Supabase ──→ Return mock results
```

**Problems:**
- No actual image processing occurs
- Webhook-to-self pattern is unnecessarily complex
- Mock data is useless for testing real UX

### After (Cloud Run)

```
Mobile App ──POST /jobs──→ FastAPI (port 8000)
                              │
                              ├─→ Supabase: Create job (status: pending)
                              ├─→ HTTP POST to Cloud Run worker
                              │      │
                              │      ├─→ FETCH: Download image from DO Spaces
                              │      ├─→ QUALITY: Assess image quality (threshold 0.80)
                              │      ├─→ ENHANCE: Resize, color-correct, sharpen
                              │      ├─→ OCR: PaddleOCR text detection
                              │      ├─→ SCHEMA: Adapt to portal specs (NEET/JEE/etc)
                              │      ├─→ UPLOAD: Upload result to DO Spaces
                              │      └─→ Return JSON result
                              │
                              ├─→ Supabase: Update job (status: completed, portal_output)
                              └─→ Return result to mobile app

Mobile App ──GET /jobs/{id}──→ FastAPI ──→ Supabase ──→ Return real results
```

**Improvements:**
- ✅ Real image processing with actual output
- ✅ Simpler flow (no webhooks, no callbacks, no ngrok)
- ✅ All ML models pre-loaded in Docker image (no pip install overhead)
- ✅ Scale-to-zero when idle ($0 cost)

---

## Migration Plan

### Phase 1: Create Cloud Run Worker Service (New Code)

**Goal**: Wrap the existing `worker/worker.py` pipeline in a thin HTTP server.

1. Create `worker/server.py` — A FastAPI/Flask app that:
   - Accepts `POST /process` with the job payload
   - Calls `process_job()` from `worker/worker.py`
   - Returns JSON result
   - Health check at `GET /health`

2. Create `Dockerfile.cloudrun` — Docker image with all dependencies pre-baked:
   - Python 3.11, Tesseract, libGL, system deps
   - Pillow, OpenCV, PaddleOCR, rembg, PyMuPDF, img2pdf
   - Pre-downloaded ML models (PaddleOCR, U2Net)

3. Deploy to Cloud Run:
   - Build and push Docker image to Google Artifact Registry
   - Deploy Cloud Run service with `concurrency=1`, `memory=2Gi`, `cpu=2`
   - Set env vars: `DO_SPACES_*` credentials for artifact storage

### Phase 2: Integrate FastAPI with Cloud Run (Modify Existing Code)

4. Create `app/api/services/cloud_run_client.py` — New execution backend:
   - Same interface as `MockCamberClient` and `CamberService` (`submit_job`, `get_job_status`)
   - Simple HTTP POST to Cloud Run URL
   - Or, refactor to a simpler synchronous call pattern

5. Update `app/api/services/camber.py` — Factory function:
   - Add `EXECUTION_BACKEND=cloudrun` option
   - Returns `CloudRunClient` instance

6. Update `app/api/config.py` — Add Cloud Run settings:
   - `CLOUD_RUN_WORKER_URL` (the deployed service URL)
   - `CLOUD_RUN_API_KEY` (optional, for authentication)

7. Update `.env`:
   - Set `EXECUTION_BACKEND=cloudrun`
   - Add `CLOUD_RUN_WORKER_URL=https://rythmiq-worker-xxxxx-el.a.run.app`

### Phase 3: Simplify Job Flow (Optional but Recommended)

8. Refactor job submission to be synchronous:
   - Remove webhook callback pattern
   - Remove ngrok dependency
   - FastAPI waits for Cloud Run response, then writes to Supabase directly
   - Cleaner error handling (HTTP errors vs webhook failures)

### Files That Need to Change

| File | Change Type | Description |
|------|:-----------:|-------------|
| `worker/server.py` | **NEW** | Thin HTTP wrapper around worker pipeline |
| `Dockerfile.cloudrun` | **NEW** | Docker image for Cloud Run with all deps |
| `app/api/services/cloud_run_client.py` | **NEW** | Cloud Run HTTP client |
| `app/api/services/camber.py` | **MODIFY** | Add `cloudrun` to factory function |
| `app/api/config.py` | **MODIFY** | Add `cloud_run_worker_url` setting |
| `.env` | **MODIFY** | Add `CLOUD_RUN_WORKER_URL`, change `EXECUTION_BACKEND` |
| `PROJECT_STATE.md` | **MODIFY** | Update architecture section |

**Total**: 3 new files, 4 modified files. The mobile app (`app-v2/`) needs **zero changes**.

---

## Dockerfile Specification

```dockerfile
# Dockerfile.cloudrun
# Rythmiq One — Cloud Run Worker
# Pre-bakes ALL dependencies to eliminate cold-start pip install overhead

FROM python:3.11-slim

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
WORKDIR /app
COPY worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download ML models (avoids runtime downloads)
# PaddleOCR detection + recognition models (~200MB)
RUN python -c "from paddleocr import PaddleOCR; PaddleOCR(use_angle_cls=True, lang='en')"

# rembg U2Net model (~176MB)
RUN python -c "from rembg import remove; from PIL import Image; import io; \
    img = Image.new('RGB', (10, 10)); \
    remove(img)"

# Copy worker code
COPY worker/ ./worker/
COPY worker/server.py ./server.py

# Cloud Run requires listening on PORT env var (default 8080)
ENV PORT=8080
EXPOSE 8080

CMD ["python", "server.py"]
```

**Expected image size**: ~1.5-2 GB (most of it is ML models)  
**Build time**: ~5-8 minutes (mostly downloading models)  
**Startup time**: ~3-5s (models already on disk, just loading into memory)

---

## Pricing Analysis

### Cost Breakdown at 1,000 Documents/Day

| Resource | Usage | Free Tier | Billable | Rate | Cost |
|----------|------:|----------:|---------:|-----:|-----:|
| **Requests** | 30K/mo | 2M/mo | 0 | $0.40/M | $0.00 |
| **vCPU-seconds** | 45K/mo | 360K/mo | 0 | $0.00002400/s | $0.00 |
| **Memory (GB-s)** | 30K/mo | 360K/mo | 0 | $0.00000250/s | $0.00 |
| **Network egress** | ~3 GB/mo | 1 GB/mo | 2 GB | $0.12/GB | $0.24 |
| **Artifact Registry** | ~2 GB | 500 MB | 1.5 GB | $0.10/GB | $0.15 |
| **Cloud Build** | ~10 min/mo | 120 min/mo | 0 | $0.003/min | $0.00 |
| | | | | **Total** | **~$0.39/mo** |

### Cost at Scale

| Daily Docs | Monthly Jobs | Est. Cost | Notes |
|-----------:|-------------:|----------:|-------|
| 100 | 3,000 | ~$0 | Fully within free tier |
| 1,000 | 30,000 | ~$4 | Mostly free tier, slight egress |
| 5,000 | 150,000 | ~$18 | Exceeding free tier on CPU |
| 10,000 | 300,000 | ~$38 | Moderate usage |
| 50,000 | 1,500,000 | ~$180 | High volume |

**Comparison**: Camber charged ~65s of compute per job (including 51s pip install waste). At $0.01/vCPU-min, that's ~$0.011/job vs Cloud Run's ~$0.0001/job. **Cloud Run is ~100× cheaper per job.**

---

## Cold Start Strategy

Cold starts occur when Cloud Run needs to spin up a new container instance (no warm instances available).

### Expected Cold Start Times

| Component | Time |
|-----------|-----:|
| Container pull (cached) | ~1-2s |
| Python interpreter startup | ~0.5s |
| Load PaddleOCR models from disk | ~3-5s |
| Load rembg U2Net from disk | ~2-3s |
| Total cold start | **~5-15s** |

### Mitigation Options

| Strategy | Cold Start | Extra Cost | Recommendation |
|----------|:----------:|:----------:|:-:|
| **Default (scale to zero)** | 5-15s | $0 | ✅ Start here |
| **Min instances = 1** | 0s | ~$5-8/mo | Consider after launch |
| **Min instances = 2** | 0s | ~$10-16/mo | For high-traffic production |
| **CPU always allocated** | 0s (faster model loads) | ~$10-15/mo | If cold starts are > 10s |

### Recommendation

**Start with defaults (scale to zero).** The first request of the day will take ~20-25s (cold start + processing). Subsequent requests will be fast (13-15s) as long as traffic is steady. The container stays warm for ~15 minutes after the last request.

If user feedback shows cold starts are a problem, set `--min-instances=1` for ~$5/month to keep one container always warm.

---

## Deployment Commands

### One-Time Setup

```bash
# 1. Install Google Cloud CLI
brew install google-cloud-sdk

# 2. Authenticate
gcloud auth login

# 3. Create project (or use existing)
gcloud projects create rythmiq-one --name="Rythmiq One"
gcloud config set project rythmiq-one

# 4. Enable required APIs
gcloud services enable \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    artifactregistry.googleapis.com

# 5. Create Artifact Registry repo (for Docker images)
gcloud artifacts repositories create rythmiq-images \
    --repository-format=docker \
    --location=asia-south1 \
    --description="Rythmiq One Docker images"
```

### Build & Deploy

```bash
# Build and push Docker image (from project root)
gcloud builds submit \
    --tag asia-south1-docker.pkg.dev/rythmiq-one/rythmiq-images/worker:latest \
    --timeout=1200 \
    -f Dockerfile.cloudrun .

# Deploy to Cloud Run
gcloud run deploy rythmiq-worker \
    --image asia-south1-docker.pkg.dev/rythmiq-one/rythmiq-images/worker:latest \
    --region asia-south1 \
    --memory 2Gi \
    --cpu 2 \
    --timeout 120 \
    --concurrency 1 \
    --min-instances 0 \
    --max-instances 10 \
    --set-env-vars "DO_SPACES_ENDPOINT=https://rythmiq-one-artifacts.sgp1.digitaloceanspaces.com" \
    --set-env-vars "DO_SPACES_REGION=sgp1" \
    --set-env-vars "DO_SPACES_BUCKET=rythmiq-one-artifacts" \
    --set-env-vars "DO_SPACES_ACCESS_KEY=<key>" \
    --set-env-vars "DO_SPACES_SECRET_KEY=<secret>" \
    --no-allow-unauthenticated
```

### Post-Deploy

```bash
# Get the service URL
gcloud run services describe rythmiq-worker \
    --region asia-south1 \
    --format="value(status.url)"
# Output: https://rythmiq-worker-xxxxx-el.a.run.app

# Test it
curl -X POST https://rythmiq-worker-xxxxx-el.a.run.app/health

# Update .env with the URL
echo "CLOUD_RUN_WORKER_URL=https://rythmiq-worker-xxxxx-el.a.run.app" >> .env
```

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|:----------:|:------:|------------|
| **Cold starts frustrate users** | Medium | Medium | Start with defaults, add `min-instances=1` if needed (~$5/mo) |
| **Docker image too large** | Low | Low | Use multi-stage build, `.dockerignore` aggressively |
| **PaddleOCR model loading fails** | Low | High | Pre-download in Dockerfile, test locally first |
| **GCP account/billing setup** | Medium | Low | Just takes time. Use free trial credits ($300). |
| **Network latency Mumbai→Singapore (Supabase/Spaces)** | Low | Low | ~40ms per call, negligible vs 13s processing |
| **Cloud Run service goes down** | Very Low | High | GCP SLA 99.95%. Auto-restart on failure. |
| **DO Spaces credentials in Cloud Run env** | Medium | Medium | Use GCP Secret Manager instead of env vars |
| **Worker pipeline bugs surface with real data** | Medium | Medium | Currently untested with real processing. Invest in integration tests. |

### Biggest Risk

The worker pipeline (`worker/worker.py`) has **never been invoked with real data in the current setup**. The mock Camber returns dummy data. When Cloud Run actually runs the pipeline, there may be bugs in the FETCH → QUALITY → ENHANCE → OCR → SCHEMA → UPLOAD chain that we haven't seen yet. Plan for debugging time.

---

## Decision Checklist

Before proceeding with implementation, confirm:

- [ ] **GCP account created** with billing enabled (free trial gives $300 credit)
- [ ] **Agreed on integration pattern**: Synchronous HTTP POST (recommended) vs async webhook
- [ ] **Agreed on auth**: API key, IAM, or both?
- [ ] **Agreed on cold start tolerance**: Scale-to-zero (free, 5-15s delay) vs min-instances (paid, instant)
- [ ] **Worker pipeline tested locally**: Run `worker/worker.py` with a real image before deploying

---

## References

| Document | Relevance |
|----------|-----------|
| [PROJECT_STATE.md](PROJECT_STATE.md) | Current architecture, hard constraints, known issues |
| [docs/CAMBER_PLATFORM_EVALUATION.md](docs/CAMBER_PLATFORM_EVALUATION.md) | Benchmark data showing Camber limitations |
| [docs/CAMBER_EXECUTION_BEHAVIOR_REPORT.md](docs/CAMBER_EXECUTION_BEHAVIOR_REPORT.md) | Real execution times (13-15s processing, 65s total with pip overhead) |
| [worker/worker.py](worker/worker.py) | Existing pipeline code that Cloud Run will execute |
| [app/api/services/camber.py](app/api/services/camber.py) | Factory function where Cloud Run client will be added |
| [app/api/config.py](app/api/config.py) | Settings that need `CLOUD_RUN_WORKER_URL` added |
