# Phase-1.5 Track C: Deployment Artifacts Summary

**Status:** Ready for Implementation  
**Date:** January 2026  
**Components:** API Gateway + Worker  

---

## Delivered Artifacts

### 1. Dockerfiles
- **Dockerfile.api-gateway** — HTTP API server (Heroku / DO App Platform)
- **Dockerfile.worker** — Job processor (Camber / DO Droplet)

Both use:
- Node.js 18-alpine (minimal, secure)
- Multi-stage build (builder + production)
- Health checks (curl or HTTP)
- Signal handling (dumb-init for worker)

### 2. Process Configuration
- **Procfile** — Heroku process definitions (web + worker)
- **deploy.sh** — Deployment automation script

### 3. Documentation
- **DEPLOYMENT.md** — Platform-specific deployment guides (Heroku, DO App, DO Droplet)
- **STARTUP_GUIDE.md** — Startup commands, entry points, example code
- **ENV_REFERENCE.md** — Environment variables, security best practices, troubleshooting
- **DEPLOYMENT_ARTIFACTS_SUMMARY.md** — This file

---

## Quick Start

### For Heroku (Both API + Worker)
```bash
heroku create <app-name>
heroku config:set DATABASE_URL=... JWT_PUBLIC_KEY=... EXECUTION_BACKEND=heroku HEROKU_API_KEY=...
git push heroku main
heroku ps:scale web=1 worker=1
heroku logs --tail
```

### For DigitalOcean App Platform (API Gateway)
```bash
# Edit app.yaml with your credentials
doctl apps create --spec app.yaml
doctl apps logs <app-id> --follow
```

### For DigitalOcean Droplet (Worker)
```bash
ssh root@DROPLET_IP
# Clone repo, build Docker image, set .env, run container
```

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│          Client (Mobile / Web)                   │
└──────────────┬──────────────────────────────────┘
               │
               ▼
┌──────────────────────────────┐
│    API Gateway (3000)        │
│  ✓ /upload                   │
│  ✓ /jobs/:id                 │
│  ✓ /jobs/:id/results         │
│  ✓ /health                   │
└──────┬───────────────────────┘
       │
       ├─ DATABASE_URL ────→ PostgreSQL
       ├─ JWT_PUBLIC_KEY ──→ Auth validation
       │
       ▼
┌──────────────────────────────┐
│    Job Queue (Database)      │
│  QUEUED → RUNNING → ...      │
└──────┬───────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│    Worker (3001)             │
│  ✓ Poll job queue            │
│  ✓ Execute (OCR + Schema)    │
│  ✓ Store artifacts           │
│  ✓ /health                   │
└──────┬───────────────────────┘
       │
       ├─ DATABASE_URL ────→ PostgreSQL
       ├─ ARTIFACT_STORE ──→ File system
       ├─ EXECUTION_BACKEND → local|camber|do|heroku
       │
       ▼
    Execution
  (Local CPU or
   External Cloud)
```

---

## Environment Variables (At a Glance)

| Variable | Component | Required | Example |
|----------|-----------|----------|---------|
| DATABASE_URL | Both | ✓ | postgresql://... |
| JWT_PUBLIC_KEY | API | ✓ | -----BEGIN PUBLIC KEY----- |
| EXECUTION_BACKEND | Worker | ✓ | local\|camber\|do\|heroku |
| ARTIFACT_STORE | Worker | ✓ | /data/artifacts |
| HEROKU_API_KEY | Worker (if heroku) | Cond. | hrku_... |
| CAMBER_API_KEY | Worker (if camber) | Cond. | sk-... |
| DO_API_TOKEN | Worker (if do) | Cond. | dop_v1_... |

**See ENV_REFERENCE.md for complete list.**

---

## Health Checks

Both services expose health endpoints:

```bash
# API Gateway
curl http://localhost:3000/health
# Response: {"status":"ok","timestamp":"..."}

