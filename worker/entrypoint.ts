/**
 * Worker Entrypoint
 * ================
 * 
 * Minimal worker startup for Phase-1.5 Track C deployment.
 * 
 * Environment variables required:
 *   - DATABASE_URL or SUPABASE_URL: for Job Queue
 *   - ARTIFACT_STORE_TYPE: s3 or local
 */

import 'dotenv/config';
import { CpuWorker, schemaProvider, inMemoryJobQueue, JobQueue } from '../engine/cpu/worker';
import { SupabaseJobQueue } from '../engine/jobs/supabaseJobQueue';
import { getConfig } from '../bootstrap/config';
import { blobStore } from '../engine/storage/blobStore';

async function startWorker(): Promise<void> {
  const startTime = Date.now();

  try {
    // 1. Validate configuration
    const config = getConfig();
    logStartup('Configuration loaded', {
      backend: config.executionBackend,
      env: config.serviceEnv,
      artifactStoreType: config.artifactStore.type,
    });

    // 2. Initialize Job Queue
    let queue: JobQueue;
    if (config.databaseUrl || process.env.SUPABASE_URL) {
      logStartup('Initializing Supabase Job Queue', {});
      queue = new SupabaseJobQueue();
    } else {
      logStartup('Initializing In-Memory Job Queue', {});
      queue = inMemoryJobQueue;
    }

    // 3. Initialize Worker
    // Note: We use the shared blobStore which is already configured for S3 or Local
    const worker = new CpuWorker({
      queue,
      schemaProvider: schemaProvider, // TODO: Use DbSchemaProvider if schemas are in DB
      // fetchBlob defaults to blobStore.get which is what we want
    });

    logStartup('Worker ready and polling', {
      uptime: `${Date.now() - startTime}ms`,
    });

    // 4. Polling Loop
    let running = true;
    process.on('SIGTERM', () => running = false);
    process.on('SIGINT', () => running = false);

    while (running) {
      try {
        const job = await worker.runOnce();
        if (!job) {
          // No job, sleep for a bit
          await new Promise(resolve => setTimeout(resolve, 1000));
        } else {
          // Job processed, loop immediately to check for more
        }
      } catch (err) {
        console.error('[WORKER] Error in polling loop:', err);
        await new Promise(resolve => setTimeout(resolve, 5000));
      }
    }

    logShutdown('Worker shutting down...');
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    logError('Worker startup failed', message, error);
    process.exit(1);
  }
}

/**
 * Structured logging (no secrets)
 */
function logStartup(message: string, context: Record<string, string | number>): void {
  const timestamp = new Date().toISOString();
  const contextStr = Object.entries(context)
    .map(([k, v]) => `${k}=${v}`)
    .join(' ');
  console.log(`[${timestamp}] [WORKER] ${message} ${contextStr}`);
}

function logError(message: string, error: string, fullError: unknown): void {
  const timestamp = new Date().toISOString();
  console.error(`[${timestamp}] [WORKER] ERROR: ${message}`);
  console.error(`[${timestamp}] [WORKER] Reason: ${error}`);
  if (process.env.SERVICE_ENV !== 'prod') {
    console.error(fullError);
  }
}

function logShutdown(message: string): void {
  const timestamp = new Date().toISOString();
  console.log(`[${timestamp}] [WORKER] ${message}`);
}

// Start worker
startWorker().catch((error) => {
  console.error('Unhandled worker error:', error);
  process.exit(1);
});
