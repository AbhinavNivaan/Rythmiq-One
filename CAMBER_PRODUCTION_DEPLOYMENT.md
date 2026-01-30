# Camber Production Deployment Guide

**Date**: 2026-01-30  
**Goal**: Deploy CPU worker to REAL Camber and execute first successful job

---

## 1. Camber Account & Credentials

### Required Credentials

| Credential | Format | Source |
|------------|--------|--------|
| `CAMBER_API_KEY` | `sk-xxxxxxxxxxxxxxx` | Camber Dashboard → API Keys |
| `CAMBER_API_URL` | `https://api.camber.cloud` | Camber Docs (default) |
| `CAMBER_APP_NAME` | `rythmiq-worker-python-v2` | You create in Camber Dashboard |

### Where to Store

```bash
# LOCAL DEVELOPMENT - .env file
CAMBER_API_KEY=sk-your-actual-key
CAMBER_API_URL=https://api.camber.cloud
CAMBER_APP_NAME=rythmiq-worker-python-v2
EXECUTION_BACKEND=camber

# PRODUCTION - Platform Secrets (DigitalOcean App Platform / Railway / etc.)
# NEVER commit real keys to .env file
```

### Verify Camber Account Access

```bash
# Test API key validity
curl -s -w "\n%{http_code}" \
  -H "Authorization: Bearer $CAMBER_API_KEY" \
  https://api.camber.cloud/v1/apps | head -20
# Expected: 200 with JSON list of apps (may be empty)
```

---

## 2. Worker Image Preparation

### Dockerfile Review

The existing `worker/Dockerfile.cpu` is **production-ready** with:
- ✅ Multi-stage build (builder → runtime)
- ✅ Non-root user execution
- ✅ Pre-downloaded PaddleOCR models (fast cold start)
- ✅ CPU-only (no GPU dependencies)
- ✅ Pinned dependency versions
- ✅ Health check via import validation

### Build Command (Exact)

```bash
# From repo root
cd "/Users/abhinav/Rythmiq One"

docker build \
  -f worker/Dockerfile.cpu \
  -t rythmiq-worker-cpu:v1 \
  ./worker
```

### Verify Build

```bash
# Test the image locally
echo '{"job_id": "test-123", "artifact_url": "https://example.com/test.jpg", "schema": {"type": "receipt"}}' | \
  docker run -i --rm rythmiq-worker-cpu:v1

# Expected: JSON output (may be error due to missing real artifact, but confirms image runs)
```

---

## 3. Docker Registry Decision

### Recommendation: **DigitalOcean Container Registry (DOCR)**

**Justification**:
1. Already using DO Spaces for storage — unified billing & auth
2. Native integration with DO App Platform if you deploy API there
3. No Docker Hub rate limits

### Alternative: GitHub Container Registry (ghcr.io)

If you prefer GitHub:
- Free for public repos, included with private repos
- Native GitHub Actions integration

### DOCR Setup & Push

```bash
# 1. Install doctl CLI if needed
brew install doctl

# 2. Authenticate
doctl auth init  # Follow prompts with your DO API token

# 3. Create registry (one-time)
doctl registry create rythmiq-registry --region nyc3

# 4. Login to registry
doctl registry login

# 5. Tag image for DOCR
docker tag rythmiq-worker-cpu:v1 \
  registry.digitalocean.com/rythmiq-registry/worker-cpu:v1

# 6. Push
docker push registry.digitalocean.com/rythmiq-registry/worker-cpu:v1
```

### Final Image Reference for Camber

```
registry.digitalocean.com/rythmiq-registry/worker-cpu:v1
```

### Grant Camber Access to DOCR

```bash
# Generate read-only credentials for Camber
doctl registry docker-config --read-write=false

# Copy the JSON output — this goes into Camber dashboard as Docker credentials
```

---

## 4. Camber App Configuration

### Current `camber-app.json` (NEEDS UPDATE)

The existing config uses `stash://` bundle which is for code-only execution. For Docker image execution, we need the `image` field.

### Updated `camber-app.json`

