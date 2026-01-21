# API Gateway Deployment Artifacts
## Phase-1.5 Track C

### Overview
This document describes the deployment setup for the Rythmiq One API Gateway.

---

## Deployment Files

### 1. Server Entry Point
**File:** [`api-gateway/server.ts`](api-gateway/server.ts)

**Purpose:** Main server application with health checks and environment validation.

**Features:**
- Express app initialization
- Environment variable validation (fails fast on missing vars)
- Health check endpoints: `/health` and `/ready`
- Error handling middleware integration
- Startup logging (NO secret values logged)

**Startup Command:**
```bash
node dist/api-gateway/server.js
```

---

### 2. Docker Deployment
**File:** [`Dockerfile.api-gateway`](Dockerfile.api-gateway)

**Build:**
```bash
docker build -f Dockerfile.api-gateway -t rythmiq-api-gateway .
```

**Run:**
```bash
docker run -p 3000:3000 \
  -e DATABASE_URL="<postgres-url>" \
  -e JWT_PUBLIC_KEY="<public-key>" \
  -e SERVICE_ENV="production" \
  -e ARTIFACT_STORE_TYPE="s3" \
  -e EXECUTION_BACKEND="cpu" \
  rythmiq-api-gateway
```

**Health Check:**
- Endpoint: `GET /health`
- Interval: 30s
- Timeout: 10s
- Retries: 3

---

### 3. Heroku Deployment
**File:** [`Procfile`](Procfile)

**Setup:**
```bash
# Create Heroku app
heroku create rythmiq-api-gateway

# Set environment variables
heroku config:set DATABASE_URL="<postgres-url>"
heroku config:set JWT_PUBLIC_KEY="<public-key>"
heroku config:set SERVICE_ENV="production"
heroku config:set ARTIFACT_STORE_TYPE="s3"
heroku config:set EXECUTION_BACKEND="cpu"

# Deploy
git push heroku main

# Scale dynos
heroku ps:scale web=1

# Monitor
heroku logs --tail
```

**Health Check:**
```bash
curl https://rythmiq-api-gateway.herokuapp.com/health
curl https://rythmiq-api-gateway.herokuapp.com/ready
```

---

## Environment Variables

### Required Variables

| Variable | Description | Valid Values | Example |
|----------|-------------|--------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | postgres://... | `postgres://user:pass@host:5432/db` |
| `JWT_PUBLIC_KEY` | Public key for JWT validation | PEM format | `-----BEGIN PUBLIC KEY-----\n...` |
| `SERVICE_ENV` | Deployment environment | development, staging, production | `production` |
| `ARTIFACT_STORE_TYPE` | Blob storage backend | local, s3, gcs | `s3` |
| `EXECUTION_BACKEND` | Job execution backend | cpu, gpu, hybrid | `cpu` |

### Optional Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `PORT` | HTTP port | `3000` |
| `NODE_ENV` | Node environment | `production` |

---

## Health Check Endpoints

### `/health`
**Purpose:** Basic liveness check for load balancers.

**Response:**
```json
{
  "status": "ok"
}
```

**HTTP 200** always returned when server is running.

---

### `/ready`
**Purpose:** Readiness check with service metadata.

**Response:**
```json
{
  "status": "ready",
  "service": "api-gateway",
  "env": "production"
}
```

**HTTP 200** returned when server is ready to accept requests.

---

## Security Rules

### ✅ Implemented
- ✅ Environment validation on startup (fails fast)
- ✅ NO secret values logged
- ✅ NO env values in error responses
- ✅ NO framework errors exposed
- ✅ Canonical error schema enforced

### ❌ Never Do
- ❌ Commit secrets to repository
- ❌ Log DATABASE_URL or JWT_PUBLIC_KEY
- ❌ Expose env values in /ready or /health responses
- ❌ Add infra logic inside app code

---

## API Endpoints

### Upload
**POST** `/upload`
- Content-Type: `application/octet-stream`
- Max size: 100MB
- Returns: `{ blobId: string }`

### Job Status
**GET** `/jobs/:id`
- Returns: `{ status, progress, result? }`

### Job Results
**GET** `/results/:jobId`
- Returns: Binary output or JSON metadata

---

## Build Requirements

### TypeScript Compilation
```bash
# Install dependencies
npm install

# Build TypeScript
npx tsc

# Output directory
dist/api-gateway/server.js
```

### tsconfig.json
Ensure `outDir` is set to `dist`:
```json
{
  "compilerOptions": {
    "outDir": "./dist",
    "rootDir": "./",
    "target": "ES2020",
    "module": "commonjs"
  }
}
```

---

## Monitoring

### Logs
- Server startup confirmation
- Environment validation results
- Port binding confirmation
- Health check access logs

### What's NOT Logged
- Database credentials
- JWT keys
- Client request payloads
- Error stack traces (production)

---

## Deployment Checklist

- [ ] Environment variables configured
- [ ] TypeScript compiled to `dist/`
- [ ] Health check endpoints working
- [ ] Error responses follow canonical schema
- [ ] No secrets in logs or responses
- [ ] CORS configured (if needed)
- [ ] Rate limiting configured (if needed)
- [ ] Load balancer pointing to `/health`

---

## Next Steps

1. **Configure Production Database**
   - Set `DATABASE_URL` with production PostgreSQL instance
   - Run migrations if needed

2. **Configure Artifact Storage**
   - Set up S3 bucket or GCS bucket
   - Configure IAM permissions
   - Set `ARTIFACT_STORE_TYPE` accordingly

3. **Configure JWT Validation**
   - Generate or obtain `JWT_PUBLIC_KEY`
   - Configure key rotation if needed

4. **Deploy**
   - Choose platform (Docker, Heroku, DigitalOcean)
   - Set environment variables
   - Deploy and verify health checks

5. **Monitor**
   - Set up log aggregation
   - Configure alerts on health check failures
   - Monitor API latency and error rates

---

## Support

For deployment issues:
1. Check health endpoints: `/health` and `/ready`
2. Verify all required env vars are set
3. Check logs for startup errors
4. Verify TypeScript build succeeded
5. Ensure Node.js version 18+ is used

---

**Last Updated:** 2026-01-07  
**Version:** Phase-1.5 Track C  
**Status:** ✅ Ready for Deployment
