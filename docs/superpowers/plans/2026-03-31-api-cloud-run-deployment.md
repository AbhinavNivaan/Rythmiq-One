# API Cloud Run Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy the Rythmiq One FastAPI API to Google Cloud Run with a dedicated service account, all secrets in Secret Manager, and a Cloud Scheduler job for 6-hourly storage cleanup.

**Architecture:** Multi-stage Dockerfile (base → builder → runtime) built from the project root, deployed via a standalone `cloudbuild-api.yaml`. Secrets managed in GCP Secret Manager and bound as env vars to the Cloud Run service. Cloud Scheduler calls `/internal/cleanup/raw-uploads` with an HMAC header every 6 hours.

**Tech Stack:** Python 3.11, FastAPI, uvicorn, GCP Cloud Run, GCP Cloud Build, GCP Secret Manager, GCP Cloud Scheduler, Artifact Registry (`asia-south1-docker.pkg.dev/rythmiq-one/rythmiq-images/`)

---

## File Map

| Action | Path | Purpose |
|--------|------|---------|
| Create | `app/api/Dockerfile` | Multi-stage production image for the API |
| Create | `cloudbuild-api.yaml` | Cloud Build pipeline: build → smoke test → push → deploy |

No existing files are modified.

---

## Task 1: Write `app/api/Dockerfile`

**Files:**
- Create: `app/api/Dockerfile`

- [ ] **Step 1: Write the Dockerfile**

```dockerfile
# app/api/Dockerfile
# Rythmiq One — Cloud Run API
#
# Multi-stage build: builder installs deps into /opt/venv, runtime copies only venv + code.
# Build context: project root (.)
#
# Build:
#   docker build --platform linux/amd64 -f app/api/Dockerfile -t rythmiq/api:local .
#
# Run (with fake env for local smoke test):
#   docker run --rm -p 8080:8080 \
#     -e SUPABASE_URL=http://test -e SUPABASE_ANON_KEY=test \
#     -e SUPABASE_SERVICE_ROLE_KEY=test -e SUPABASE_JWT_SECRET=test \
#     -e DO_SPACES_ENDPOINT=https://test.com -e DO_SPACES_REGION=sgp1 \
#     -e DO_SPACES_BUCKET=test -e DO_SPACES_ACCESS_KEY=test \
#     -e DO_SPACES_SECRET_KEY=test -e WEBHOOK_SECRET=test \
#     rythmiq/api:local

# -----------------------------------------------------------------------------
# Stage 1: Base — minimal system deps
# -----------------------------------------------------------------------------
FROM --platform=linux/amd64 python:3.11-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# -----------------------------------------------------------------------------
# Stage 2: Builder — install Python packages into /opt/venv
# -----------------------------------------------------------------------------
FROM base AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY app/api/requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip setuptools wheel \
    && pip install -r /tmp/requirements.txt \
    && find /opt/venv -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true \
    && find /opt/venv -type f -name "*.pyc" -delete 2>/dev/null || true

# -----------------------------------------------------------------------------
# Stage 3: Runtime — minimal production image
# -----------------------------------------------------------------------------
FROM base AS runtime

# Non-root user
RUN useradd --create-home --shell /bin/bash --uid 1000 api

# Copy venv from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Copy app source (app/ includes app/__init__.py + app/api/)
COPY --chown=api:api app/ ./app/

# PYTHONPATH must point to /app so 'from app.api...' imports resolve
ENV PYTHONPATH=/app

USER api

# Verify all critical imports succeed at build time
RUN python -c "\
import sys; print(f'Python: {sys.version}'); \
import fastapi; print(f'fastapi: {fastapi.__version__}'); \
import uvicorn; print(f'uvicorn: ok'); \
import boto3; print(f'boto3: {boto3.__version__}'); \
import supabase; print(f'supabase: ok'); \
import httpx; print(f'httpx: {httpx.__version__}'); \
print('All imports OK'); \
"

ENV PORT=8080
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

CMD ["python", "-m", "uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

- [ ] **Step 2: Build the image locally to verify it compiles**

```bash
cd "/Users/abhinav/Rythmiq One"
docker build --platform linux/amd64 -f app/api/Dockerfile -t rythmiq/api:local .
```

Expected: build completes, final line shows `All imports OK` from the RUN verification step. If imports fail, the build exits non-zero.

- [ ] **Step 3: Run a local smoke test against /health**

```bash
docker run -d --name api-smoke-local \
  -p 8080:8080 \
  -e SUPABASE_URL=http://smoke-test \
  -e SUPABASE_ANON_KEY=smoke-test \
  -e SUPABASE_SERVICE_ROLE_KEY=smoke-test \
  -e SUPABASE_JWT_SECRET=smoke-test \
  -e DO_SPACES_ENDPOINT=https://sgp1.digitaloceanspaces.com \
  -e DO_SPACES_REGION=sgp1 \
  -e DO_SPACES_BUCKET=smoke-test \
  -e DO_SPACES_ACCESS_KEY=smoke-test \
  -e DO_SPACES_SECRET_KEY=smoke-test \
  -e WEBHOOK_SECRET=smoke-test \
  rythmiq/api:local

