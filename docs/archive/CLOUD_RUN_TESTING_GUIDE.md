# End-to-End Testing Guide — Cloud Run + FastAPI + Mobile App

**Status**: All systems deployed and running  
**Date**: 14 February 2026

---

## 🎯 Current Status

| Component | Status | Details |
|-----------|--------|---------|
| **Cloud Run Worker** | ✅ Running | `https://rythmiq-worker-1048753379343.asia-south1.run.app` |
| **FastAPI Backend** | ✅ Running | `http://localhost:8000` (port 8000) |
| **Mobile App (Expo)** | ✅ Ready | Port 8082, waiting for connections |
| **Configuration** | ✅ Set | `EXECUTION_BACKEND=cloudrun` |

---

## 📱 Testing Scenarios

### Scenario 1: Health Check (Without Mobile App)

**Test if all services are responding:**

```bash
# FastAPI health
curl http://localhost:8000/health

# Cloud Run health
curl https://rythmiq-worker-1048753379343.asia-south1.run.app/health
```

**Expected responses:**
- FastAPI: `{"status": "ok", "dev_sandbox": {...}}`
- Cloud Run: `{"status": "ok", "service": "rythmiq-worker"}`

---

### Scenario 2: Submit Test Job via API (Direct)

**Test FastAPI → Cloud Run integration without mobile app:**

```bash
# Create a test job
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test-user-001",
    "artifact_url": "https://rythmiq-one-artifacts.sgp1.digitaloceanspaces.com/uploads/test/sample.jpg",
    "portal": "neet"
  }'
```

**What will happen:**
1. FastAPI receives the request
2. Creates a job in Supabase (status: pending)
3. HTTP POST to Cloud Run `/process`
4. Cloud Run executes the pipeline
5. Result stored in Supabase
6. Response returned to API caller

**Check logs:**
```bash
# FastAPI logs
tail -f /tmp/fastapi.log | grep -E "Cloud Run|job|submitted|completed"

# Cloud Run logs
gcloud run logs read rythmiq-worker --region asia-south1 --follow --limit 50
```

---

### Scenario 3: Submit Job via Mobile App

**For full end-to-end testing:**

1. **Open Expo Go on your device:**
   - Scan the QR code from `npm start` output
   - Or access web version: http://localhost:8082

2. **Navigate to job submission:**
   - Select a document to upload
   - Click "Submit" or similar button
   - Watch the loading indicator

3. **Monitor logs in parallel:**

   **Terminal 1 - FastAPI logs:**
   ```bash
   tail -f /tmp/fastapi.log
   ```

   **Terminal 2 - Cloud Run logs:**
   ```bash
   gcloud run logs read rythmiq-worker --region asia-south1 --follow
   ```

4. **Verify result:**
   - Check Supabase for updated job status
   - Result should appear on mobile app

---

## 📊 What Each Service Logs

### FastAPI Logs

**When a job is submitted, look for:**
```
{"timestamp": "...", "level": "INFO", "logger": "...", "message": "Cloud Run job submitted"}
{"timestamp": "...", "level": "INFO", "logger": "...", "message": "Cloud Run job completed successfully"}
```

**To monitor:**
```bash
tail -f /tmp/fastapi.log | grep -i "cloud run\|job"
```

### Cloud Run Logs

**When a job is processing, look for:**
```
[Processing request received]
[FETCH: Downloaded artifact]
[QUALITY: Assessment complete]
[ENHANCE: Image enhanced]
[SCHEMA: Result adapted]
[UPLOAD: Artifacts uploaded]
[Processing complete]
```

**To monitor:**
```bash
gcloud run logs read rythmiq-worker --region asia-south1 --follow
```

---

## 🔍 Troubleshooting Checklist

| Issue | Debug Steps |
|-------|------------|
| **Mobile app can't connect to FastAPI** | 1. Verify FastAPI running: `lsof -i :8000`<br>2. Check `.env` has correct API URL<br>3. Ensure both on same network |
| **FastAPI can't reach Cloud Run** | 1. Test endpoint: `curl https://...asia-south1.run.app/health`<br>2. Check `.env` has correct URL<br>3. Verify public access enabled |
| **Job gets stuck in "pending"** | 1. Check FastAPI logs<br>2. Check Cloud Run logs<br>3. Verify network connectivity |
| **Cloud Run returns error** | 1. Read error message in logs<br>2. Check environment variables are set<br>3. Verify artifact source is accessible |
| **Result doesn't appear in Supabase** | 1. Check if job completed in Cloud Run<br>2. Verify Supabase credentials in `.env`<br>3. Check FastAPI update logic |

---

## 📋 Key Endpoints

| Service | Endpoint | Purpose |
|---------|----------|---------|
| **FastAPI** | `http://localhost:8000/health` | Health check |
| **FastAPI** | `http://localhost:8000/jobs` | Submit job |
| **FastAPI** | `http://localhost:8000/jobs/{id}` | Get job status |
| **Cloud Run** | `https://...asia-south1.run.app/health` | Health check |
| **Cloud Run** | `https://...asia-south1.run.app/process` | Process job (internal) |

---

## 🚀 Expected Data Flow

```
1. Mobile App submits job
   ↓
2. FastAPI receives request
   ├─ Extract job data
   ├─ Create record in Supabase
   └─ Build payload for Cloud Run
   ↓
3. HTTP POST to Cloud Run /process
   ↓
4. Cloud Run executes pipeline
   ├─ FETCH image from artifact_url
   ├─ QUALITY assessment
   ├─ ENHANCE image
   ├─ SCHEMA adaptation
   ├─ UPLOAD result
   └─ Return JSON response
   ↓
5. FastAPI receives Cloud Run response
   ├─ Extract results
   └─ Update Supabase job record
   ↓
6. Mobile App receives response
   └─ Display results to user
```

---

## 💡 Tips for Testing

1. **Start with simple documents** — Use small images for faster processing
2. **Monitor both logs simultaneously** — Use multiple terminal windows
3. **Check Supabase in real-time** — Watch the jobs table update
4. **Test with different portals** — Try "neet", "jee", etc. to verify SCHEMA adaptation
5. **Measure latency** — First job: ~20-30s (cold start), subsequent: ~13-15s

---

## ✅ Success Indicators

You'll know it's working when:

- ✅ FastAPI health responds
- ✅ Cloud Run health responds  
- ✅ Mobile app can load UI
- ✅ Submitting a job creates record in Supabase
- ✅ Cloud Run processes the job (check logs)
- ✅ Result appears in Supabase job record
- ✅ Mobile app displays the result

---

## 📞 Quick Commands

**Monitor all systems:**
```bash
# Terminal 1: FastAPI logs
tail -f /tmp/fastapi.log

# Terminal 2: Cloud Run logs
gcloud run logs read rythmiq-worker --region asia-south1 --follow

# Terminal 3: Check services
watch -n 5 'echo "=== FastAPI ===" && curl -s http://localhost:8000/health | jq -c . && echo "=== Cloud Run ===" && curl -s https://rythmiq-worker-1048753379343.asia-south1.run.app/health'
```

---

## 📝 Notes

- Dev Sandbox Mode is enabled (auth bypassed)
- Cloud Run has 5-minute timeout per request
- Results are cached in memory on FastAPI
- All logs are JSON-formatted for easy parsing

Good luck with testing! 🚀
