import { CpuWorker, cpuWorker } from '../engine/cpu/worker';
import { selectExecutionBackend, ExecutionSelectorDeps } from '../bootstrap/executionSelector';
import { ExecutionBackend } from '../engine/execution/executionBackend';

/**
 * Example: Initializing the Execution Backend in your application
 *
 * This file demonstrates how to integrate the execution backend selector
 * into your application startup sequence.
 */

/**
 * Application bootstrap function.
 * Initializes the execution backend based on EXECUTION_BACKEND env var.
 */
export async function initializeExecutionBackend(): Promise<ExecutionBackend> {
  // For local backend, we need to initialize CpuWorker
  // For other backends, we can pass empty deps (they use env vars)

  const deps: ExecutionSelectorDeps = {};

  // Only initialize local backend dependencies if needed
  if (isLocalBackendSelected()) {
    // Use pre-configured cpuWorker instance with proper dependencies
    deps.localDeps = { worker: cpuWorker };
  }

  try {
    const backend = selectExecutionBackend(deps);
    logBackendInitialization(backend);
    return backend;
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    throw new Error(`Failed to initialize execution backend: ${errorMessage}`);
  }
}

/**
 * Check if local backend is selected.
 */
function isLocalBackendSelected(): boolean {
  const backend = (process.env.EXECUTION_BACKEND || 'local').toLowerCase().trim();
  return backend === 'local';
}

/**
 * Log backend initialization details for debugging.
 */
function logBackendInitialization(backend: ExecutionBackend): void {
  const backendType = process.env.EXECUTION_BACKEND || 'local';
  console.log(`[BOOTSTRAP] Execution backend initialized: ${backendType}`);
  console.log(`[BOOTSTRAP] Backend instance: ${backend.constructor.name}`);

  // Log relevant environment variables (non-sensitive)
  if (backendType === 'camber') {
    console.log(`[BOOTSTRAP] Camber region: ${process.env.CAMBER_EXECUTION_REGION || 'us-east-1'}`);
  } else if (backendType === 'do') {
    console.log(`[BOOTSTRAP] DigitalOcean region: ${process.env.DO_EXECUTION_REGION || 'nyc'}`);
    console.log(`[BOOTSTRAP] DO app name: ${process.env.DO_APP_NAME || 'rythmiq-execution'}`);
  } else if (backendType === 'heroku') {
    console.log(`[BOOTSTRAP] Heroku app: ${process.env.HEROKU_APP_NAME || 'rythmiq-execution'}`);
    console.log(`[BOOTSTRAP] Heroku dyno type: ${process.env.HEROKU_DYNO_TYPE || 'worker'}`);
  }
}

/**
 * Example: Using the execution backend in your job router/handler.
 */
export class JobExecutor {
  constructor(private readonly backend: ExecutionBackend) { }

  async executeJob(jobId: string): Promise<void> {
    try {
      console.log(`[JobExecutor] Executing job ${jobId} on ${process.env.EXECUTION_BACKEND || 'local'}`);
      await this.backend.runJob(jobId);
      console.log(`[JobExecutor] Job ${jobId} execution completed`);
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      console.error(`[JobExecutor] Job ${jobId} failed: ${errorMessage}`);
      throw error;
    }
  }
}

/**
 * Example: Express app integration
 *
 * // In your main app.ts or server initialization:
 *
 * import express from 'express';
 * import { initializeExecutionBackend, JobExecutor } from './app/executionBackendIntegration';
 *
 * const app = express();
 * let jobExecutor: JobExecutor;
 *
 * (async () => {
 *   const backend = await initializeExecutionBackend();
 *   jobExecutor = new JobExecutor(backend);
 *
 *   app.post('/api/jobs/:jobId/execute', async (req, res) => {
 *     try {
 *       await jobExecutor.executeJob(req.params.jobId);
 *       res.json({ success: true, jobId: req.params.jobId });
 *     } catch (error) {
 *       res.status(500).json({ error: (error as Error).message });
 *     }
 *   });
 *
 *   app.listen(3000, () => {
 *     console.log('Server listening on port 3000');
 *   });
 * })();
 */

/**
 * Example: Dependency injection setup
 *
 * // In a DI container or factory:
 *
 * import { Container } from 'inversify';
 * import { ExecutionBackend } from '../engine/execution/executionBackend';
 *
 * const container = new Container();
 *
 * container.bind<ExecutionBackend>(Symbol.for('ExecutionBackend'))
 *   .toDynamicValue(async (context) => {
 *     return initializeExecutionBackend();
 *   })
 *   .inSingletonScope();
 *
 * container.bind<JobExecutor>(JobExecutor)
 *   .toSelf()
 *   .inSingletonScope();
 */