sleep 6
curl -sf http://localhost:8080/health
docker stop api-smoke-local && docker rm api-smoke-local
```

Expected: `{"status":"ok"}` printed. If the curl fails, run `docker logs api-smoke-local` to see startup errors.

- [ ] **Step 4: Commit**

```bash
git add app/api/Dockerfile
git commit -m "feat(api): add Cloud Run Dockerfile"
```

---

## Task 2: Write `cloudbuild-api.yaml`

**Files:**
- Create: `cloudbuild-api.yaml`

- [ ] **Step 1: Write the file**

```yaml
# cloudbuild-api.yaml
# Rythmiq One — API Cloud Run build + deploy pipeline
#
# Separate from cloudbuild.yaml (worker) to allow independent triggering.
# Worker builds take ~20 min (ML deps); API builds take ~2 min.
#
# Trigger:
#   gcloud builds submit --config cloudbuild-api.yaml .

steps:
  # Step 1: Build API Docker image
  - name: 'gcr.io/cloud-builders/docker'
    args:
      - 'build'
      - '--platform=linux/amd64'
      - '-t'
      - 'asia-south1-docker.pkg.dev/rythmiq-one/rythmiq-images/api:latest'
      - '-f'
      - 'app/api/Dockerfile'
      - '.'

  # Step 2: Smoke test — start API with fake env vars, verify /health returns 200
  # Uses fake values: /health does not touch DB or storage.
  - name: 'gcr.io/cloud-builders/docker'
    entrypoint: bash
    args:
      - '-c'
      - |
        docker run -d --name api-smoke \
          -p 8080:8080 \
          -e SUPABASE_URL=http://smoke-test \
          -e SUPABASE_ANON_KEY=smoke-test \
          -e SUPABASE_SERVICE_ROLE_KEY=smoke-test \
          -e SUPABASE_JWT_SECRET=smoke-test \
          -e DO_SPACES_ENDPOINT=https://sgp1.digitaloceanspaces.com \
          -e DO_SPACES_REGION=sgp1 \
          -e DO_SPACES_BUCKET=smoke-test \
          -e DO_SPACES_ACCESS_KEY=smoke-test \
          -e DO_SPACES_SECRET_KEY=smoke-test \
          -e WEBHOOK_SECRET=smoke-test \
          asia-south1-docker.pkg.dev/rythmiq-one/rythmiq-images/api:latest
        sleep 8
        curl -sf http://localhost:8080/health \
          || (echo "=== SMOKE TEST FAILED ===" && docker logs api-smoke && docker stop api-smoke && exit 1)
        echo "Smoke test passed: $(curl -s http://localhost:8080/health)"
        docker stop api-smoke

  # Step 3: Push to Artifact Registry
  - name: 'gcr.io/cloud-builders/docker'
    args:
      - 'push'
      - 'asia-south1-docker.pkg.dev/rythmiq-one/rythmiq-images/api:latest'

  # Step 4: Deploy to Cloud Run
  # Uses bash entrypoint to avoid YAML multiline issues with --set-secrets value.
  - name: 'gcr.io/google.com/cloudsdktool/cloud-sdk'
    entrypoint: bash
    args:
      - '-c'
      - |
        gcloud run deploy rythmiq-api \
          --image=asia-south1-docker.pkg.dev/rythmiq-one/rythmiq-images/api:latest \
          --region=asia-south1 \
          --allow-unauthenticated \
          --cpu=1 \
          --memory=1Gi \
          --max-instances=10 \
          --timeout=60 \
          --cpu-boost \
          --project=rythmiq-one \
          --service-account=rythmiq-api@rythmiq-one.iam.gserviceaccount.com \
          --set-env-vars="SERVICE_ENV=production,EXECUTION_BACKEND=cloudrun,CLOUD_RUN_WORKER_URL=https://rythmiq-worker-1048753379343.asia-south1.run.app" \
          --set-secrets="SUPABASE_URL=rythmiq-api-supabase-url:latest,SUPABASE_ANON_KEY=rythmiq-api-supabase-anon-key:latest,SUPABASE_SERVICE_ROLE_KEY=rythmiq-api-supabase-service-role-key:latest,SUPABASE_JWT_SECRET=rythmiq-api-supabase-jwt-secret:latest,DO_SPACES_ACCESS_KEY=rythmiq-api-spaces-access-key:latest,DO_SPACES_SECRET_KEY=rythmiq-api-spaces-secret-key:latest,DO_SPACES_ENDPOINT=rythmiq-api-spaces-endpoint:latest,DO_SPACES_REGION=rythmiq-api-spaces-region:latest,DO_SPACES_BUCKET=rythmiq-api-spaces-bucket:latest,WEBHOOK_SECRET=rythmiq-api-webhook-secret:latest,INTERNAL_CLEANUP_SECRET=rythmiq-api-internal-cleanup-secret:latest"