```json
{
  "name": "rythmiq-worker-python-v2",
  "engineType": "container",
  "image": "registry.digitalocean.com/rythmiq-registry/worker-cpu:v1",
  "command": ["python", "worker.py"],
  "resources": {
    "cpu": "1",
    "memory": "2Gi"
  },
  "timeout": 300,
  "env": {
    "PYTHONUNBUFFERED": "1"
  }
}
```

### Deploy App to Camber

```bash
# Using Camber CLI (install if needed: pip install camber-cli)
camber app create --file camber-app.json

# Or via API:
curl -X POST https://api.camber.cloud/v1/apps \
  -H "Authorization: Bearer $CAMBER_API_KEY" \
  -H "Content-Type: application/json" \
  -d @camber-app.json
```

### Cold Start & Billing Considerations

| Factor | Setting | Impact |
|--------|---------|--------|
| Image size | ~1.2GB (with PaddleOCR) | First pull ~30-60s |
| Pre-downloaded models | Yes | Avoids model download at runtime |
| CPU allocation | 1 core | Sufficient for OCR |
| Memory | 2Gi | PaddleOCR needs ~1.5GB |
| Timeout | 300s | 5 min max per job |

**Billing tip**: Camber bills per-second of execution. Our OCR jobs average 15-30s.

---

## 5. API Configuration

### Environment Variables for Camber Integration

Create or update `.env.camber` in the project root:

```bash
# .env.camber - Camber Production Configuration
# Copy this to .env when deploying with real Camber

# ============================================================================
# EXECUTION BACKEND
# ============================================================================
EXECUTION_BACKEND=camber
CAMBER_API_URL=https://api.camber.cloud
CAMBER_API_KEY=sk-your-actual-key-here
CAMBER_APP_NAME=rythmiq-worker-python-v2

# ============================================================================
# WEBHOOK (Camber calls this URL on job completion)
# ============================================================================
WEBHOOK_SECRET=your-32-char-random-secret-here
# For production: use your deployed API URL
# WEBHOOK_BASE_URL=https://api.rythmiq.app

# ============================================================================
# SUPABASE
# ============================================================================
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_ROLE_KEY=eyJ...
SUPABASE_JWT_SECRET=your-jwt-secret

# ============================================================================
# DIGITALOCEAN SPACES
# ============================================================================
DO_SPACES_ENDPOINT=https://nyc3.digitaloceanspaces.com
DO_SPACES_REGION=nyc3
DO_SPACES_BUCKET=rythmiq-production
DO_SPACES_ACCESS_KEY=your-spaces-key
DO_SPACES_SECRET_KEY=your-spaces-secret

# ============================================================================
# SERVICE
# ============================================================================
SERVICE_ENV=prod
API_PORT=8000
```

### Verify Config Loads Correctly

```bash
cd "/Users/abhinav/Rythmiq One"
cp .env.camber .env

# Start API and check logs
python -c "from app.api.config import get_settings; s = get_settings(); print(f'Backend: {s.execution_backend}'); print(f'Camber URL: {s.camber_api_url}')"

# Expected:
# Backend: camber
# Camber URL: https://api.camber.cloud
```

---

## 6. Webhook Connectivity

### Webhook Endpoint

```
POST /internal/webhooks/camber
```

### Required Headers

| Header | Value | Purpose |
|--------|-------|---------|
| `X-Webhook-Secret` | `$WEBHOOK_SECRET` | HMAC verification |
| `Content-Type` | `application/json` | Payload format |

### Expected Payload from Camber

```json
{
  "camber_job_id": "cj_abc123",
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "success",
  "result": {
    "status": "SUCCESS",
    "job_id": "550e8400-e29b-41d4-a716-446655440000",
    "result": {
      "structured": {...},
      "confidence": {...}
    }
  }
}
```

### Option A: Temporary (ngrok for local testing)

