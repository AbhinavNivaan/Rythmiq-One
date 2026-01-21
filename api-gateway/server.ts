/**
 * API Gateway Server
 * Phase-1.5 Track C
 *
 * REQUIRED ENVIRONMENT VARIABLES:
 * - DATABASE_URL
 * - JWT_PUBLIC_KEY
 * - SERVICE_ENV          (dev | staging | prod)
 * - ARTIFACT_STORE_TYPE  (local | s3 | gcs)
 * - EXECUTION_BACKEND    (local | camber | do | heroku)
 * - PORT                 (optional, default 3000)
 */

import 'dotenv/config';
import express, { Express, Request, Response } from 'express';
import uploadRoutes from './routes/upload';
import jobRoutes from './routes/jobs';
import resultsRoutes from './routes/results';
import { globalErrorHandler } from './errors/errorHandler';

/* -------------------------------------------------------------------------- */
/*                               ENV VALIDATION                               */
/* -------------------------------------------------------------------------- */

function validateEnvironment(): void {
  const requiredVars = [
    // 'DATABASE_URL', // Optional if SUPABASE_URL is set
    'JWT_PUBLIC_KEY',
    'SERVICE_ENV',
    'ARTIFACT_STORE_TYPE',
    'EXECUTION_BACKEND'
  ];

  const missing = requiredVars.filter(v => !process.env[v]);
  if (missing.length > 0) {
    console.error(`FATAL: Missing required environment variables: ${missing.join(', ')}`);
    process.exit(1);
  }

  if (!process.env.DATABASE_URL && !process.env.SUPABASE_URL) {
    console.error('FATAL: Missing required environment variable: DATABASE_URL or SUPABASE_URL');
    process.exit(1);
  }

  const validServiceEnvs = ['dev', 'staging', 'prod'];
  if (!validServiceEnvs.includes(process.env.SERVICE_ENV!)) {
    console.error(`FATAL: Invalid SERVICE_ENV: ${process.env.SERVICE_ENV}`);
    process.exit(1);
  }

  const validArtifactStores = ['local', 's3', 'gcs'];
  if (!validArtifactStores.includes(process.env.ARTIFACT_STORE_TYPE!)) {
    console.error(`FATAL: Invalid ARTIFACT_STORE_TYPE: ${process.env.ARTIFACT_STORE_TYPE}`);
    process.exit(1);
  }

  const validBackends = ['local', 'camber', 'do', 'heroku'];
  if (!validBackends.includes(process.env.EXECUTION_BACKEND!)) {
    console.error(`FATAL: Invalid EXECUTION_BACKEND: ${process.env.EXECUTION_BACKEND}`);
    process.exit(1);
  }
}

/* -------------------------------------------------------------------------- */
/*                                APP FACTORY                                 */
/* -------------------------------------------------------------------------- */

export function createApp(): Express {
  const app = express();

  /* ------------------------------- Body Parsers ------------------------------ */
  app.use(express.json({ limit: '10kb' }));
  app.use(express.raw({ type: 'application/octet-stream', limit: '100mb' }));

  /* --------------------------------- Health --------------------------------- */
  app.get('/health', (_req: Request, res: Response) => {
    res.status(200).json({ status: 'ok' });
  });

  app.get('/ready', (_req: Request, res: Response) => {
    res.status(200).json({
      status: 'ready',
      service: 'api-gateway',
      env: process.env.SERVICE_ENV
    });
  });

  /* ---------------------------------- Routes --------------------------------- */
  app.use('/upload', uploadRoutes);
  app.use('/jobs', jobRoutes);
  app.use('/results', resultsRoutes);

  /* ----------------------------------- 404 ----------------------------------- */
  app.use((_req: Request, res: Response) => {
    res.status(404).json({ errorCode: 'NOT_FOUND' });
  });

  /* ---------------------------- Global Error Handler -------------------------- */
  app.use(globalErrorHandler);

  return app;
}

/* -------------------------------------------------------------------------- */
/*                                SERVER START                                */
/* -------------------------------------------------------------------------- */

export function startServer(): void {
  validateEnvironment();

  const app = createApp();
  const port = Number(process.env.PORT ?? 3000);

  app.listen(port, () => {
    console.log(`API Gateway listening on port ${port}`);
  });
}

if (require.main === module) {
  startServer();
}