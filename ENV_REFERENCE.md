# Environment Variables Reference
# Phase-1.5 Track C Deployment

## Required Variables (All Deployments)

### DATABASE_URL
- **Description:** PostgreSQL connection string
- **Format:** `postgresql://user:password@host:port/database`
- **Example:** `postgresql://app:secret@db.example.com:5432/rythmiq`
- **Required by:** API Gateway, Worker
- **Never log:** ✓ (contains credentials)

### JWT_PUBLIC_KEY
- **Description:** Public key for JWT token validation
- **Format:** PEM-encoded public key
- **Example:**
  ```
  -----BEGIN PUBLIC KEY-----
  MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA...
  -----END PUBLIC KEY-----
  ```
- **Required by:** API Gateway only
- **Never log:** ✓ (security sensitive)

---

## Optional Variables (Common)

### NODE_ENV
- **Description:** Environment mode
- **Values:** `production` | `development` | `staging`
- **Default:** `production`
- **Recommended:** `production` for deployments

### PORT
- **Description:** HTTP server port
- **Default API Gateway:** `3000`
- **Default Worker:** `3001`
- **Example:** `PORT=8080`

### LOG_LEVEL
- **Description:** Logging verbosity
- **Values:** `debug` | `info` | `warn` | `error`
- **Default:** `info`

---

## Worker-Specific Variables

### EXECUTION_BACKEND
- **Description:** Job execution backend
- **Values:** 
  - `local` - Run jobs locally in container
  - `camber` - Delegate to Camber Cloud
  - `do` - Delegate to DigitalOcean
  - `heroku` - Delegate to Heroku
- **Required by:** Worker only
- **Default:** `local`

### ARTIFACT_STORE
- **Description:** Path to store job output artifacts
- **Format:** Absolute filesystem path
- **Example:** `/data/artifacts` or `/tmp/artifacts`
- **Required by:** Worker only
- **Note:** Directory must be writable by container process

---

## Backend-Specific Variables

### For EXECUTION_BACKEND=camber

```env
CAMBER_API_KEY=sk-xxxxxxxxxxxx
CAMBER_API_ENDPOINT=https://api.camber.cloud
CAMBER_EXECUTION_REGION=us-east-1
CAMBER_QUEUE_NAME=default
CAMBER_EXECUTION_TIMEOUT_MS=300000
```

**Obtain from:** Camber Cloud dashboard

### For EXECUTION_BACKEND=do

```env
DO_API_TOKEN=dop_v1_xxxxxxxxxxxx
DO_API_ENDPOINT=https://api.digitalocean.com/v2
DO_APP_NAME=rythmiq-execution
DO_EXECUTION_REGION=nyc
DO_FUNCTION_MEMORY_MB=256
DO_EXECUTION_TIMEOUT_MS=300000
```

**Obtain from:** DigitalOcean Account > API > Tokens

### For EXECUTION_BACKEND=heroku

```env
HEROKU_API_KEY=hrku_xxxxxxxxxxxx
HEROKU_API_ENDPOINT=https://api.heroku.com
HEROKU_APP_NAME=rythmiq-execution
HEROKU_DYNO_TYPE=worker
HEROKU_DYNO_SIZE=standard-1x
HEROKU_EXECUTION_TIMEOUT_MS=300000
```

**Obtain from:** Heroku Account Settings > API Keys

---

## Platform-Specific Setup

### Heroku

```bash
# Set all variables at once
heroku config:set \
  DATABASE_URL="postgresql://..." \
  JWT_PUBLIC_KEY="-----BEGIN PUBLIC KEY-----..." \
  EXECUTION_BACKEND="heroku" \
  HEROKU_API_KEY="hrku_..." \
  NODE_ENV="production" \
  -a <app-name>

# Verify
heroku config -a <app-name>

# View logs
heroku logs --tail -a <app-name>
```

### DigitalOcean App Platform

Via `app.yaml`:
```yaml
envs:
  - key: DATABASE_URL
    scope: RUN_AND_BUILD_TIME
    value: ${DATABASE_URL}
  - key: JWT_PUBLIC_KEY
    scope: RUN_AND_BUILD_TIME
    value: ${JWT_PUBLIC_KEY}
  - key: NODE_ENV
    value: production
```

Set values:
```bash
doctl apps update <app-id> --spec app.yaml
```

### DigitalOcean Droplet

Create `.env` file:
```bash
cat > /app/.env << 'EOF'
DATABASE_URL=postgresql://...
JWT_PUBLIC_KEY=-----BEGIN PUBLIC KEY-----...
EXECUTION_BACKEND=do
ARTIFACT_STORE=/data/artifacts
NODE_ENV=production
DO_API_TOKEN=dop_v1_...
EOF

# Load in container
docker run --env-file /app/.env ...
```

---

## Security Best Practices