images:
  - 'asia-south1-docker.pkg.dev/rythmiq-one/rythmiq-images/api:latest'

timeout: 600s

options:
  machineType: 'E2_HIGHCPU_8'
```

- [ ] **Step 2: Commit**

```bash
git add cloudbuild-api.yaml
git commit -m "feat(api): add Cloud Run build + deploy pipeline"
```

---

## Task 3: Infrastructure Setup (Run These Commands Yourself)

This task is manual shell commands — no code to write. Run them in your terminal before triggering the first Cloud Build.

**Files:** none

- [ ] **Step 1: Create the `rythmiq-api` service account**

```bash
gcloud iam service-accounts create rythmiq-api \
  --display-name="Rythmiq API Service Account" \
  --project=rythmiq-one
```

Expected: `Created service account [rythmiq-api].`

- [ ] **Step 2: Create the 10 new secrets using `read -s` (same pattern as session 12)**

Run each block one at a time. The `read -s` hides input so the value doesn't appear in your shell history or this chat.

```bash
# SUPABASE_URL
read -s SECRET_VAL
printf "%s" "$SECRET_VAL" | gcloud secrets create rythmiq-api-supabase-url \
  --data-file=- --project=rythmiq-one
```

```bash
# SUPABASE_ANON_KEY
read -s SECRET_VAL
printf "%s" "$SECRET_VAL" | gcloud secrets create rythmiq-api-supabase-anon-key \
  --data-file=- --project=rythmiq-one
```

```bash
# SUPABASE_SERVICE_ROLE_KEY
read -s SECRET_VAL
printf "%s" "$SECRET_VAL" | gcloud secrets create rythmiq-api-supabase-service-role-key \
  --data-file=- --project=rythmiq-one
```

```bash
# SUPABASE_JWT_SECRET
read -s SECRET_VAL
printf "%s" "$SECRET_VAL" | gcloud secrets create rythmiq-api-supabase-jwt-secret \
  --data-file=- --project=rythmiq-one
```

```bash
# DO_SPACES_ACCESS_KEY
read -s SECRET_VAL
printf "%s" "$SECRET_VAL" | gcloud secrets create rythmiq-api-spaces-access-key \
  --data-file=- --project=rythmiq-one
```

```bash
# DO_SPACES_SECRET_KEY
read -s SECRET_VAL
printf "%s" "$SECRET_VAL" | gcloud secrets create rythmiq-api-spaces-secret-key \
  --data-file=- --project=rythmiq-one