```bash
# Install ngrok
brew install ngrok

# Start API locally
cd "/Users/abhinav/Rythmiq One"
uvicorn app.api.main:app --host 0.0.0.0 --port 8000

# In another terminal, expose it
ngrok http 8000

# Copy the HTTPS URL (e.g., https://abc123.ngrok.io)
# Your webhook URL becomes:
# https://abc123.ngrok.io/internal/webhooks/camber
```

### Option B: Production (Cloud Deploy)

For production, deploy the API to a cloud platform. Example for DigitalOcean App Platform:

```yaml
# app.yaml for DO App Platform
name: rythmiq-api
services:
  - name: api
    github:
      repo: your-org/rythmiq-one
      branch: main
      deploy_on_push: true
    source_dir: /
    dockerfile_path: Dockerfile.api-gateway
    http_port: 8000
    routes:
      - path: /
    envs:
      - key: EXECUTION_BACKEND
        value: camber
      - key: CAMBER_API_URL
        value: https://api.camber.cloud
      - key: CAMBER_API_KEY
        type: SECRET
        value: ${CAMBER_API_KEY}
      - key: WEBHOOK_SECRET
        type: SECRET
        value: ${WEBHOOK_SECRET}
      # ... other env vars
```

Production webhook URL format:
```
https://api.rythmiq.app/internal/webhooks/camber
```

### Configure Webhook URL in Camber

The webhook URL is passed in the job submission payload. The `CamberService.submit_job()` already handles this. You need to ensure the API server is reachable from the internet.

For Camber to call back:
1. API must be publicly accessible (ngrok or cloud deploy)
2. `WEBHOOK_SECRET` must match between API and worker payload
3. No firewall blocking inbound HTTPS

---

## 7. First Real Job Execution

### Test Job Payload

Create `test-job-camber.json`:

```json
{
  "artifact_url": "https://your-spaces-bucket.nyc3.digitaloceanspaces.com/test/receipt.jpg",
  "schema_id": "receipt",
  "options": {
    "fast_path": true,
    "quality_threshold": 0.5
  }
}
```

### Submit Job via API

```bash
# Get auth token (from Supabase or your auth system)
TOKEN="your-jwt-token"

# Submit job
curl -X POST https://your-api-url/jobs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d @test-job-camber.json
```

