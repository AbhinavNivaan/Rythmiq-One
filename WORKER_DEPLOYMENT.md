# Worker Deployment - Phase-1.5 Track C (Camber Cloud)

## Quick Start

### 1. Configuration

Copy environment template and configure for your Camber Cloud setup:

```bash
cp .env.worker.camber .env.worker
# Edit .env.worker with your values:
#   DATABASE_URL (PostgreSQL connection)
#   ARTIFACT_STORE_BUCKET (S3 bucket name)
#   CAMBER_API_KEY (from Camber dashboard)
```

### 2. Build

```bash
npm install
npm run build
docker build -f Dockerfile.worker -t rythmiq-worker:latest .
```

### 3. Run

```bash
# Local/staging testing
docker run \
  --env-file .env.worker \
  -e SERVICE_ENV=staging \
  rythmiq-worker:latest

# Production on Camber Cloud
# (Follow Camber platform instructions for deployment)
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | ✓ | PostgreSQL connection string |
| `ARTIFACT_STORE_TYPE` | ✓ | `s3` or `local` |
| `ARTIFACT_STORE_BUCKET` | ✓ (if S3) | S3 bucket for artifacts |
| `ARTIFACT_STORE_PATH` | ✓ (if local) | Local filesystem path (default: `./artifacts`) |
| `EXECUTION_BACKEND` | ✓ | Must be: `camber` |
| `CAMBER_API_KEY` | ✓ | Camber Cloud API key |
| `CAMBER_API_ENDPOINT` | ✓ | Camber API URL (default: `https://api.camber.cloud`) |
| `CAMBER_EXECUTION_REGION` | — | Camber region (default: `us-east-1`) |
| `SERVICE_ENV` | — | `dev`, `staging`, or `prod` (default: `dev`) |
| `NODE_ENV` | — | Set to `production` for docker |

## Architecture

```
Worker (entrypoint.ts)
  ├── Config validation (bootstrap/config.ts)
  ├── Execution Backend selection (bootstrap/executionSelector.ts)
  │   └── Camber Backend (engine/execution/camberBackend.ts)
  └── Job Executor (app/executionBackendIntegration.ts)
```

### Key Design Constraints

- **No API routes**: Worker is job processor only, no HTTP server
- **No secrets in logs**: `CAMBER_API_KEY`, `DATABASE_URL` credentials never logged
- **Shared codebase**: Uses same bootstrap & configuration as API Gateway
- **No provider-specific code**: Camber logic isolated in `engine/execution/`

## Entrypoint

**File**: `worker/entrypoint.ts`

**Entry point**: `npm run worker` → `node dist/worker/entrypoint.js`

**Startup sequence**:
1. Load configuration from environment variables
2. Validate required variables (throws on missing)
3. Initialize Camber execution backend
4. Create job executor instance
5. Wait for jobs (signals graceful shutdown on SIGTERM/SIGINT)

**Logs** (no sensitive data):
```
[2025-01-07T10:30:45.123Z] [WORKER] Configuration loaded backend=camber env=prod artifactStoreType=s3
[2025-01-07T10:30:45.234Z] [WORKER] Execution backend initialized backendType=CamberExecutionBackend
[2025-01-07T10:30:45.245Z] [WORKER] Job executor ready
[2025-01-07T10:30:45.246Z] [WORKER] Worker ready uptime=123ms backend=camber
```

## Deployment Checklist

- [ ] Database credentials configured in `DATABASE_URL`
- [ ] S3 bucket created and accessible via `ARTIFACT_STORE_BUCKET`
- [ ] Camber API key configured in `CAMBER_API_KEY`
- [ ] SERVICE_ENV set to `prod` for production
- [ ] Docker image built: `npm run build && docker build -f Dockerfile.worker`
- [ ] Health check passing (worker logs show "Worker ready")
- [ ] No secrets visible in logs: `docker logs <container> | grep -i key`

## Troubleshooting

### Configuration errors
```bash
# Check which variables are missing
docker run --env-file .env.worker rythmiq-worker:latest 2>&1 | grep "Missing required"
```

### Backend initialization fails
```bash
# Check Camber credentials
# Verify CAMBER_API_ENDPOINT is reachable
# Verify CAMBER_API_KEY has required permissions
docker logs <container> | grep "Execution backend"
```

### Database connection
```bash
# Test PostgreSQL connection
docker run --env-file .env.worker -it rythmiq-worker:latest node -e \
  "require('dotenv').config(); console.log(process.env.DATABASE_URL)"
```

## Files

- `worker/entrypoint.ts` - Worker startup logic
- `.env.worker.camber` - Environment template
- `Dockerfile.worker` - Docker build spec
- `package.json` - Added `npm run worker` script

## Integration Points

### API Gateway
- Shares: `bootstrap/config.ts`, `engine/` codebase
- Decoupled: API routes not included in worker build

### Job Queue (Future)
- Worker ready for integration with job queue service
- Expected integration point: Between "Job executor ready" and "Worker ready" logs
- Queue polling would replace the `waitForShutdown()` placeholder

### Camber Cloud
- Delegated job execution to Camber backend
- Worker polls Camber for job results (or receives webhooks - TBD)
