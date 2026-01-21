# Phase-1.5 Track C: Deployment Artifacts

Minimal deployment configuration for API Gateway and Worker.

---

## Overview

This deployment supports two independent components:

| Component | Role | Deployment | Endpoints |
|-----------|------|-----------|-----------|
| **API Gateway** | HTTP entry point | Heroku / DO App Platform | `/upload`, `/jobs/:id`, `/jobs/:id/results` |
| **Worker** | Job processor | Camber / DO Droplet | Internal only (event-driven) |

---

## API Gateway (Dockerfile.api-gateway)

### Heroku Deployment

```bash
# 1. Create Heroku app
heroku create <app-name>

# 2. Set required environment variables
heroku config:set \
  DATABASE_URL=postgresql://... \
  JWT_PUBLIC_KEY="-----BEGIN PUBLIC KEY-----..." \
  NODE_ENV=production

# 3. Deploy
git push heroku main

# 4. Monitor
heroku logs --tail
```

### DigitalOcean App Platform Deployment

```bash
# 1. Create app.yaml (see below)

# 2. Deploy
doctl apps create --spec app.yaml

# 3. Set environment variables via console or:
doctl apps update <app-id> --spec app.yaml

# 4. Monitor
doctl apps logs <app-id> --follow
```

**app.yaml example:**
```yaml
name: rythmiq-api-gateway
regions:
  - name: nyc
services:
  - name: api-gateway
    github:
      repo: <org>/rythmiq-one
      branch: main
      deploy_on_push: true
    build_command: npm ci && npm run build
    run_command: npm start
    envs:
      - key: DATABASE_URL
        scope: RUN_AND_BUILD_TIME
        value: ${DATABASE_URL}
      - key: JWT_PUBLIC_KEY
        scope: RUN_AND_BUILD_TIME
        value: ${JWT_PUBLIC_KEY}
      - key: NODE_ENV
        value: production
    http_port: 3000
    health_check:
      http_path: /health
      period_seconds: 30
```

### Environment Variables (API Gateway)

| Variable | Source | Required |
|----------|--------|----------|
| `DATABASE_URL` | Deployment config | ✓ |
| `JWT_PUBLIC_KEY` | Deployment config | ✓ |
| `PORT` | Default: 3000 | |
| `NODE_ENV` | Default: production | |

---

## Worker (Dockerfile.worker)

### Camber Deployment

```bash
# 1. Create Camber account and obtain API key

# 2. Build container
docker build -f Dockerfile.worker -t rythmiq-worker:latest .

# 3. Deploy (Camber-specific steps)
# Contact Camber support for deployment instructions

# 4. Set required environment variables:
#    - EXECUTION_BACKEND=camber
#    - CAMBER_API_KEY=<key>
#    - DATABASE_URL=<db-url>
#    - ARTIFACT_STORE=<store-path>
```

### DigitalOcean Droplet Deployment

```bash
# 1. Create Droplet (Ubuntu 22.04, 1GB RAM minimum)

# 2. SSH into Droplet
ssh root@<droplet-ip>

# 3. Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh && sh get-docker.sh

# 4. Clone repository
git clone <repo> && cd <repo>

# 5. Build container
docker build -f Dockerfile.worker -t rythmiq-worker:latest .

# 6. Create .env.worker
cat > .env.worker << 'EOF'
EXECUTION_BACKEND=do
DATABASE_URL=postgresql://...
ARTIFACT_STORE=/data/artifacts
NODE_ENV=production
EOF

# 7. Run container
docker run -d \
  --name worker \
  --env-file .env.worker \
  -v /data/artifacts:/data/artifacts \
  -v /var/run/docker.sock:/var/run/docker.sock \
  --restart unless-stopped \
  rythmiq-worker:latest

# 8. Monitor logs
docker logs -f worker
```

### Environment Variables (Worker)

| Variable | Source | Required |
|----------|--------|----------|
| `DATABASE_URL` | Deployment config | ✓ |
| `ARTIFACT_STORE` | Deployment config | ✓ |
| `EXECUTION_BACKEND` | local / camber / do | ✓ |
| `CAMBER_API_KEY` | If EXECUTION_BACKEND=camber | Conditional |
| `DO_API_TOKEN` | If EXECUTION_BACKEND=do | Conditional |
| `NODE_ENV` | Default: production | |

---

## Heroku Deployment (Both Components)

Use `Procfile` to deploy both API Gateway and Worker to Heroku.

```bash
# 1. Create Heroku app
heroku create <app-name>

# 2. Set required environment variables
heroku config:set \
  DATABASE_URL=postgresql://... \
  JWT_PUBLIC_KEY="-----BEGIN PUBLIC KEY-----..." \
  EXECUTION_BACKEND=heroku \
  HEROKU_API_KEY=<heroku-token> \
  NODE_ENV=production

# 3. Deploy (Procfile defines web and worker processes)
git push heroku main

# 4. Scale processes
heroku ps:scale web=1 worker=1

# 5. Monitor
heroku logs --tail
```

---

## Health Checks

### API Gateway
- **Endpoint:** `GET /health`
- **Port:** 3000
- **Expected:** 200 OK, JSON response
- **Interval:** 30 seconds

### Worker
- **Endpoint:** `GET /health` (internal)
- **Port:** 3001
- **Expected:** 200 OK
- **Interval:** 60 seconds

---

## Startup Commands

| Service | Command |
|---------|---------|
| API Gateway | `npm start` |
| Worker | `npm run worker` |

Both commands:
1. Load `.env` via dotenv
2. Connect to DATABASE_URL
3. Verify required environment variables
4. Start listening/processing

---

## Critical Rules

### No Autoscaling
- Manual scaling only via `heroku ps:scale` or cloud provider dashboard
- No auto-scaling policies configured

### No Infra Logic in App Code
- All deployment configuration in Dockerfile or env vars
- No hardcoded IPs, regions, or scaling logic
- No cloud provider SDKs for provisioning

### No Secret Logging
- DATABASE_URL never logged
- JWT_PUBLIC_KEY never logged
- CAMBER_API_KEY never logged
- Credentials only logged as `[REDACTED]` if necessary

---

## Monitoring & Troubleshooting

### API Gateway Issues
```bash
# Check if DATABASE_URL is valid
heroku config

# Check recent logs
heroku logs --tail

# Test health endpoint
curl https://<app>.herokuapp.com/health
```

### Worker Issues
```bash
# Check execution backend config
docker logs worker | grep EXECUTION_BACKEND

# Verify artifact storage is writable
docker exec worker touch /data/artifacts/test.txt && rm /data/artifacts/test.txt

# Check for timeout errors
docker logs worker | grep timeout
```

---

## Rollback Plan

### Heroku
```bash
# Rollback to previous release
heroku releases
heroku rollback v<previous-version>
```

### DigitalOcean
```bash
# Stop running container
docker stop worker

# Start previous container
docker run -d --name worker-prev <previous-image-hash> ...
```

---

## Package.json Scripts

Ensure `package.json` includes:
```json
{
  "scripts": {
    "start": "node dist/server.js",
    "worker": "node dist/worker.js",
    "build": "tsc"
  }
}
```

---

## Next Steps

1. **Code Review:** Verify Dockerfiles match your startup scripts
2. **Local Testing:** `docker build -f Dockerfile.api-gateway .` and test locally
3. **Credentials:** Prepare DATABASE_URL, JWT_PUBLIC_KEY, and backend-specific keys
4. **Deployment:** Follow platform-specific steps above (Heroku / DO App Platform / Droplet)
5. **Verification:** Test health endpoints and run sample jobs