### Expected Response

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending"
}
```

### Full Lifecycle Trace

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 1: API receives POST /jobs                                             │
│ Log: "Job created" job_id=550e8400... status=pending                        │
│ DB: INSERT INTO jobs (id, status, ...) VALUES (...)                         │
├─────────────────────────────────────────────────────────────────────────────┤
│ STEP 2: API calls Camber API                                                │
│ Log: "Camber job submitted" job_id=550e... camber_job_id=cj_abc123          │
│ HTTP: POST https://api.camber.cloud/v1/jobs                                 │
│ DB: UPDATE jobs SET camber_job_id='cj_abc123', status='processing'          │
├─────────────────────────────────────────────────────────────────────────────┤
│ STEP 3: Camber pulls Docker image                                           │
│ Image: registry.digitalocean.com/rythmiq-registry/worker-cpu:v1             │
│ Time: ~5-30s (warm) or 30-60s (cold)                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│ STEP 4: Worker executes                                                     │
│ STDIN: {"job_id": "550e...", "artifact_url": "...", "schema": {...}}        │
│ Pipeline: FETCH → OCR → SCHEMA → OUTPUT                                     │
│ STDOUT: {"status": "SUCCESS", "job_id": "550e...", "result": {...}}         │
│ Time: 15-30s typical                                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│ STEP 5: Camber calls webhook                                                │
│ HTTP: POST /internal/webhooks/camber                                        │
│ Headers: X-Webhook-Secret: $WEBHOOK_SECRET                                  │
│ Body: {"camber_job_id": "cj_abc123", "job_id": "550e...", "status": "..."}  │
├─────────────────────────────────────────────────────────────────────────────┤
│ STEP 6: API processes webhook                                               │
│ Log: "Camber webhook received" camber_job_id=cj_abc123 job_id=550e...       │
│ Log: "Job state transitioned" old_status=processing new_status=completed    │
│ DB: UPDATE jobs SET status='completed', output_metadata={...}               │
│ DB: INSERT/UPDATE documents (portal_outputs, canonical_output)              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Log Markers to Look For

| Stage | Log Message | Key Fields |
|-------|-------------|------------|
| Job Submit | "Job created" | `job_id`, `user_id` |
| Camber Submit | "Camber job submitted" | `job_id`, `camber_job_id` |
| Webhook Received | "Camber webhook received" | `camber_job_id`, `status` |
| State Transition | "Job state transitioned" | `old_status`, `new_status` |
| Output Packaged | "Output packaged successfully" | `job_id`, `output_path` |

---

## 8. Validation Checklist

Run through this checklist after submitting a test job:

### Pre-Flight

- [ ] `.env` has `EXECUTION_BACKEND=camber`
- [ ] `CAMBER_API_KEY` is valid (test with curl)
- [ ] `CAMBER_APP_NAME` matches Camber dashboard
- [ ] Docker image pushed to registry
- [ ] Camber app configured with correct image reference
- [ ] API is publicly reachable (ngrok or cloud)
- [ ] `WEBHOOK_SECRET` is set (32+ chars recommended)

### Job Submission

- [ ] Job ID returned in API response
- [ ] Job status is `pending` initially
- [ ] DB record created with `status=pending`

### Camber Execution

- [ ] Log shows "Camber job submitted"
- [ ] `camber_job_id` present in log (format: `cj_xxxxx`)
- [ ] DB record updated with `camber_job_id`
- [ ] Job status transitions to `processing`

### Worker Execution

- [ ] Camber dashboard shows job running
- [ ] Worker execution time logged (typically 15-30s)
- [ ] No worker errors in Camber logs

### Webhook Delivery

- [ ] API log shows "Camber webhook received"
- [ ] Webhook received exactly ONCE (check for duplicates)
- [ ] `X-Webhook-Secret` header verified (no 401)
- [ ] Webhook payload has correct `job_id`

### Completion

- [ ] Job status is `completed` in DB
- [ ] `output_metadata` populated in jobs table
- [ ] Document record created in `documents` table
- [ ] GET /jobs/:jobId returns `state: completed`

### Error Handling (if job fails)

- [ ] Job status is `failed` in DB
- [ ] Error code present in job record
- [ ] Webhook still acknowledged (200 OK)
- [ ] No partial state (either completed or failed, not stuck)

---

## Quick Commands Reference

```bash
# Build image
docker build -f worker/Dockerfile.cpu -t rythmiq-worker-cpu:v1 ./worker

# Push to DOCR
docker tag rythmiq-worker-cpu:v1 registry.digitalocean.com/rythmiq-registry/worker-cpu:v1
docker push registry.digitalocean.com/rythmiq-registry/worker-cpu:v1

# Start API locally
uvicorn app.api.main:app --host 0.0.0.0 --port 8000 --reload

# Expose locally (ngrok)
ngrok http 8000

# Check job status
curl -H "Authorization: Bearer $TOKEN" https://your-api/jobs/$JOB_ID

# Tail Camber logs (if CLI available)
camber logs --app rythmiq-worker-python-v2 --follow

# Check DB directly (via Supabase)
SELECT id, status, camber_job_id, created_at, updated_at 
FROM jobs 
WHERE id = '$JOB_ID';
```

---

## Troubleshooting

### Job stuck in `pending`

1. Check API logs for Camber submission errors
2. Verify `CAMBER_API_KEY` is valid
3. Verify `CAMBER_APP_NAME` exists in Camber

### Job stuck in `processing`

1. Check Camber dashboard for worker status
2. Check if webhook URL is reachable
3. Verify `WEBHOOK_SECRET` matches

### Webhook returns 401

1. `X-Webhook-Secret` header missing or wrong
2. Check that worker payload includes correct secret

### Worker crashes with OOM

1. Increase memory in `camber-app.json` to `4Gi`
2. Check if processing very large images

### Cold start too slow

1. Pre-download models (already done in Dockerfile)
2. Consider keeping a warm instance via Camber settings
