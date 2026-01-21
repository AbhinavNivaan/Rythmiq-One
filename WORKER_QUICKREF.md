# Worker Deployment Quick Reference

## Files Created

| File | Purpose |
|------|---------|
| `worker/entrypoint.ts` | Worker startup logic (npm run worker) |
| `.env.worker.camber` | Environment template for Camber |
| `WORKER_DEPLOYMENT.md` | Deployment guide & troubleshooting |
| `WORKER_DEPLOYMENT_ARTIFACTS_SUMMARY.md` | Complete artifacts documentation |

## Files Modified

| File | Changes |
|------|---------|
| `package.json` | Added `npm run worker` & `npm run worker:dev` scripts |

## Deploy

```bash
# 1. Configure
cp .env.worker.camber .env.worker
# Edit with your values: DATABASE_URL, CAMBER_API_KEY, etc.

# 2. Build
npm install
npm run build
docker build -f Dockerfile.worker -t rythmiq-worker:latest .

# 3. Run (local test)
docker run --env-file .env.worker -e SERVICE_ENV=staging rythmiq-worker:latest

# 4. Deploy to Camber Cloud
# Follow Camber platform instructions to push image & configure env vars
```

## Verification

```bash
# Check logs for startup confirmation
docker logs <container-id> | grep "[WORKER]"

# Expected output pattern:
# [timestamp] [WORKER] Configuration loaded backend=camber env=prod artifactStoreType=s3
# [timestamp] [WORKER] Execution backend initialized backendType=CamberExecutionBackend
# [timestamp] [WORKER] Job executor ready
# [timestamp] [WORKER] Worker ready uptime=XXXms backend=camber
```

## Required Environment Variables

```
DATABASE_URL=postgresql://user:pass@host:port/db
ARTIFACT_STORE_TYPE=s3
ARTIFACT_STORE_BUCKET=my-bucket
EXECUTION_BACKEND=camber
CAMBER_API_KEY=sk-xxxxx
CAMBER_API_ENDPOINT=https://api.camber.cloud
SERVICE_ENV=prod
```

## Design Guarantees

✓ **No API routes** - Worker is job processor only  
✓ **No secrets in logs** - API keys & credentials never printed  
✓ **Shared codebase** - Uses same bootstrap/config as API Gateway  
✓ **No provider-specific code** - Camber selection via env var only  

## Next: Job Queue Integration

Worker is ready for job queue polling. Integration point:
- File: `worker/entrypoint.ts`
- Location: After `logStartup('Job executor ready')`
- Expected: Job queue service fetches from PostgreSQL