```

```bash
# DO_SPACES_ENDPOINT
read -s SECRET_VAL
printf "%s" "$SECRET_VAL" | gcloud secrets create rythmiq-api-spaces-endpoint \
  --data-file=- --project=rythmiq-one
```

```bash
# DO_SPACES_REGION
read -s SECRET_VAL
printf "%s" "$SECRET_VAL" | gcloud secrets create rythmiq-api-spaces-region \
  --data-file=- --project=rythmiq-one
```

```bash
# DO_SPACES_BUCKET
read -s SECRET_VAL
printf "%s" "$SECRET_VAL" | gcloud secrets create rythmiq-api-spaces-bucket \
  --data-file=- --project=rythmiq-one
```

```bash
# WEBHOOK_SECRET
read -s SECRET_VAL
printf "%s" "$SECRET_VAL" | gcloud secrets create rythmiq-api-webhook-secret \
  --data-file=- --project=rythmiq-one
```

Expected for each: `Created version [1] of the secret [rythmiq-api-*].`

- [ ] **Step 3: Verify all 11 secrets exist (10 new + 1 pre-existing)**

```bash
gcloud secrets list --project=rythmiq-one --filter="name:rythmiq-api-" \
  --format="table(name)"
```

Expected: all 11 names listed:
- `rythmiq-api-supabase-url`
- `rythmiq-api-supabase-anon-key`
- `rythmiq-api-supabase-service-role-key`
- `rythmiq-api-supabase-jwt-secret`
- `rythmiq-api-spaces-access-key`
- `rythmiq-api-spaces-secret-key`
- `rythmiq-api-spaces-endpoint`
- `rythmiq-api-spaces-region`
- `rythmiq-api-spaces-bucket`
- `rythmiq-api-webhook-secret`
- `rythmiq-api-internal-cleanup-secret`

- [ ] **Step 4: Grant `rythmiq-api` SA secret accessor on all 11 secrets**

```bash
for SECRET in \
  rythmiq-api-supabase-url \
  rythmiq-api-supabase-anon-key \
  rythmiq-api-supabase-service-role-key \
  rythmiq-api-supabase-jwt-secret \
  rythmiq-api-spaces-access-key \
  rythmiq-api-spaces-secret-key \
  rythmiq-api-spaces-endpoint \
  rythmiq-api-spaces-region \
  rythmiq-api-spaces-bucket \
  rythmiq-api-webhook-secret \
  rythmiq-api-internal-cleanup-secret; do
  gcloud secrets add-iam-policy-binding "$SECRET" \
    --member="serviceAccount:rythmiq-api@rythmiq-one.iam.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor" \
    --project=rythmiq-one
  echo "Granted secretAccessor on $SECRET"
done
```

Expected: 11 lines of `Granted secretAccessor on rythmiq-api-*`.

- [ ] **Step 5: Allow Cloud Build to deploy using `rythmiq-api` as the service identity**

Cloud Build runs as `<project-number>@cloudbuild.gserviceaccount.com`. To deploy a Cloud Run service with `--service-account=rythmiq-api@...`, Cloud Build needs `iam.serviceAccountUser` on that SA.

```bash
# Get your project number
PROJECT_NUMBER=$(gcloud projects describe rythmiq-one --format="value(projectNumber)")

gcloud iam service-accounts add-iam-policy-binding \
  rythmiq-api@rythmiq-one.iam.gserviceaccount.com \
  --member="serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser" \
  --project=rythmiq-one
