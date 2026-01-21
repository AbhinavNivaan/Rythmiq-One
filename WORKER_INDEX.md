# Worker Deployment Index - Phase-1.5 Track C

**Status**: ✅ Ready for Camber Cloud Deployment  
**Track**: Phase-1.5 Track C  
**Target**: Camber Cloud  
**Date**: January 7, 2025

---

## Overview

Worker deployment artifacts prepared for Camber Cloud integration. Worker runs as standalone job processor with:
- ✓ Shared codebase with API Gateway (no duplication)
- ✓ No API routes exposed (job processor only)
- ✓ No secrets logged (safe for log aggregation)
- ✓ Configuration via environment variables (provider-agnostic)

---

## Documentation Index

### Quick Start
**[WORKER_QUICKREF.md](WORKER_QUICKREF.md)** - 2-minute deployment summary
- Configure → Build → Deploy → Verify
- Copy/paste commands
- Quick environment reference

### Complete Deployment Guide
**[WORKER_DEPLOYMENT.md](WORKER_DEPLOYMENT.md)** - Full deployment guide
- Architecture overview
- Environment variables reference table
- Deployment checklist
- Troubleshooting guide
- Integration points

### Artifacts Documentation
**[WORKER_DEPLOYMENT_ARTIFACTS_SUMMARY.md](WORKER_DEPLOYMENT_ARTIFACTS_SUMMARY.md)** - Complete artifacts inventory
- Each artifact described with purpose
- Files created/modified
- Step-by-step deployment process
- Security checklist

---

## Artifacts Created

### 1. Worker Entrypoint
**File**: [worker/entrypoint.ts](worker/entrypoint.ts)  
**Entry command**: `npm run worker`  
**What it does**:
- Loads & validates environment configuration
- Initializes Camber execution backend
- Creates job executor instance
- Waits for jobs (signals graceful shutdown)

**Key properties**:
- No secrets logged (credentials never appear)
- Configuration-driven (no hardcoded values)
- Shared with API Gateway (same code)
- Structured logging for observability

### 2. Environment Configuration Template
**File**: [.env.worker.camber](.env.worker.camber)  
**Purpose**: Template for Camber deployment environment variables  
**Variables**:
- `DATABASE_URL` - PostgreSQL connection
- `ARTIFACT_STORE_TYPE` - S3 or local
- `ARTIFACT_STORE_BUCKET` - S3 bucket name
- `EXECUTION_BACKEND=camber` - Required for Camber
- `CAMBER_API_KEY` - Camber credentials
- `CAMBER_API_ENDPOINT` - Camber API URL
- `SERVICE_ENV` - Deployment environment

### 3. Docker Build Configuration
**File**: [Dockerfile.worker](Dockerfile.worker)  
**Status**: ✓ Already existed, verified correct  
**Entry**: `npm run worker`  
**Includes**:
- Multi-stage build (builder + runtime)
- Health check endpoint
- Dumb-init for signal handling
- Minimal Alpine base image

### 4. NPM Scripts
**File**: [package.json](package.json)  
**Changes**:
```json
"worker": "node dist/worker/entrypoint.js",
"worker:dev": "ts-node worker/entrypoint.ts"
```
**Usage**:
- Production: `npm run worker` (requires `npm run build` first)
- Development: `npm run worker:dev` (uses ts-node)

---

## Deployment Process

### Phase 1: Prepare
```bash
# Copy environment template
cp .env.worker.camber .env.worker

# Edit with actual values:
# - DATABASE_URL (PostgreSQL connection string)
# - ARTIFACT_STORE_BUCKET (your S3 bucket)
# - CAMBER_API_KEY (from Camber dashboard)
# - CAMBER_API_ENDPOINT (Camber API URL)
```

### Phase 2: Build
```bash
# Install dependencies
npm install

# Compile TypeScript
npm run build

# Build Docker image
docker build -f Dockerfile.worker -t rythmiq-worker:latest .
```

### Phase 3: Test (Local)
```bash
# Run locally to verify configuration
docker run \
  --env-file .env.worker \
  -e SERVICE_ENV=staging \
  -e LOG_LEVEL=debug \
  rythmiq-worker:latest

# Expected output in logs:
# [timestamp] [WORKER] Configuration loaded backend=camber env=staging artifactStoreType=s3
# [timestamp] [WORKER] Execution backend initialized backendType=CamberExecutionBackend
# [timestamp] [WORKER] Job executor ready
# [timestamp] [WORKER] Worker ready uptime=XXXms backend=camber
```

### Phase 4: Deploy to Camber Cloud
1. Push image to container registry (Docker Hub, ECR, etc.)
2. Create Camber Cloud deployment with:
   - Container image: `rythmiq-worker:latest`
   - Environment variables from `.env.worker`
   - Set `SERVICE_ENV=prod` for production
3. Deploy container
4. Monitor logs for "Worker ready" message

### Phase 5: Verify Production
```bash
# Check logs from Camber Cloud console
# Look for:
docker logs <container-id> | grep "[WORKER] Worker ready"

# If not present, check for errors:
docker logs <container-id> | grep "[WORKER] ERROR"
```

---

## Design Constraints

### ✓ No API Routes Exposed
- Worker is job processor only
- No HTTP server or Express app
- Can run without exposing ports
- Separate process from API Gateway

### ✓ No Secrets Logged
- API keys never appear in logs
- Database credentials never printed
- `CAMBER_API_KEY` filtered from output
- Stack traces suppressed when `SERVICE_ENV=prod`

### ✓ Shared Codebase with API
- Same `bootstrap/config.ts` configuration
- Same `engine/execution/` backend implementations
- Same `engine/storage/`, `engine/jobs/` etc.
- Only difference: Worker has no API routes