# Worker
curl http://localhost:3001/health
# Response: {"status":"running","timestamp":"..."}
```

Health checks run every:
- **API Gateway:** 30 seconds
- **Worker:** 60 seconds

---

## Rules Enforced

✓ **No autoscaling** — Manual scaling only (heroku ps:scale, cloud dashboard)  
✓ **No infra logic in app** — All config via env vars, Dockerfile, or platform config  
✓ **No secret logging** — DATABASE_URL, JWT_PUBLIC_KEY, API keys never logged  

---

## Deployment Checklist

### Pre-Deployment
- [ ] Database provisioned and accessible
- [ ] JWT key pair generated and public key extracted
- [ ] EXECUTION_BACKEND selected (local, camber, do, heroku)
- [ ] Credentials obtained for selected backend
- [ ] `package.json` has `start` and `worker` scripts
- [ ] `npm run build` compiles without errors

### Deployment
- [ ] Dockerfile.api-gateway builds successfully
- [ ] Dockerfile.worker builds successfully
- [ ] Environment variables set in deployment platform
- [ ] Health endpoints respond 200 OK
- [ ] Test upload endpoint with sample file
- [ ] Test job status endpoint with job ID
- [ ] Verify worker processes jobs in queue
- [ ] Monitor logs for errors

### Post-Deployment
- [ ] API Gateway responding to /health
- [ ] Worker health check passing
- [ ] Database connection stable
- [ ] Artifact storage writable
- [ ] Error handling functional (invalid JWT, missing job, etc.)

---

## File Manifest

```
/Users/abhinav/Rythmiq One/
├── Dockerfile.api-gateway          ← API Gateway container
├── Dockerfile.worker               ← Worker container
├── Procfile                        ← Heroku process config
├── DEPLOYMENT.md                   ← Platform-specific guides
├── STARTUP_GUIDE.md                ← Startup commands & entry points
├── ENV_REFERENCE.md                ← Environment variables reference
├── DEPLOYMENT_ARTIFACTS_SUMMARY.md ← This file
├── deploy.sh                       ← Deployment automation script
├── api-gateway/
│   ├── routes/
│   │   ├── jobs.ts                 ← GET /jobs/:id
│   │   └── results.ts              ← GET /jobs/:id/results
│   ├── auth/
│   │   └── middleware.ts           ← JWT validation
│   ├── errors/
│   │   └── ...                     ← Error handling
│   └── ...
├── engine/
│   ├── cpu/
│   │   └── worker.ts               ← Job processor
│   ├── jobs/
│   │   ├── jobStore.ts             ← Database access
│   │   └── stateMachine.ts         ← Job states
│   ├── storage/
│   │   └── blobStore.ts            ← Artifact storage
│   └── ...
├── app/
│   └── executionBackendIntegration.ts ← Backend selector
├── bootstrap/
│   └── executionSelector.ts        ← Backend initialization
└── [Other directories...]
```

---

## Testing Locally

### Option 1: Docker Compose (Recommended)
```bash
# See deploy.sh: ./deploy.sh local
docker-compose up
```

### Option 2: Manual Docker
```bash
# Build images
docker build -f Dockerfile.api-gateway -t api:latest .
docker build -f Dockerfile.worker -t worker:latest .

# Start PostgreSQL
docker run -d --name postgres \
  -e POSTGRES_PASSWORD=dev \
  -p 5432:5432 \
  postgres:15-alpine

# Start API Gateway
docker run -d --name api \
  -e DATABASE_URL="postgres://postgres:dev@postgres:5432/postgres" \
  -e JWT_PUBLIC_KEY="test-key" \
  -p 3000:3000 \
  api:latest

# Start Worker
docker run -d --name worker \
  -e DATABASE_URL="postgres://postgres:dev@postgres:5432/postgres" \
  -e ARTIFACT_STORE="/tmp/artifacts" \
  -e EXECUTION_BACKEND=local \
  -p 3001:3001 \
  worker:latest

# Test
curl http://localhost:3000/health
curl http://localhost:3001/health
```

---

## Troubleshooting

### Container won't start
```bash
# Check logs
docker logs <container-name>

# Check environment variables
docker inspect <container-name> | grep -A 50 "Env"

# Check if port is in use
lsof -i :3000
```

### Database connection fails
```bash
# Verify DATABASE_URL format
echo $DATABASE_URL

# Test connection
psql "$DATABASE_URL"

# Check network (if containerized)
docker network ls
docker network inspect <network>
```

### Health check fails
```bash
# Manual health check
curl -v http://localhost:3000/health

# Check if server is listening
netstat -tlnp | grep 3000
```

### Artifact storage permission denied
```bash
# Fix permissions
docker exec worker chmod 777 /data/artifacts

# Or run container as root during setup
docker run --user root ...
chmod -R 777 /data/artifacts
```

---

## Next Steps

1. **Review** — Examine DEPLOYMENT.md and choose platform (Heroku / DO App / DO Droplet)
2. **Setup** — Follow platform-specific guide, set environment variables
3. **Test** — Run `npm run build`, `npm start`, `npm run worker` locally
4. **Deploy** — Push to platform using provided scripts
5. **Monitor** — Tail logs, test health endpoints, verify jobs process
6. **Scale** — If needed, increase worker count or dyno size

---

## Support

- **Heroku:** `heroku logs --tail` + `heroku ps`
- **DigitalOcean:** `doctl apps logs` or `docker logs`
- **Debugging:** Set `LOG_LEVEL=debug` in environment
- **Database:** Connect via psql or database GUI (DataGrip, pgAdmin)

---

## Files Created

This summary covers the following new files:

```
✓ Dockerfile.api-gateway (159 lines)
✓ Dockerfile.worker (172 lines)
✓ Procfile (16 lines)
✓ DEPLOYMENT.md (comprehensive guide)
✓ STARTUP_GUIDE.md (entry points + examples)
✓ ENV_REFERENCE.md (variables + best practices)
✓ deploy.sh (automation script)
✓ DEPLOYMENT_ARTIFACTS_SUMMARY.md (this file)
```

**Total:** 8 new files, ready for production deployment.

---

**Ready to deploy.** Choose your platform above and follow the corresponding guide in DEPLOYMENT.md.