```

Expected: `Updated IAM policy for serviceAccount [rythmiq-api@rythmiq-one.iam.gserviceaccount.com].`

---

## Task 4: First Deploy

- [ ] **Step 1: Trigger Cloud Build from project root**

```bash
cd "/Users/abhinav/Rythmiq One"
gcloud builds submit --config cloudbuild-api.yaml . --project=rythmiq-one
```

Watch the output. Steps in order:
1. Docker build → should show `All imports OK` from RUN verification
2. Smoke test → should print `Smoke test passed: {"status":"ok"}`
3. Push to Artifact Registry
4. `gcloud run deploy` → should print the service URL at the end

Expected final lines:
```
Service [rythmiq-api] revision [rythmiq-api-00001-xxx] has been deployed and is serving 100 percent of traffic.
Service URL: https://rythmiq-api-<hash>-<region>.a.run.app
```

- [ ] **Step 2: Save the API URL**

Note the service URL from the deploy output. You'll need it for the Cloud Scheduler step.

```bash
# Retrieve URL if you missed it
gcloud run services describe rythmiq-api \
  --region=asia-south1 \
  --project=rythmiq-one \
  --format="value(status.url)"
```

- [ ] **Step 3: Verify /health is live**

```bash
API_URL=$(gcloud run services describe rythmiq-api \
  --region=asia-south1 --project=rythmiq-one --format="value(status.url)")
curl -sf "$API_URL/health"
```

Expected: `{"status":"ok"}`

- [ ] **Step 4: Verify /ready is live**

```bash
curl -sf "$API_URL/ready"
```

Expected: `{"status":"ready","service":"api-gateway"}`

---

## Task 5: Create Cloud Scheduler Job

- [ ] **Step 1: Fetch the INTERNAL_CLEANUP_SECRET value**

```bash
CLEANUP_SECRET=$(gcloud secrets versions access latest \
  --secret=rythmiq-api-internal-cleanup-secret \
  --project=rythmiq-one)
echo "Secret fetched (${#CLEANUP_SECRET} chars)"
```

Expected: `Secret fetched (N chars)` — confirms the secret is accessible. Do not echo the value.

- [ ] **Step 2: Get the API URL**

```bash
API_URL=$(gcloud run services describe rythmiq-api \
  --region=asia-south1 --project=rythmiq-one --format="value(status.url)")
echo "API URL: $API_URL"
```

- [ ] **Step 3: Create the Cloud Scheduler job**

```bash
gcloud scheduler jobs create http rythmiq-cleanup-raw-uploads \
  --location=asia-south1 \
  --schedule="0 */6 * * *" \
  --uri="$API_URL/internal/cleanup/raw-uploads" \
  --http-method=POST \
  --headers="X-Internal-Secret=$CLEANUP_SECRET,Content-Type=application/json" \
  --message-body='{}' \
  --time-zone="Asia/Kolkata" \
  --project=rythmiq-one
```

Expected: `Created job [rythmiq-cleanup-raw-uploads].`

**Secret rotation note:** If `rythmiq-api-internal-cleanup-secret` is ever rotated, update this job:
```bash
gcloud scheduler jobs update http rythmiq-cleanup-raw-uploads \
  --location=asia-south1 \
  --update-headers "X-Internal-Secret=$(gcloud secrets versions access latest --secret=rythmiq-api-internal-cleanup-secret --project=rythmiq-one)"
```

- [ ] **Step 4: Manually trigger the scheduler job to verify end-to-end**

```bash
gcloud scheduler jobs run rythmiq-cleanup-raw-uploads \
  --location=asia-south1 \
  --project=rythmiq-one
```

Expected: command completes (Cloud Scheduler fired the HTTP request).

- [ ] **Step 5: Check API logs to confirm the cleanup endpoint was called**

```bash
gcloud logging read \
  'resource.type="cloud_run_revision" AND resource.labels.service_name="rythmiq-api" AND textPayload=~"cleanup"' \
  --project=rythmiq-one \
  --limit=20 \
  --format="table(timestamp, textPayload)"
```

Expected: log entries showing the cleanup endpoint was hit and returned a result (deleted count or "0 raw uploads found").

---

## Post-Deploy Checklist

- [ ] `/health` returns `{"status":"ok"}`
- [ ] `/ready` returns `{"status":"ready","service":"api-gateway"}`
- [ ] Cloud Scheduler job exists and manual trigger shows logs in Cloud Run
- [ ] All 11 secrets bound (verify via `gcloud run services describe rythmiq-api --region=asia-south1 --format=yaml | grep secretKeyRef`)
- [ ] Service account is `rythmiq-api@rythmiq-one.iam.gserviceaccount.com` (not the worker SA)