### ✓ No Provider-Specific Logic
- Camber selection through `EXECUTION_BACKEND` env var
- No hardcoded Camber URLs or keys
- Configuration centralized in `bootstrap/config.ts`
- Works with any execution backend (camber, do, heroku, local)

---

## Environment Variables Reference

### Required
| Variable | Format | Example |
|----------|--------|---------|
| `DATABASE_URL` | PostgreSQL URI | `postgresql://user:pass@host:5432/db` |
| `ARTIFACT_STORE_TYPE` | `s3` or `local` | `s3` |
| `ARTIFACT_STORE_BUCKET` | S3 bucket | `my-company-artifacts` |
| `EXECUTION_BACKEND` | Fixed value | `camber` |
| `CAMBER_API_KEY` | API key | `sk-xxxxxxxxxxxxxxxx` |
| `CAMBER_API_ENDPOINT` | URL | `https://api.camber.cloud` |

### Optional
| Variable | Default | Example |
|----------|---------|---------|
| `SERVICE_ENV` | `dev` | `prod` |
| `CAMBER_EXECUTION_REGION` | `us-east-1` | `us-east-1` |
| `CAMBER_QUEUE_NAME` | `default` | `default` |
| `CAMBER_EXECUTION_TIMEOUT_MS` | `300000` | `300000` |
| `NODE_ENV` | — | `production` |
| `LOG_LEVEL` | `info` | `debug` |

---

## File Structure

```
/Users/abhinav/Rythmiq One/
├── worker/
│   └── entrypoint.ts                        ← Worker startup logic
├── .env.worker.camber                       ← Environment template
├── WORKER_QUICKREF.md                       ← 2-minute guide (START HERE)
├── WORKER_DEPLOYMENT.md                     ← Full deployment guide
├── WORKER_DEPLOYMENT_ARTIFACTS_SUMMARY.md   ← Complete documentation
├── WORKER_INDEX.md                          ← This file
├── Dockerfile.worker                        ← Docker build spec
├── package.json                             ← npm scripts (updated)
├── bootstrap/
│   ├── config.ts                            ← Configuration provider
│   └── executionSelector.ts                 ← Backend selector
├── app/
│   └── executionBackendIntegration.ts       ← Backend initialization
├── engine/
│   ├── execution/
│   │   ├── executionBackend.ts              ← Backend interface
│   │   ├── camberBackend.ts                 ← Camber implementation
│   │   └── ...
│   ├── jobs/                                ← Job processing
│   ├── storage/                             ← Artifact storage
│   └── ...
└── api-gateway/                             ← API (not in worker)
    ├── server.ts                            ← API endpoint
    └── routes/                              ← API routes
```

---

## Verification Checklist

**Before deployment**:
- [ ] All required env vars present in `.env.worker`
- [ ] `EXECUTION_BACKEND=camber` set
- [ ] `DATABASE_URL` points to valid PostgreSQL
- [ ] `ARTIFACT_STORE_BUCKET` exists and is accessible
- [ ] `CAMBER_API_KEY` valid and has required permissions
- [ ] `npm run build` completes without errors
- [ ] `docker build -f Dockerfile.worker` succeeds

**After deployment**:
- [ ] Container starts without errors
- [ ] Logs contain "[WORKER] Worker ready"
- [ ] `SERVICE_ENV=prod` set (suppresses debug info)
- [ ] No secrets visible in logs
- [ ] Health check passing (if configured)
- [ ] Container gracefully exits on SIGTERM

---

## Next Steps

### Immediate
1. Update `.env.worker` with actual values
2. Build and test Docker image locally
3. Deploy to Camber Cloud
4. Verify logs show "Worker ready"

### Future Integration
- **Job Queue**: Integrate with persistent job queue (PostgreSQL)
  - Integration point: `worker/entrypoint.ts` line 40
  - Expected: Polling job queue instead of `waitForShutdown()`
  - Queue implementation: TBD (could be Bull, RabbitMQ, SQS, etc.)

### Monitoring & Operations
- Set up log aggregation (ensure `SERVICE_ENV=prod` to prevent secret leakage)
- Monitor startup time and job throughput
- Alert on worker crashes or configuration errors
- Regular rotation of `CAMBER_API_KEY`

---

## Security Notes

✓ **Secrets Management**:
- API keys not logged
- Database credentials not printed
- Configuration through environment variables only
- Secrets should be stored in secure vault (Camber Cloud secrets, AWS Secrets Manager, etc.)
- Never commit `.env.worker` to git

✓ **Process Isolation**:
- Worker runs separate from API Gateway
- No API routes exposed
- Graceful shutdown on SIGTERM

✓ **Database Access**:
- Worker connects to same PostgreSQL as API
- Recommend separate database role with minimal permissions
- Read job queue, write job status, read/write artifacts

✓ **Storage Access**:
- S3 bucket access via IAM role (preferred) or credentials
- Limit bucket permissions to worker role only
- Regular key rotation for any stored credentials

---

## Support

**For issues**:
1. Check [WORKER_DEPLOYMENT.md](WORKER_DEPLOYMENT.md) Troubleshooting section
2. Verify all environment variables in `.env.worker`
3. Check logs: `docker logs <container-id> | grep [WORKER]`
4. Ensure DATABASE_URL is accessible and credentials are correct

**For questions**:
- Architecture: See [WORKER_DEPLOYMENT_ARTIFACTS_SUMMARY.md](WORKER_DEPLOYMENT_ARTIFACTS_SUMMARY.md)
- Configuration: See [WORKER_DEPLOYMENT.md](WORKER_DEPLOYMENT.md) Environment Variables section
- Deployment: See [WORKER_QUICKREF.md](WORKER_QUICKREF.md)
