# Phase-1.5 Track C: Deployment Artifacts Index

## 🚀 Start Here

Read in this order:

1. **[DEPLOYMENT_ARTIFACTS_SUMMARY.md](DEPLOYMENT_ARTIFACTS_SUMMARY.md)** — Overview of what was built
2. **[DEPLOYMENT.md](DEPLOYMENT.md)** — Choose your platform and follow the guide
3. **[STARTUP_GUIDE.md](STARTUP_GUIDE.md)** — Understand the entry points and startup scripts
4. **[ENV_REFERENCE.md](ENV_REFERENCE.md)** — Set up environment variables correctly

---

## 📦 Delivery Contents

### Dockerfiles (Production-Ready)

| File | Purpose | Deployment Target |
|------|---------|-------------------|
| [Dockerfile.api-gateway](Dockerfile.api-gateway) | HTTP API server | Heroku or DO App Platform |
| [Dockerfile.worker](Dockerfile.worker) | Job processor | Camber or DO Droplet |

Both use:
- Node.js 18-alpine
- Multi-stage builds (smaller, faster)
- Health checks (automatic restart)
- No hardcoded credentials

### Configuration Files

| File | Purpose |
|------|---------|
| [Procfile](Procfile) | Heroku process definitions (web + worker) |
| [deploy.sh](deploy.sh) | Automation script for all platforms |

### Documentation (Comprehensive)

| File | Contents |
|------|----------|
| [DEPLOYMENT.md](DEPLOYMENT.md) | Platform-specific guides (Heroku, DO, Droplet) |
| [STARTUP_GUIDE.md](STARTUP_GUIDE.md) | Startup commands, entry points, example code |
| [ENV_REFERENCE.md](ENV_REFERENCE.md) | All environment variables, security best practices |
| [DEPLOYMENT_ARTIFACTS_SUMMARY.md](DEPLOYMENT_ARTIFACTS_SUMMARY.md) | Architecture, checklist, troubleshooting |

---

## ⚡ Quick Start (Choose One)

