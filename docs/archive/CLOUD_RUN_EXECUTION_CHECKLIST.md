# Cloud Run Migration — Execution Checklist

**Status**: Phase 1 Implementation Complete  
**Next**: Deploy to GCP  
**Estimated Time**: 45-60 minutes

---

## ✅ What's Been Completed

- [x] **worker/server.py** — HTTP FastAPI wrapper for worker pipeline
  - GET `/health` — Health check for Cloud Run liveness probe
  - POST `/process` — Main job processing endpoint
  - Error handling and JSON response formatting

- [x] **Dockerfile.cloudrun** — Production-ready Docker image
  - Python 3.11-slim base
  - All system dependencies (Tesseract, libGL, etc)
  - All Python packages pre-installed
  - Health check configured
  - PORT environment variable support

- [x] **app/api/services/cloud_run_client.py** — Cloud Run HTTP client
  - Implements same interface as CamberService
  - Synchronous operation (blocks until job completes)
  - Result caching for status queries
  - Proper error handling and logging

- [x] **Configuration updates**
  - `app/api/config.py` — Added Cloud Run settings
  - `app/api/services/camber.py` — Updated factory function to support Cloud Run
  - `.env` — Added Cloud Run configuration section

- [x] **Documentation**
  - `CLOUD_RUN_DEPLOYMENT_GUIDE.md` — Step-by-step deployment
  - `CLOUD_RUN_IMPLEMENTATION_SUMMARY.md` — Implementation details

---

## 🚀 Immediate Next Steps

### Phase 1: Build & Deploy (30 minutes)

**Step 1: Build Docker Image**

You have two options:

**Option A: Build with Google Cloud Build (Recommended)**
```bash
cd "/Users/abhinav/Rythmiq One"

gcloud builds submit \
    --tag asia-south1-docker.pkg.dev/rythmiq-one/rythmiq-images/worker:latest \
    --timeout=1200 \
    -f Dockerfile.cloudrun \
    .

# Watch the build progress in Cloud Console
# https://console.cloud.google.com/cloud-build/builds
```

**Option B: Build Locally** (only if you have enough disk space)
```bash
cd "/Users/abhinav/Rythmiq One"

docker build \
    --platform linux/amd64 \
    -f Dockerfile.cloudrun \
    -t asia-south1-docker.pkg.dev/rythmiq-one/rythmiq-images/worker:latest \
    .

docker push asia-south1-docker.pkg.dev/rythmiq-one/rythmiq-images/worker:latest
```

**Verify the image:**
```bash
gcloud artifacts docker images list \
    asia-south1-docker.pkg.dev/rythmiq-one/rythmiq-images
```

---

**Step 2: Deploy to Cloud Run**

```bash
gcloud run deploy rythmiq-worker \
    --image asia-south1-docker.pkg.dev/rythmiq-one/rythmiq-images/worker:latest \
    --region asia-south1 \
    --memory 2Gi \
    --cpu 2 \
    --timeout 120 \
    --concurrency 1 \
    --min-instances 0 \
    --max-instances 100 \
    --set-env-vars "DO_SPACES_ENDPOINT=https://rythmiq-one-artifacts.sgp1.digitaloceanspaces.com,DO_SPACES_REGION=sgp1,DO_SPACES_BUCKET=rythmiq-one-artifacts,DO_SPACES_ACCESS_KEY=DO801FCJYBTBKXZUX8MT,DO_SPACES_SECRET_KEY=qvtaYhOWs8FzCak56pUiEMDXKfN2ovqbnqAYw3rlMbE" \
    --no-allow-unauthenticated
```

**Get the service URL:**
```bash
gcloud run services describe rythmiq-worker \
    --region asia-south1 \
    --format="value(status.url)"

# Output: https://rythmiq-worker-xxxxx-el.a.run.app
```

Save this URL for the next step.

---

**Step 3: Update .env File**

```bash
# Edit .env and update these lines:
EXECUTION_BACKEND=cloudrun
CLOUD_RUN_WORKER_URL=https://rythmiq-worker-xxxxx-el.a.run.app
```

Or run in terminal:
```bash
cd "/Users/abhinav/Rythmiq One"

# Replace the URL with your actual URL from Step 2
sed -i '' 's|^EXECUTION_BACKEND=.*|EXECUTION_BACKEND=cloudrun|' .env
echo "CLOUD_RUN_WORKER_URL=https://YOUR_URL_HERE" >> .env
```

---

### Phase 2: Verify & Test (15 minutes)

**Step 4: Test Cloud Run Health Check**

