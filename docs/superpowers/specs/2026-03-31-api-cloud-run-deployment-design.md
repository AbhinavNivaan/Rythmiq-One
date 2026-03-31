# API Cloud Run Deployment — Design Spec

_Date: 2026-03-31_
_Status: Approved_

---

## Overview

Deploy the Rythmiq One FastAPI API (`app/api/`) to Google Cloud Run so that:
1. The API is publicly accessible (replacing local-only operation)
2. The `/internal/cleanup/raw-uploads` endpoint can be called by Cloud Scheduler every 6 hours
3. All secrets are managed via GCP Secret Manager

---

## New Files

### `app/api/Dockerfile`

Multi-stage build mirroring `worker/Dockerfile.production`:

- **Stage 1 (base):** `python:3.11-slim-bookworm` — only `ca-certificates` as system dep (no OpenCV/Tesseract/ML)
- **Stage 2 (builder):** Installs `build-essential` (for native extensions in supabase/cryptography), creates `/opt/venv`, installs `app/api/requirements.txt`, strips `__pycache__`/`.pyc`
- **Stage 3 (runtime):** Copies venv + app source, sets `PYTHONPATH=/app` (required: imports use `from app.api...`), runs as non-root user `api`, verifies imports at build time (`fastapi`, `boto3`, `supabase`, `httpx`)

**Build context:** project root (`.`) — needed because `COPY app/api/ ./app/api/` and `PYTHONPATH=/app`.

**Start command:** `uvicorn app.api.main:app --host 0.0.0.0 --port 8080`

**Port:** 8080 (Cloud Run standard)

---

### `cloudbuild-api.yaml`

Four steps (separate from `cloudbuild.yaml` to allow independent triggering — worker builds take ~20 min, API builds ~2 min):

1. **Build** — `docker build --platform linux/amd64 -f app/api/Dockerfile -t asia-south1-docker.pkg.dev/rythmiq-one/rythmiq-images/api:latest .`
2. **Smoke test** — run the built image, call `/health`, assert HTTP 200 before pushing. Catches import errors and startup failures before they go live.
3. **Push** — push to Artifact Registry
4. **Deploy** — `gcloud run deploy rythmiq-api`:
   - `--region=asia-south1`
   - `--allow-unauthenticated` (app-layer auth is Supabase JWT; Cloud Run does not add auth)
   - `--cpu=1 --memory=1Gi --max-instances=10 --timeout=60`
   - `--cpu-boost`
   - `--project=rythmiq-one`
   - Plain env vars: `SERVICE_ENV=production`, `EXECUTION_BACKEND=cloudrun`, `CLOUD_RUN_WORKER_URL=https://rythmiq-worker-1048753379343.asia-south1.run.app`
   - Secret bindings (all mounted as env vars from Secret Manager, see below)

**Build machine:** `E2_HIGHCPU_8`
**Build timeout:** 600s

---

## Secrets

### Secrets to Create in Secret Manager

All 10 created manually by Abhinav using `read -s` pattern (same as session 12 Slack webhook). Secret values come from `.env`.

| Secret Manager name | Cloud Run env var |
|---|---|
| `rythmiq-api-supabase-url` | `SUPABASE_URL` |
| `rythmiq-api-supabase-anon-key` | `SUPABASE_ANON_KEY` |
| `rythmiq-api-supabase-service-role-key` | `SUPABASE_SERVICE_ROLE_KEY` |
| `rythmiq-api-supabase-jwt-secret` | `SUPABASE_JWT_SECRET` |
| `rythmiq-api-spaces-access-key` | `DO_SPACES_ACCESS_KEY` |
| `rythmiq-api-spaces-secret-key` | `DO_SPACES_SECRET_KEY` |
| `rythmiq-api-spaces-endpoint` | `DO_SPACES_ENDPOINT` |
| `rythmiq-api-spaces-region` | `DO_SPACES_REGION` |
| `rythmiq-api-spaces-bucket` | `DO_SPACES_BUCKET` |
| `rythmiq-api-webhook-secret` | `WEBHOOK_SECRET` |

### Already in Secret Manager

| Secret Manager name | Cloud Run env var |
|---|---|
| `rythmiq-api-internal-cleanup-secret` | `INTERNAL_CLEANUP_SECRET` |

### IAM

A dedicated service account `rythmiq-api@rythmiq-one.iam.gserviceaccount.com` is created for the API Cloud Run service (least privilege — separate blast radius from the worker SA). It needs `roles/secretmanager.secretAccessor` granted on all 11 secrets above.

---

## Cloud Scheduler

Created once after first successful deploy (not part of `cloudbuild-api.yaml`):

```
Name:     rythmiq-cleanup-raw-uploads
Schedule: 0 */6 * * *
Region:   asia-south1
Method:   POST
URL:      https://<api-cloud-run-url>/internal/cleanup/raw-uploads
Header:   X-Internal-Secret: <INTERNAL_CLEANUP_SECRET value>
```

Secret value fetched at job-creation time via:
```bash
gcloud secrets versions access latest --secret=rythmiq-api-internal-cleanup-secret
```

**Secret rotation note:** Cloud Scheduler hardcodes the `X-Internal-Secret` header value at job creation time. If `rythmiq-api-internal-cleanup-secret` is rotated in Secret Manager, the scheduler job must be manually updated:
```bash
gcloud scheduler jobs update http rythmiq-cleanup-raw-uploads \
  --update-headers "X-Internal-Secret=$(gcloud secrets versions access latest --secret=rythmiq-api-internal-cleanup-secret)"
```

---

## Deployment Steps (In Order)

1. Write `app/api/Dockerfile` and `cloudbuild-api.yaml`
2. Create `rythmiq-api` service account
3. Create 10 secrets in Secret Manager (Abhinav runs `read -s` → pipe to `gcloud secrets create`)
4. Grant `rythmiq-api` SA `secretAccessor` on all 11 secrets
5. Trigger first build: `gcloud builds submit --config cloudbuild-api.yaml .`
6. Verify API is live: `curl https://<url>/health`
7. Create Cloud Scheduler job
8. Verify scheduler: manually trigger job and check API logs

---

## Non-Goals

- No changes to `cloudbuild.yaml` (worker pipeline untouched)
- Cloud Scheduler job is created manually once, not managed by Cloud Build