### Never
- ❌ Commit `.env` files to Git
- ❌ Log DATABASE_URL, JWT_PUBLIC_KEY, or API keys
- ❌ Share credentials via Slack, email, or unencrypted channels
- ❌ Use development credentials in production

### Always
- ✓ Use secret management (Heroku Config Vars, 1Password, Vault)
- ✓ Rotate credentials quarterly
- ✓ Audit access to production variables
- ✓ Use IAM roles instead of long-lived tokens when possible
- ✓ Verify variables are set before starting app

### Validation Script

```typescript
// Add to src/server.ts or src/worker.ts
function validateEnvironment() {
  const required = [
    'DATABASE_URL',
    'JWT_PUBLIC_KEY',  // Required for API Gateway
    'ARTIFACT_STORE',  // Required for Worker
  ];

  const missing = required.filter(v => !process.env[v]);
  if (missing.length > 0) {
    console.error(`✗ Missing required environment variables: ${missing.join(', ')}`);
    process.exit(1);
  }

  console.log('✓ All required environment variables are set');
}

validateEnvironment();
```

---

## Troubleshooting

### Connection Refused
```
Error: connect ECONNREFUSED 127.0.0.1:5432
```
**Cause:** DATABASE_URL points to wrong host
**Fix:** Verify DATABASE_URL and network connectivity

### JWT Validation Fails
```
Error: unable to verify the signature
```
**Cause:** JWT_PUBLIC_KEY is wrong or corrupted
**Fix:** Verify key format and regenerate if needed

### Artifact Store Permission Denied
```
Error: EACCES: permission denied, open '/data/artifacts/file.json'
```
**Cause:** ARTIFACT_STORE directory not writable
**Fix:** 
```bash
docker run -v /data/artifacts:/data/artifacts \
  -u root --entrypoint /bin/sh image
# Inside: chown -R node /data/artifacts
```

### Backend Initialization Fails
```
Error: Invalid EXECUTION_BACKEND value
```
**Cause:** EXECUTION_BACKEND is not one of: local, camber, do, heroku
**Fix:** Set EXECUTION_BACKEND to valid value

---

## Examples

### Complete Heroku Setup
```bash
# 1. Create app
heroku create rythmiq-app

# 2. Provision PostgreSQL
heroku addons:create heroku-postgresql:standard-0 -a rythmiq-app

# 3. Get DATABASE_URL (automatic)
heroku config:get DATABASE_URL -a rythmiq-app

# 4. Generate JWT key pair (run locally)
node -e "const crypto = require('crypto'); const {publicKey} = crypto.generateKeyPairSync('rsa', {modulusLength: 2048, publicKeyEncoding: {type: 'spki', format: 'pem'}}); console.log(publicKey);"

# 5. Set all variables
heroku config:set \
  DATABASE_URL="postgres://..." \
  JWT_PUBLIC_KEY="-----BEGIN PUBLIC KEY-----..." \
  EXECUTION_BACKEND="heroku" \
  HEROKU_API_KEY="<get from account settings>" \
  -a rythmiq-app

# 6. Deploy
git push heroku main

# 7. Scale
heroku ps:scale web=1 worker=1 -a rythmiq-app
```

### Complete Droplet Setup
```bash
# 1. Create Droplet (Ubuntu 22.04, 1GB RAM)

# 2. SSH and install Docker
ssh root@DROPLET_IP
curl -fsSL https://get.docker.com | sh

# 3. Clone repo and build
git clone <repo> /app
cd /app
docker build -f Dockerfile.worker -t worker:latest .

# 4. Create .env
cat > /app/.env << 'EOF'
DATABASE_URL=postgresql://app:pass@db.example.com/rythmiq
ARTIFACT_STORE=/data/artifacts
EXECUTION_BACKEND=do
DO_API_TOKEN=dop_v1_...
NODE_ENV=production
EOF

# 5. Run worker
mkdir -p /data/artifacts
docker run -d \
  --name worker \
  --env-file /app/.env \
  -v /data/artifacts:/data/artifacts \
  --restart unless-stopped \
  worker:latest

# 6. Monitor
docker logs -f worker
```

---

## Reference Table

| Variable | Service | Required | Example |
|----------|---------|----------|---------|
| DATABASE_URL | Both | ✓ | postgresql://user:pass@host/db |
| JWT_PUBLIC_KEY | API | ✓ | -----BEGIN PUBLIC KEY----- |
| ARTIFACT_STORE | Worker | ✓ | /data/artifacts |
| EXECUTION_BACKEND | Worker | ✓ | local, camber, do, heroku |
| NODE_ENV | Both | | production |
| PORT | Both | | 3000, 3001 |
| LOG_LEVEL | Both | | info |
| CAMBER_API_KEY | Worker | Conditional | sk-... |
| DO_API_TOKEN | Worker | Conditional | dop_v1_... |
| HEROKU_API_KEY | Worker | Conditional | hrku_... |