```bash
WORKER_URL=$(gcloud run services describe rythmiq-worker \
    --region asia-south1 \
    --format="value(status.url)")

curl -X GET "${WORKER_URL}/health"

# Expected response:
# {"status": "ok", "service": "rythmiq-worker"}
```

---

**Step 5: Start FastAPI Locally**

```bash
cd "/Users/abhinav/Rythmiq One"
source .venv/bin/activate

uvicorn app.api.main:app --reload --port 8000
```

**Check logs:**
- Should see: `[CLOUD RUN] Using Cloud Run worker backend`
- Should see: `Uvicorn running on http://0.0.0.0:8000`

---

**Step 6: Test End-to-End (with Mobile App or curl)**

If running the Expo app:
1. Launch app-v2: `cd app-v2 && npm start`
2. Submit a test document through the mobile UI
3. Watch FastAPI logs for Cloud Run calls
4. Watch Cloud Run logs: `gcloud run logs read rythmiq-worker --region asia-south1 --follow`

Or test with curl (if you have an auth token):
```bash
TOKEN=$(gcloud auth print-identity-token)

curl -X POST \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json" \
    -d '{...job payload...}' \
    "${WORKER_URL}/process"
```

---

## 🎯 Success Criteria

After completing the checklist above, verify:

- [ ] **Docker image built successfully** — Visible in Artifact Registry
- [ ] **Cloud Run service deployed** — Can describe service and get URL
- [ ] **Health check responds** — `curl /health` returns `{"status": "ok"}`
- [ ] **FastAPI starts without errors** — No exceptions in startup logs
- [ ] **Correct backend initialized** — Logs show `[CLOUD RUN] Using Cloud Run worker backend`
- [ ] **Test job completes** — Either via mobile app or curl
- [ ] **Result appears in Supabase** — Job status updates to `completed`
- [ ] **Performance reasonable** — Cold start 20-30s, warm 14-16s

---

## 🔍 Monitoring

**View Recent Logs:**
```bash
gcloud run logs read rythmiq-worker --region asia-south1 --limit 50
```

**Stream Logs (Real-time):**
```bash
gcloud run logs read rythmiq-worker --region asia-south1 --follow
```

**View Metrics in Cloud Console:**
- CPU, Memory, Requests, Latency
- https://console.cloud.google.com/run/detail/asia-south1/rythmiq-worker/metrics

---

## 📚 Documentation

For detailed information, refer to:

1. **[CLOUD_RUN_DEPLOYMENT_GUIDE.md](CLOUD_RUN_DEPLOYMENT_GUIDE.md)**
   - GCP setup instructions
   - Build and deployment steps
   - Troubleshooting guide

2. **[CLOUD_RUN_IMPLEMENTATION_SUMMARY.md](CLOUD_RUN_IMPLEMENTATION_SUMMARY.md)**
   - Architecture overview
   - Configuration details
   - Performance expectations
   - Phase 2 roadmap

3. **[CLOUD_RUN_MIGRATION_PLAN.md](CLOUD_RUN_MIGRATION_PLAN.md)**
   - Original proposal document
   - Why Cloud Run was chosen
   - Detailed platform comparison

4. **Code files:**
   - [worker/server.py](worker/server.py) — HTTP wrapper
   - [Dockerfile.cloudrun](Dockerfile.cloudrun) — Docker image
   - [app/api/services/cloud_run_client.py](app/api/services/cloud_run_client.py) — Client

---

## ⚠️ Common Issues & Quick Fixes

| Issue | Fix |
|-------|-----|
| Build times out | Increase `--timeout=1200` when running `gcloud builds submit` |
| Image not found | Verify: `gcloud artifacts docker images list asia-south1-docker.pkg.dev/rythmiq-one/rythmiq-images` |
| `403 Forbidden` from Cloud Run | Get auth: `TOKEN=$(gcloud auth print-identity-token)` then use Bearer token in requests |
| Cold start slow (5-15s) | Normal. For warm container, add `--min-instances=1` (costs ~$5-8/mo) |
| `500 error` from Cloud Run | Check logs: `gcloud run logs read rythmiq-worker --region asia-south1 --limit 50` |

---

## 🎉 Done!

Once all steps above are complete, you'll have:

✅ Cloud Run worker deployed and running  
✅ FastAPI configured to use Cloud Run backend  
✅ End-to-end job processing working  
✅ Zero Camber dependency  
✅ ~100× cost reduction per job  
✅ Simpler architecture (no webhooks, no ngrok)

Ready for production! 🚀
