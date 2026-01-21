import { ExecutionBackend } from './executionBackend';

/**
 * Dependencies for HerokuExecutionBackend.
 * Assumes Heroku credentials/config available via environment variables.
 */
export interface HerokuExecutionBackendDeps {
  // Optional: Heroku API client instance
  // If not provided, will initialize from environment
  herokuApiClient?: HerokuApiClient;
}

/**
 * Heroku API client interface.
 * Abstracts the actual Heroku API client implementation.
 */
export interface HerokuApiClient {
  submitJob(jobId: string, config: HerokuJobConfig): Promise<string>;
}

/**
 * Configuration passed to Heroku for job execution.
 * Contains only jobId and minimal env/config, not schema/payload/secrets.
 */
export interface HerokuJobConfig {
  jobId: string;
  executionEnv?: Record<string, string>;
  timeout?: number;
  dynoType?: string;
}

/**
 * HerokuExecutionBackend implements ExecutionBackend by delegating
 * job execution to Heroku dynos or Heroku Scheduler.
 *
 * Design principles:
 * - Heroku is treated as an executor only
 * - No Heroku-specific error semantics; failures bubble up as generic execution errors
 * - Only jobId and minimal env/config are passed; schema, payload, and secrets are NOT included inline
 * - Job data and artifacts are referenced by jobId, allowing Heroku to fetch them as needed
 */
export class HerokuExecutionBackend implements ExecutionBackend {
  private readonly herokuApiClient: HerokuApiClient;
  private readonly appName: string;
  private readonly dynoType: string;

  constructor(deps: HerokuExecutionBackendDeps = {}) {
    // Use provided client or initialize default from environment
    this.herokuApiClient = deps.herokuApiClient || createDefaultHerokuApiClient();
    this.appName = process.env.HEROKU_APP_NAME || 'rythmiq-execution';
    this.dynoType = process.env.HEROKU_DYNO_TYPE || 'worker';
  }

  /**
   * Submits a job to Heroku for execution.
   *
   * @param jobId - The unique job identifier
   * @throws Error if job submission fails (generic execution error)
   */
  async runJob(jobId: string): Promise<void> {
    try {
      const config: HerokuJobConfig = {
        jobId,
        dynoType: this.dynoType,
        executionEnv: extractExecutionEnv(),
        timeout: getExecutionTimeout(),
      };

      await this.herokuApiClient.submitJob(jobId, config);
    } catch (error) {
      // Bubble up as generic execution error (no Heroku-specific semantics)
      const errorMessage = error instanceof Error ? error.message : String(error);
      throw new Error(`Failed to execute job ${jobId} on Heroku: ${errorMessage}`);
    }
  }
}

/**
 * Extracts execution environment configuration from environment variables.
 * Only includes non-sensitive configuration; credentials are managed separately.
 */
function extractExecutionEnv(): Record<string, string> {
  return {
    HEROKU_RELEASE_VERSION: process.env.HEROKU_RELEASE_VERSION || 'v1',
    HEROKU_DYNO_SIZE: process.env.HEROKU_DYNO_SIZE || 'standard-1x',
  };
}

/**
 * Gets the execution timeout in milliseconds from environment or returns default.
 */
function getExecutionTimeout(): number {
  const timeoutStr = process.env.HEROKU_EXECUTION_TIMEOUT_MS;
  if (timeoutStr) {
    const timeout = parseInt(timeoutStr, 10);
    if (!isNaN(timeout) && timeout > 0) {
      return timeout;
    }
  }
  return 300000; // 5 minutes default
}

/**
 * Creates a default Heroku API client from environment configuration.
 * Assumes Heroku credentials are available via environment variables:
 * - HEROKU_API_KEY
 * - HEROKU_API_ENDPOINT (optional)
 */
function createDefaultHerokuApiClient(): HerokuApiClient {
  const apiKey = process.env.HEROKU_API_KEY;
  const apiEndpoint = process.env.HEROKU_API_ENDPOINT || 'https://api.heroku.com';

  if (!apiKey) {
    throw new Error('HEROKU_API_KEY environment variable is required');
  }

  return new HerokuApiClientImpl(apiEndpoint, apiKey);
}

/**
 * Default implementation of HerokuApiClient.
 * Submits jobs to Heroku via HTTP API or dyno creation.
 */
class HerokuApiClientImpl implements HerokuApiClient {
  constructor(
    private readonly apiEndpoint: string,
    private readonly apiKey: string,
  ) { }

  async submitJob(jobId: string, config: HerokuJobConfig): Promise<string> {
    // Construct request payload with only jobId and env/config
    const payload = {
      jobId,
      dynoType: config.dynoType,
      executionEnv: config.executionEnv,
      timeout: config.timeout,
    };

    // Make HTTP request to Heroku API
    // Using Heroku's dyno creation endpoint
    const response = await fetch(`${this.apiEndpoint}/apps/dynos`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${this.apiKey}`,
        Accept: 'application/vnd.heroku+json; version=3',
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Heroku API error (${response.status}): ${errorText}`);
    }

    const result = await response.json() as { id?: string; jobId?: string };
    return result.id || result.jobId || jobId;
  }
}
