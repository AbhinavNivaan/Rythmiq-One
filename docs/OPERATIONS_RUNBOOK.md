# Rythmiq One - Operations Runbook

This document provides operational procedures for managing the Rythmiq One production environment.

---

## 📋 Table of Contents

1. [Service Overview](#service-overview)
2. [Health Checks](#health-checks)
3. [Deployment Procedures](#deployment-procedures)
4. [Scaling Guidelines](#scaling-guidelines)
5. [Incident Response](#incident-response)
6. [Monitoring & Alerts](#monitoring--alerts)
7. [Database Operations](#database-operations)
8. [Storage Operations](#storage-operations)
9. [Common Issues & Fixes](#common-issues--fixes)

---

## 🏗️ Service Overview

### Production Components

| Service | Platform | URL | Purpose |
|---------|----------|-----|---------|
| API Gateway | Railway/Render | api.rythmiq.one | REST API |
| Worker | Railway/Render | N/A (internal) | Image processing |
| Database | Supabase | [project].supabase.co | PostgreSQL + Auth |
| Storage | DigitalOcean Spaces | nyc3.digitaloceanspaces.com | File storage |
| CDN | Spaces CDN | cdn.rythmiq.one | File delivery |

### Service Dependencies

```
Mobile App
    └── API Gateway
            ├── Supabase Auth (authentication)
            ├── Supabase DB (job metadata)
            └── Worker (async processing)
                    ├── DO Spaces (file input)
                    └── DO Spaces (file output)
```

---

## 🏥 Health Checks

### API Gateway Health

```bash
# Check API health
curl https://api.rythmiq.one/health

# Expected response:
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": "2025-01-26T10:00:00Z"
}
```

### Database Health

```bash
# Check Supabase connection
curl https://api.rythmiq.one/health/db

# Or via Supabase dashboard
# Project → Database → Connection Pooler status
```

### Worker Health

```bash
# Check worker queue depth
curl https://api.rythmiq.one/health/worker

# Expected response:
{
  "queue_depth": 5,
  "active_jobs": 2,
  "workers_available": 4
}
```

### Storage Health

```bash
# Check Spaces connectivity
curl -I https://rythmiq-files.nyc3.digitaloceanspaces.com/

# Expected: HTTP 403 (forbidden but reachable)
```

---

## 🚀 Deployment Procedures

### API Gateway Deployment

```bash
# 1. Run tests locally
pytest tests/api/ -v

# 2. Build Docker image
docker build -t rythmiq-api:v1.0.x -f Dockerfile .

# 3. Push to registry
docker push registry.digitalocean.com/rythmiq/api:v1.0.x

# 4. Deploy (Railway)
railway up --environment production

# Or (Render)
# Push to main branch triggers auto-deploy

# 5. Verify deployment
curl https://api.rythmiq.one/health
```

### Worker Deployment

```bash
# 1. Run worker tests
pytest tests/worker/ -v

# 2. Build worker image
docker build -t rythmiq-worker:v1.0.x -f Dockerfile.worker .

# 3. Push to registry
docker push registry.digitalocean.com/rythmiq/worker:v1.0.x

# 4. Deploy
railway up --service worker --environment production
```

### Mobile App Deployment

```bash
cd app-v2

# 1. Update version in app.json
# "version": "1.0.x"

# 2. Build for TestFlight
eas build --platform ios --profile preview

# 3. Submit to TestFlight
eas submit --platform ios --latest

# 4. For production release
eas build --platform ios --profile production
eas submit --platform ios --latest
```

### Rollback Procedure

```bash
# API Gateway
railway rollback --environment production

# Or deploy previous version explicitly
docker push registry.digitalocean.com/rythmiq/api:v1.0.previous
railway deploy --image registry.digitalocean.com/rythmiq/api:v1.0.previous
```

---

## 📈 Scaling Guidelines

### API Gateway Scaling

| Metric | Threshold | Action |
|--------|-----------|--------|
| CPU > 70% | 5 min | Add instance |
| Memory > 80% | 5 min | Add instance |
| Response time > 2s | 10 min | Add instance |
| Error rate > 1% | 5 min | Investigate |

```bash
# Railway
railway scale --replicas 3 --service api

# Render
# Dashboard → Service → Scaling → Set instance count
```

### Worker Scaling

| Metric | Threshold | Action |
|--------|-----------|--------|
| Queue depth > 50 | 10 min | Add worker |
| Job wait time > 30s | 10 min | Add worker |
| CPU > 80% | 5 min | Add worker |

```bash
# Scale workers
railway scale --replicas 4 --service worker
```

### Database Scaling

- Supabase handles connection pooling automatically
- Monitor via Supabase Dashboard → Database → Usage

**If hitting limits:**
1. Enable connection pooler (PgBouncer mode)
2. Upgrade Supabase plan

---

## 🚨 Incident Response

### Severity Levels

| Level | Description | Response Time | Example |
|-------|-------------|---------------|---------|
| SEV1 | Total outage | 15 min | API down, auth broken |
| SEV2 | Major degradation | 30 min | Worker queue stalled |
| SEV3 | Minor issue | 4 hours | Slow response times |
| SEV4 | Low impact | 24 hours | UI bug, edge case |

### SEV1 Response Checklist

1. **Acknowledge** - Post in #incidents channel
2. **Assess** - Check all health endpoints
3. **Isolate** - Identify failing component
4. **Mitigate** - Apply quick fix or rollback
5. **Communicate** - Update status page
6. **Resolve** - Full fix
7. **Post-mortem** - Document within 48 hours

### Communication Templates

**Initial Alert:**
```
🔴 [SEV1] Rythmiq One - API Gateway Down
Time: 2025-01-26 10:00 UTC
Impact: All users affected
Status: Investigating
Next Update: 10:15 UTC
```

**Resolution:**
```
✅ [RESOLVED] Rythmiq One - API Gateway Down
Duration: 10:00-10:25 UTC (25 min)
Root Cause: Database connection pool exhausted
Fix: Increased pool size, added monitoring
Post-mortem: [link]
```

---

## 📊 Monitoring & Alerts

### Key Metrics

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| API Availability | 99.9% | < 99% (5 min) |
| API Response Time (p95) | < 500ms | > 2000ms |
| Error Rate | < 0.1% | > 1% |
| Worker Queue Depth | < 20 | > 100 |
| Job Processing Time | < 30s | > 120s |

### Monitoring Stack

- **Logs**: Railway/Render logs, Supabase logs
- **Metrics**: Built-in platform metrics
- **Uptime**: UptimeRobot / Better Uptime
- **APM**: Sentry (error tracking)

### Alert Configuration

```yaml
# Example UptimeRobot monitors
monitors:
  - name: API Health
    url: https://api.rythmiq.one/health
    type: HTTP
    interval: 60s
    alert_contacts: [oncall-pager, slack-incidents]
    
  - name: API Latency
    url: https://api.rythmiq.one/health
    type: HTTP
    interval: 300s
    response_time_threshold: 2000ms
```

---

## 🗄️ Database Operations

### Backup Schedule

- **Automatic**: Supabase daily backups (7-day retention)
- **Manual**: Before major migrations

```bash
# Manual backup
pg_dump $DATABASE_URL > backup_$(date +%Y%m%d).sql
```

### Common Queries

```sql
-- Active jobs by status
SELECT status, COUNT(*) 
FROM jobs 
GROUP BY status;

-- Jobs older than 24h in processing
SELECT id, user_id, created_at 
FROM jobs 
WHERE status = 'processing' 
AND created_at < NOW() - INTERVAL '24 hours';

-- User with most jobs
SELECT user_id, COUNT(*) as job_count 
FROM jobs 
GROUP BY user_id 
ORDER BY job_count DESC 
LIMIT 10;

-- Failed jobs in last hour
SELECT * FROM jobs 
WHERE status = 'failed' 
AND updated_at > NOW() - INTERVAL '1 hour';
```

### Migration Procedure

```bash
# 1. Test migration locally
psql $LOCAL_DB < migrations/001_add_column.sql

# 2. Backup production
pg_dump $DATABASE_URL > pre_migration_backup.sql

# 3. Apply to production (off-peak hours)
psql $DATABASE_URL < migrations/001_add_column.sql

# 4. Verify
psql $DATABASE_URL -c "SELECT * FROM jobs LIMIT 1;"
```

---

## 📦 Storage Operations

### DigitalOcean Spaces Structure

```
rythmiq-files/
├── raw/                    # Original uploads
│   └── {user_id}/
│       └── {doc_id}/
│           └── original.jpg
├── master/                 # Processed master docs
│   └── {user_id}/
│       └── {doc_id}/
│           └── master.png
└── output/                 # Adapted outputs
    └── {user_id}/
        └── {job_id}/
            └── {portal}_photo.jpg
```

### Cleanup Procedures

```bash
# List old raw files (> 30 days)
s3cmd ls --recursive s3://rythmiq-files/raw/ | \
  awk '$1 < "'$(date -d "30 days ago" +%Y-%m-%d)'" {print $4}'

# Delete old temporary files
s3cmd rm --recursive s3://rythmiq-files/temp/

# Check storage usage
s3cmd du -H s3://rythmiq-files/
```

### Storage Quotas

| Type | Retention | Quota/User |
|------|-----------|------------|
| Raw | 30 days | 500 MB |
| Master | Forever | 2 GB |
| Output | 7 days | 200 MB |

---

## 🔧 Common Issues & Fixes

### Issue: Jobs Stuck in "processing"

**Symptoms:** Jobs stay in processing state > 10 minutes

**Diagnosis:**
```sql
SELECT * FROM jobs 
WHERE status = 'processing' 
AND updated_at < NOW() - INTERVAL '10 minutes';
```

**Fix:**
```bash
# Check worker logs
railway logs --service worker

# Restart worker
railway restart --service worker

# If needed, manually fail stuck jobs
psql $DATABASE_URL -c "
  UPDATE jobs 
  SET status = 'failed', 
      error = 'Timed out during processing' 
  WHERE status = 'processing' 
  AND updated_at < NOW() - INTERVAL '30 minutes';
"
```

### Issue: High Latency on API

**Symptoms:** Response times > 2 seconds

**Diagnosis:**
1. Check database connection pool usage
2. Check CPU/memory of API instances
3. Check for slow queries

**Fix:**
```bash
# Scale up API instances
railway scale --replicas 3 --service api

# Check for slow queries
psql $DATABASE_URL -c "
  SELECT * FROM pg_stat_statements 
  ORDER BY mean_time DESC 
  LIMIT 10;
"
```

### Issue: Storage Upload Failures

**Symptoms:** "Upload failed" errors

**Diagnosis:**
```bash
# Check Spaces status
curl -I https://rythmiq-files.nyc3.digitaloceanspaces.com/

# Check credentials
s3cmd info s3://rythmiq-files/
```

**Fix:**
1. Verify `DO_SPACES_KEY` and `DO_SPACES_SECRET` are set
2. Check bucket permissions
3. Verify CORS configuration

### Issue: Authentication Failures

**Symptoms:** Users can't log in

**Diagnosis:**
1. Check Supabase Auth status
2. Verify API can reach Supabase

```bash
curl https://[project].supabase.co/auth/v1/health
```

**Fix:**
1. Check Supabase dashboard for issues
2. Verify `SUPABASE_URL` and `SUPABASE_KEY` env vars
3. Check rate limits on auth endpoints

---

## 📞 Contacts

| Role | Name | Contact |
|------|------|---------|
| On-Call | Rotating | PagerDuty |
| Lead Engineer | - | @lead in Slack |
| DevOps | - | @devops in Slack |
| Supabase Support | - | support@supabase.io |
| DO Support | - | support.digitalocean.com |

---

## 📚 Related Documents

- [DEPLOYMENT.md](./DEPLOYMENT.md) - Detailed deployment guide
- [ENV_REFERENCE.md](./ENV_REFERENCE.md) - Environment variables
- [API_GATEWAY_QUICKSTART.md](./API_GATEWAY_QUICKSTART.md) - API documentation
- [WORKER_DEPLOYMENT.md](./WORKER_DEPLOYMENT.md) - Worker specifics

---

*Last updated: 2025-01-26*
