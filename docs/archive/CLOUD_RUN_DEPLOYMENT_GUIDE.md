# Cloud Run Deployment Guide

> **Status**: Ready for implementation  
> **Date**: 14 February 2026  
> **Phase**: Phase 1 - Basic HTTP Worker

This guide walks through building and deploying the Rythmiq One worker to Google Cloud Run.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [GCP Setup (One-Time)](#gcp-setup-one-time)
3. [Build Docker Image Locally](#build-docker-image-locally)
4. [Deploy to Cloud Run](#deploy-to-cloud-run)
5. [Test the Deployment](#test-the-deployment)
6. [Update FastAPI Configuration](#update-fastapi-configuration)
7. [Troubleshooting](#troubleshooting)

---

## Prerequisites

**Local machine:**
- `gcloud` CLI installed: `brew install google-cloud-sdk`
- Docker installed and running
- Access to GCP account with billing enabled
- GCP project created (or will create during setup)

**GCP:**
- Cloud Run API enabled
- Artifact Registry API enabled
- Cloud Build API enabled

---

## GCP Setup (One-Time)

### 1. Create GCP Project

```bash
# If you don't have a project, create one
gcloud projects create rythmiq-one --name="Rythmiq One"

# Set it as the default
gcloud config set project rythmiq-one
```

### 2. Enable Required APIs

```bash
gcloud services enable \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    artifactregistry.googleapis.com
```

### 3. Create Artifact Registry Repository

```bash
# Create Docker repo in asia-south1 (Mumbai, India)
gcloud artifacts repositories create rythmiq-images \
    --repository-format=docker \
    --location=asia-south1 \
    --description="Rythmiq One Docker images"

# Verify
gcloud artifacts repositories list --location=asia-south1
```

### 4. Configure Docker Authentication

```bash
# Allow Docker to push to Google Artifact Registry
gcloud auth configure-docker asia-south1-docker.pkg.dev
```

---

## Build Docker Image Locally

### Option A: Build with Google Cloud Build (Recommended)

Cloud Build handles dependencies and automatically pushes to Artifact Registry.

```bash
cd "/Users/abhinav/Rythmiq One"

# Build and push (takes 5-10 minutes)
gcloud builds submit \
    --tag asia-south1-docker.pkg.dev/rythmiq-one/rythmiq-images/worker:latest \
    --timeout=1200 \
    -f Dockerfile.cloudrun \
    .

# Verify the image exists
gcloud artifacts docker images list asia-south1-docker.pkg.dev/rythmiq-one/rythmiq-images
```

### Option B: Build Locally and Push

If you prefer to build and push locally:

```bash
cd "/Users/abhinav/Rythmiq One"

# Build image locally
docker build \
    -f Dockerfile.cloudrun \
    -t asia-south1-docker.pkg.dev/rythmiq-one/rythmiq-images/worker:latest \
    .

# Push to Artifact Registry
docker push asia-south1-docker.pkg.dev/rythmiq-one/rythmiq-images/worker:latest
```

**Note**: On Apple Silicon Mac (M1/M2), you may need to specify the platform:

```bash
docker build \
    --platform linux/amd64 \
    -f Dockerfile.cloudrun \
    -t asia-south1-docker.pkg.dev/rythmiq-one/rythmiq-images/worker:latest \
    .
```

---

## Deploy to Cloud Run

### Deploy with Full Configuration

```bash
# Set your GCP project ID (change if different)
PROJECT_ID="rythmiq-one"

gcloud run deploy rythmiq-worker \
    --image asia-south1-docker.pkg.dev/${PROJECT_ID}/rythmiq-images/worker:latest \
    --region asia-south1 \
    --memory 2Gi \
    --cpu 2 \
    --timeout 120 \
    --concurrency 1 \
    --min-instances 0 \
    --max-instances 100 \
    --set-env-vars "DO_SPACES_ENDPOINT=https://rythmiq-one-artifacts.sgp1.digitaloceanspaces.com" \
    --set-env-vars "DO_SPACES_REGION=sgp1" \
    --set-env-vars "DO_SPACES_BUCKET=rythmiq-one-artifacts" \
    --set-env-vars "DO_SPACES_ACCESS_KEY=DO801FCJYBTBKXZUX8MT" \
    --set-env-vars "DO_SPACES_SECRET_KEY=qvtaYhOWs8FzCak56pUiEMDXKfN2ovqbnqAYw3rlMbE" \
    --no-allow-unauthenticated
```

**Key parameters:**
- `--region asia-south1` — Mumbai (low latency to India)
- `--memory 2Gi` — Sufficient for ML models
- `--cpu 2` — Good for image processing
- `--timeout 120` — 120 seconds (max is 3600s)
- `--concurrency 1` — One request per instance (CPU-bound)
- `--min-instances 0` — Scale to zero when idle (free)
- `--max-instances 100` — Allow scaling for traffic spikes
- `--no-allow-unauthenticated` — Require authentication

### Get the Service URL

```bash
gcloud run services describe rythmiq-worker \
    --region asia-south1 \
    --format="value(status.url)"

# Output: https://rythmiq-worker-xxxxx-el.a.run.app
```

Save this URL — you'll need it for the FastAPI configuration.

---

## Test the Deployment

### 1. Health Check

```bash
WORKER_URL=$(gcloud run services describe rythmiq-worker \
    --region asia-south1 \
    --format="value(status.url)")

curl -X GET "${WORKER_URL}/health"

# Expected response:
# {"status": "ok", "service": "rythmiq-worker"}
```

### 2. Test Job Processing (Optional)

Since Cloud Run requires authentication, you need to get an auth token:

```bash
# Get an auth token
TOKEN=$(gcloud auth print-identity-token)

# Create a test payload (adjust paths as needed)
PAYLOAD='{
  "job_id": "test-job-001",
  "artifact_source": {
    "type": "spaces",
    "endpoint": "https://rythmiq-one-artifacts.sgp1.digitaloceanspaces.com",
    "bucket": "rythmiq-one-artifacts",
    "region": "sgp1",
    "path": "uploads/test-user/test-image.jpg",
    "access_key": "DO801FCJYBTBKXZUX8MT",
    "secret_key": "qvtaYhOWs8FzCak56pUiEMDXKfN2ovqbnqAYw3rlMbE"
  },
  "output_artifact_destination": {
    "type": "spaces",
    "endpoint": "https://rythmiq-one-artifacts.sgp1.digitaloceanspaces.com",
    "bucket": "rythmiq-one-artifacts",
    "region": "sgp1",
    "path": "results/test-user/test-job-001.json",
    "access_key": "DO801FCJYBTBKXZUX8MT",
    "secret_key": "qvtaYhOWs8FzCak56pUiEMDXKfN2ovqbnqAYw3rlMbE"
  },
  "portal": "neet",
  "quality_threshold": 0.80,
  "enhancement_options": {
    "resize_max": 2048,
    "color_correction": true,
    "sharpen": true
  }
}'

# POST request to /process
curl -X POST \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json" \
    -d "${PAYLOAD}" \
    "${WORKER_URL}/process"
```

---

## Update FastAPI Configuration

### Update .env File

```bash
# Change execution backend from 'local' to 'cloudrun'
EXECUTION_BACKEND=cloudrun

# Add Cloud Run worker URL (from step above)
CLOUD_RUN_WORKER_URL=https://rythmiq-worker-xxxxx-el.a.run.app
```

### Verify Configuration

```bash
# Start FastAPI locally
cd "/Users/abhinav/Rythmiq One"
source .venv/bin/activate
uvicorn app.api.main:app --reload

# Check logs for Cloud Run initialization
# Should see: "[CLOUD RUN] Using Cloud Run worker backend"
```

### Test End-to-End

```bash
# Create a test job via FastAPI
curl -X POST http://localhost:8000/jobs \
    -H "Content-Type: application/json" \
    -d '{
      "user_id": "test-user-001",
      "artifact_url": "https://rythmiq-one-artifacts.sgp1.digitaloceanspaces.com/uploads/test-user/test-image.jpg",
      "portal": "neet"
    }'
```

---

## Troubleshooting

### Image Not Found

```
Error: Image asia-south1-docker.pkg.dev/rythmiq-one/rythmiq-images/worker:latest not found
```

**Solution:**
1. Verify the image was built: `gcloud artifacts docker images list asia-south1-docker.pkg.dev/rythmiq-one/rythmiq-images`
2. Re-run the build with `--timeout=1200` (sometimes builds time out)

### Cold Start Slow (5-15 seconds)

**Expected behavior** on first request each day. Models are pre-cached in the image, so subsequent requests are faster.

**To always have a warm container**, set `--min-instances=1`:

```bash
gcloud run deploy rythmiq-worker \
    --update-env-vars="" \  # Keep existing vars
    --min-instances 1       # Always keep 1 container warm
```

**Cost**: ~$5-8/month for always-on container.

### Cloud Run Returns 500 Error

**Check logs:**

```bash
gcloud run logs read rythmiq-worker --region asia-south1 --limit 50
```

**Common issues:**
- Missing environment variables (DO_SPACES_*)
- Worker code error in `/process` handler
- Image loading failure (pre-download models issue)

### Authentication Errors

If you see `403 Forbidden`:

```bash
# Grant yourself permission to invoke the service
gcloud run services add-iam-policy-binding rythmiq-worker \
    --region=asia-south1 \
    --member=user:your-email@gmail.com \
    --role=roles/run.invoker
```

Or allow unauthenticated access (not recommended for production):

```bash
gcloud run services update rythmiq-worker \
    --region asia-south1 \
    --allow-unauthenticated
```

---

## Monitoring & Logs

### View Recent Requests

```bash
gcloud run logs read rythmiq-worker --region asia-south1 --limit 50
```

### Stream Logs in Real Time

```bash
gcloud run logs read rythmiq-worker --region asia-south1 --follow
```

### Check Metrics

```bash
# View CPU, memory, request count, latency in Cloud Console
# https://console.cloud.google.com/run/detail/asia-south1/rythmiq-worker/metrics
```

---

## Next Steps

1. ✅ Deploy worker to Cloud Run
2. ✅ Update FastAPI to use Cloud Run backend
3. ✅ Test end-to-end with real image
4. ⏳ (Optional) Add monitoring and alerting
5. ⏳ (Optional) Set up CI/CD to auto-deploy on code changes

---

## References

- [Google Cloud Run Documentation](https://cloud.google.com/run/docs)
- [Dockerfile.cloudrun](../Dockerfile.cloudrun)
- [worker/server.py](../worker/server.py)
- [app/api/services/cloud_run_client.py](../app/api/services/cloud_run_client.py)