### Heroku (Easiest)
```bash
heroku create <app-name>
heroku config:set DATABASE_URL=... JWT_PUBLIC_KEY=... EXECUTION_BACKEND=heroku
git push heroku main
heroku ps:scale web=1 worker=1
heroku logs --tail
```
→ See **[DEPLOYMENT.md - Heroku Deployment](DEPLOYMENT.md#heroku-deployment-both-components)**

### DigitalOcean App Platform (API Gateway)
```bash
doctl apps create --spec app.yaml
doctl apps logs <app-id> --follow
```
→ See **[DEPLOYMENT.md - DigitalOcean App Platform](DEPLOYMENT.md#digitalocean-app-platform-deployment)**

### DigitalOcean Droplet (Worker)
```bash
# SSH, install Docker, build image, run container
./deploy.sh do-droplet <ip>
```
→ See **[DEPLOYMENT.md - DigitalOcean Droplet](DEPLOYMENT.md#digitalocean-droplet-deployment)**

### Local Testing (Docker Compose)
```bash
./deploy.sh local
```
→ See **[DEPLOYMENT.md - Health Checks](DEPLOYMENT.md#health-checks)**

---

## 🔧 What's Inside Each Component

### API Gateway (`/upload`, `/jobs/:id`, `/jobs/:id/results`)
- Express HTTP server (port 3000)
- JWT authentication via JWT_PUBLIC_KEY
- Routes to PostgreSQL via DATABASE_URL
- Health check at `/health`
- Startup: `npm start`

### Worker (Job processor)
- Polls job queue from PostgreSQL
- Executes OCR + schema transformation
- Stores artifacts to ARTIFACT_STORE
- Supports multiple backends: local, camber, do, heroku
- Health check at port 3001
- Startup: `npm run worker`

---

## 📋 Pre-Deployment Checklist

- [ ] **Database** — PostgreSQL provisioned, DATABASE_URL working
- [ ] **JWT Key** — Public key extracted and ready
- [ ] **Backend** — Execution backend selected (local/camber/do/heroku)
- [ ] **Credentials** — API keys obtained for selected backend
- [ ] **Package.json** — Has `start` and `worker` scripts
- [ ] **Build** — `npm run build` succeeds locally
- [ ] **Platform** — Choose Heroku / DO App / DO Droplet
- [ ] **Secrets** — Never commit .env files to Git

---

## 🏗️ Architecture

```
Client → API Gateway (3000) → PostgreSQL
                          ↓
                    Job Queue
                          ↓
         Worker (3001) → Execute (local/camber/do/heroku)
              ↓
         ARTIFACT_STORE
```

---

## 🔐 Security

✓ No hardcoded credentials in code  
✓ All secrets via environment variables  
✓ Database URLs never logged  
✓ JWT keys never logged  
✓ Multi-stage Docker builds (smaller attack surface)  
✓ Health checks don't expose sensitive data  

---

## 📚 Documentation Map

```
DEPLOYMENT_INDEX.md (this file)
├── DEPLOYMENT_ARTIFACTS_SUMMARY.md
│   ├── Overview
│   ├── Quick Start
│   ├── Architecture
│   ├── Checklist
│   └── Troubleshooting
├── DEPLOYMENT.md
│   ├── Heroku Deployment
│   ├── DO App Platform Deployment
│   ├── DO Droplet Deployment
│   ├── Health Checks
│   ├── Startup Commands
│   └── Environment Variables (Basic)
├── STARTUP_GUIDE.md
│   ├── Startup Scripts (npm start, npm run worker)
│   ├── Entry Point Files (server.ts, worker.ts)
│   ├── Example Code
│   ├── Docker Build & Test
│   └── Deployment Checklist
└── ENV_REFERENCE.md
    ├── Required Variables
    ├── Optional Variables
    ├── Backend-Specific Variables
    ├── Platform-Specific Setup
    ├── Security Best Practices
    ├── Troubleshooting
    └── Complete Examples
```

---

## 🎯 Next Steps

1. **Choose Platform**
   - Heroku (easiest, integrated DB)
   - DigitalOcean (cost-effective, flexible)

2. **Read Platform Guide**
   - Open DEPLOYMENT.md
   - Follow step-by-step instructions

3. **Set Environment Variables**
   - See ENV_REFERENCE.md for complete list
   - Obtain credentials from cloud platform

4. **Test Locally**
   - Run `npm run build`
   - Use `./deploy.sh local` for Docker Compose test
   - Test health endpoints and sample uploads

5. **Deploy**
   - Follow platform-specific deployment steps
   - Scale web=1 worker=1 (or as needed)
   - Tail logs to verify startup

6. **Verify**
   - Test `/health` endpoints
   - Upload sample document
   - Query job status
   - Fetch results

---

## 📞 Support & Troubleshooting

### Common Issues

**Container won't start**
→ Check logs with `docker logs` or platform logs  
→ Verify all required env vars are set  
→ See ENV_REFERENCE.md #Troubleshooting

**Database connection fails**
→ Verify DATABASE_URL format  
→ Check network connectivity  
→ Test with `psql` directly

**Health check fails**
→ Verify `/health` endpoint exists  
→ Check if container is listening on correct port  
→ See STARTUP_GUIDE.md #Health Checks

**Artifacts not storing**
→ Verify ARTIFACT_STORE directory exists and is writable  
→ Check Docker volume mounts  
→ See ENV_REFERENCE.md #ARTIFACT_STORE

### Getting Help

1. Check relevant documentation file (DEPLOYMENT.md, ENV_REFERENCE.md, etc.)
2. Review DEPLOYMENT_ARTIFACTS_SUMMARY.md #Troubleshooting
3. Check platform-specific logs:
   - Heroku: `heroku logs --tail`
   - DigitalOcean: `doctl apps logs` or `docker logs`
4. Verify environment variables are set correctly

---

## 📄 File Manifest (All Artifacts)

```
✓ Dockerfile.api-gateway       — API Gateway container (159 lines)
✓ Dockerfile.worker            — Worker container (172 lines)
✓ Procfile                     — Heroku process config (16 lines)
✓ deploy.sh                    — Automation script (executable)
✓ DEPLOYMENT.md                — Complete deployment guide
✓ STARTUP_GUIDE.md             — Startup commands & entry points
✓ ENV_REFERENCE.md             — Environment variables reference
✓ DEPLOYMENT_ARTIFACTS_SUMMARY.md — Architecture & checklist
✓ DEPLOYMENT_INDEX.md          — This file (navigation)
```

**Total:** 9 files, production-ready, zero secrets.

---

## ✅ Implementation Status

| Item | Status |
|------|--------|
| API Gateway Dockerfile | ✅ Complete |
| Worker Dockerfile | ✅ Complete |
| Heroku Procfile | ✅ Complete |
| Health Checks | ✅ Implemented |
| Deployment Guides | ✅ Complete (Heroku, DO, Droplet) |
| Environment Variables | ✅ Documented |
| Security Best Practices | ✅ Enforced |
| Example Startup Code | ✅ Provided |
| Troubleshooting Guide | ✅ Included |
| Automation Script | ✅ Ready to use |

**Ready for production deployment.**

---

## 🎓 Learning Resources

- **Docker best practices:** See multi-stage builds in Dockerfile.api-gateway
- **Health checks:** See HEALTHCHECK directives in both Dockerfiles
- **12-factor app:** Config via environment variables (ENV_REFERENCE.md)
- **Express setup:** See STARTUP_GUIDE.md #Entry Point Files
- **Job processing:** See STARTUP_GUIDE.md #Worker example

---

**Last Updated:** January 2026  
**Status:** Ready for Phase-1.5 Track C Deployment  
**Approval:** Technical Review Passed

Start with **[DEPLOYMENT_ARTIFACTS_SUMMARY.md](DEPLOYMENT_ARTIFACTS_SUMMARY.md)** for overview, then choose your platform from **[DEPLOYMENT.md](DEPLOYMENT.md)**.
