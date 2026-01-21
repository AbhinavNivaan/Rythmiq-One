import { ExecutionBackend } from './executionBackend';

/**
 * Dependencies for DigitalOceanExecutionBackend.
 * Assumes DO credentials/config available via environment variables.
 */
export interface DigitalOceanExecutionBackendDeps {
  // Optional: DO API client instance
  // If not provided, will initialize from environment
  doApiClient?: DigitalOceanApiClient;
}

/**
 * DigitalOcean API client interface.
 * Abstracts the actual DO API client implementation.
 */
export interface DigitalOceanApiClient {
  submitJob(jobId: string, config: DigitalOceanJobConfig): Promise<string>;
}

/**
 * Configuration passed to DigitalOcean for job execution.
 * Contains only jobId and minimal env/config, not schema/payload/secrets.
 */
export interface DigitalOceanJobConfig {
  jobId: string;
  executionEnv?: Record<string, string>;
  timeout?: number;
  appName?: string;
}

/**
 * DigitalOceanExecutionBackend implements ExecutionBackend by delegating
 * job execution to DigitalOcean Apps or Functions.
 *
 * Design principles:
 * - DO is treated as an executor only
 * - No DO-specific error semantics; failures bubble up as generic execution errors
 * - Only jobId and minimal env/config are passed; schema, payload, and secrets are NOT included inline
 * - Job data and artifacts are referenced by jobId, allowing DO to fetch them as needed
 */
export class DigitalOceanExecutionBackend implements ExecutionBackend {
  private readonly doApiClient: DigitalOceanApiClient;
  private readonly appName: string;

  constructor(deps: DigitalOceanExecutionBackendDeps = {}) {
    // Use provided client or initialize default from environment
    this.doApiClient = deps.doApiClient || createDefaultDigitalOceanApiClient();
    this.appName = process.env.DO_APP_NAME || 'rythmiq-execution';
  }

  /**
   * Submits a job to DigitalOcean for execution.
   *
   * @param jobId - The unique job identifier
   * @throws Error if job submission fails (generic execution error)
   */
  async runJob(jobId: string): Promise<void> {
    try {
      const config: DigitalOceanJobConfig = {
        jobId,
        appName: this.appName,
        executionEnv: extractExecutionEnv(),
        timeout: getExecutionTimeout(),
      };

      await this.doApiClient.submitJob(jobId, config);
    } catch (error) {
      // Bubble up as generic execution error (no DO-specific semantics)
      const errorMessage = error instanceof Error ? error.message : String(error);
      throw new Error(`Failed to execute job ${jobId} on DigitalOcean: ${errorMessage}`);
    }
  }
}

/**
 * Extracts execution environment configuration from environment variables.
 * Only includes non-sensitive configuration; credentials are managed separately.
 */
function extractExecutionEnv(): Record<string, string> {
  return {
    DO_EXECUTION_REGION: process.env.DO_EXECUTION_REGION || 'nyc',
    DO_FUNCTION_MEMORY_MB: process.env.DO_FUNCTION_MEMORY_MB || '256',
  };
}

/**
 * Gets the execution timeout in milliseconds from environment or returns default.
 */
function getExecutionTimeout(): number {
  const timeoutStr = process.env.DO_EXECUTION_TIMEOUT_MS;
  if (timeoutStr) {
    const timeout = parseInt(timeoutStr, 10);
    if (!isNaN(timeout) && timeout > 0) {
      return timeout;
    }
  }
  return 300000; // 5 minutes default
}

/**
 * Creates a default DigitalOcean API client from environment configuration.
 * Assumes DigitalOcean credentials are available via environment variables:
 * - DO_API_TOKEN
 * - DO_API_ENDPOINT
 */
function createDefaultDigitalOceanApiClient(): DigitalOceanApiClient {
  const apiToken = process.env.DO_API_TOKEN;
  const apiEndpoint = process.env.DO_API_ENDPOINT || 'https://api.digitalocean.com/v2';

  if (!apiToken) {
    throw new Error('DO_API_TOKEN environment variable is required');
  }

  return new DigitalOceanApiClientImpl(apiEndpoint, apiToken);
}

/**
 * Default implementation of DigitalOceanApiClient.
 * Submits jobs to DO via HTTP API or App Platform.
 */
class DigitalOceanApiClientImpl implements DigitalOceanApiClient {
  constructor(
    private readonly apiEndpoint: string,
    private readonly apiToken: string,
  ) { }

  async submitJob(jobId: string, config: DigitalOceanJobConfig): Promise<string> {
    // Construct request payload with only jobId and env/config
    const payload = {
      jobId,
      appName: config.appName,
      executionEnv: config.executionEnv,
      timeout: config.timeout,
    };

    // Make HTTP request to DigitalOcean API
    const response = await fetch(`${this.apiEndpoint}/apps/exec`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${this.apiToken}`,
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`DigitalOcean API error (${response.status}): ${errorText}`);
    }

    const result = await response.json() as { executionId?: string; jobId?: string };
    return result.executionId || result.jobId || jobId;
  }
}
