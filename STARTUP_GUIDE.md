# Startup Commands & Entry Points

## Quick Reference

```bash
# API Gateway (HTTP server)
npm start

# Worker (Job processor)
npm run worker
```

---

## Startup Script Requirements

Your `package.json` must include:

```json
{
  "scripts": {
    "start": "node dist/server.js",
    "worker": "node dist/worker.js",
    "build": "tsc"
  },
  "devDependencies": {
    "typescript": "^5.0.0"
  },
  "dependencies": {
    "express": "^4.18.0",
    "dotenv": "^16.0.0"
  }
}
```

---

## Entry Point Files

### API Gateway: `src/server.ts`

Minimal example:

```typescript
import express from 'express';
import { initializeExecutionBackend } from './app/executionBackendIntegration';
import uploadRoutes from './api-gateway/routes/upload';
import jobRoutes from './api-gateway/routes/jobs';
import resultsRoutes from './api-gateway/routes/results';
import { authenticateRequest } from './api-gateway/auth/middleware';

const app = express();
const port = process.env.PORT || 3000;

// Middleware
app.use(express.json());
app.use(express.raw({ type: 'application/octet-stream', limit: '50mb' }));

// Health check (before auth)
app.get('/health', (req, res) => {
  res.status(200).json({ status: 'ok', timestamp: new Date().toISOString() });
});

// Routes (with auth)
app.use('/upload', uploadRoutes);
app.use('/jobs', jobRoutes);
app.use('/results', resultsRoutes);

// Error handler (last)
app.use((err: any, req: express.Request, res: express.Response, next: express.NextFunction) => {
  console.error('Unhandled error:', err);
  res.status(err.status || 500).json({
    error: err.message || 'Internal server error',
    code: err.code || 'INTERNAL_ERROR',
  });
});

app.listen(port, () => {
  console.log(`✓ API Gateway listening on port ${port}`);
  console.log(`✓ Health: GET /health`);
  console.log(`✓ Upload: POST /upload`);
  console.log(`✓ Job Status: GET /jobs/:id`);
  console.log(`✓ Results: GET /jobs/:id/results`);
});
```

### Worker: `src/worker.ts`

Minimal example:

```typescript
import { initializeExecutionBackend } from './app/executionBackendIntegration';
import { cpuWorker } from './engine/cpu/worker';

const POLL_INTERVAL_MS = 5000;  // Poll for jobs every 5 seconds
const port = process.env.PORT || 3001;

async function startWorker() {
  try {
    console.log('[Worker] Initializing...');
    const backend = await initializeExecutionBackend();
    console.log(`[Worker] Ready. EXECUTION_BACKEND=${process.env.EXECUTION_BACKEND || 'local'}`);

    // Health check endpoint (optional, for container orchestration)
    const http = require('http');
    http.createServer((req: any, res: any) => {
      if (req.url === '/health' && req.method === 'GET') {
        res.writeHead(200);
        res.end(JSON.stringify({ status: 'running', timestamp: new Date().toISOString() }));
      } else {
        res.writeHead(404);
        res.end();
      }
    }).listen(port, () => {
      console.log(`[Worker] Health check available at http://localhost:${port}/health`);
    });

    // Main processing loop
    setInterval(async () => {
      try {
        const job = await cpuWorker.runOnce();
        if (job) {
          console.log(`[Worker] Processed job: ${job.jobId} -> ${job.state}`);
        }
      } catch (error) {
        console.error('[Worker] Error processing job:', error instanceof Error ? error.message : error);
      }
    }, POLL_INTERVAL_MS);

    // Graceful shutdown
    process.on('SIGTERM', () => {
      console.log('[Worker] SIGTERM received, shutting down...');
      process.exit(0);
    });

  } catch (error) {
    console.error('[Worker] Fatal error:', error);
    process.exit(1);
  }
}

startWorker();
```

---

## Environment Variables

### Required (Both)
```
NODE_ENV=production
DATABASE_URL=postgresql://user:pass@host/db
```

### Required (API Gateway Only)
```
JWT_PUBLIC_KEY="-----BEGIN PUBLIC KEY-----..."
```

### Required (Worker Only)
```
EXECUTION_BACKEND=local|camber|do|heroku
ARTIFACT_STORE=/path/to/artifacts
```

### Optional
```
PORT=3000
LOG_LEVEL=info
```

---

## Docker Build & Test

```bash
# Build API Gateway
docker build -f Dockerfile.api-gateway -t rythmiq-api:latest .

# Build Worker
docker build -f Dockerfile.worker -t rythmiq-worker:latest .

# Test API Gateway locally
docker run -p 3000:3000 \
  -e DATABASE_URL="postgres://localhost/test" \
  -e JWT_PUBLIC_KEY="test-key" \
  rythmiq-api:latest

# Test Worker locally
docker run -p 3001:3001 \
  -e DATABASE_URL="postgres://localhost/test" \
  -e ARTIFACT_STORE="/tmp/artifacts" \
  -e EXECUTION_BACKEND=local \
  rythmiq-worker:latest
```

---

## Deployment Checklist

- [ ] `package.json` has `start` and `worker` scripts
- [ ] `src/server.ts` exists and listens on PORT or 3000
- [ ] `src/worker.ts` exists and has polling loop
- [ ] DATABASE_URL is set and database is accessible
- [ ] JWT_PUBLIC_KEY is set (API Gateway)
- [ ] ARTIFACT_STORE is writable (Worker)
- [ ] `/health` endpoint responds 200 OK
- [ ] `npm run build` compiles without errors
- [ ] `npm start` starts API Gateway
- [ ] `npm run worker` starts Worker
