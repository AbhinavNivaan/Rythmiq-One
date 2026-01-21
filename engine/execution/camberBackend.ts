import { ExecutionBackend } from './executionBackend';

/**
 * Dependencies for CamberExecutionBackend.
 * Assumes Camber credentials/config available via environment variables.
 */
export interface CamberExecutionBackendDeps {
  // Optional: Camber API client instance
  // If not provided, will initialize from environment
  camberApiClient?: CamberApiClient;
}

/**
 * Camber SDK/API client interface.
 * Abstracts the actual Camber client implementation.
 */
export interface CamberApiClient {
  submitJob(jobId: string, config: CamberJobConfig): Promise<string>;
}

/**
 * Configuration passed to Camber for job execution.
 * Contains only jobId and minimal env/config, not schema/payload/secrets.
 */
export interface CamberJobConfig {
  jobId: string;
  executionEnv?: Record<string, string>;
  timeout?: number;
  retryPolicy?: CamberRetryPolicy;
}

/**
 * Retry policy specific to Camber execution.
 */
export interface CamberRetryPolicy {
  maxRetries: number;
  initialDelayMs: number;
  backoffMultiplier: number;
}

/**
 * Default retry policy for Camber execution.
 */
const DEFAULT_CAMBER_RETRY_POLICY: CamberRetryPolicy = {
  maxRetries: 3,
  initialDelayMs: 1000,
  backoffMultiplier: 2,
};

/**
 * CamberExecutionBackend implements ExecutionBackend by delegating
 * job execution to Camber Cloud as an external execution engine.
 *
 * Design principles:
 * - Camber is treated as an executor only
 * - No Camber-specific error semantics; failures bubble up as generic execution errors
 * - Only jobId and minimal env/config are passed; schema, payload, and secrets are NOT included inline
 * - Job data and artifacts are referenced by jobId, allowing Camber to fetch them as needed
 */
export class CamberExecutionBackend implements ExecutionBackend {
  private readonly camberApiClient: CamberApiClient;
  private readonly defaultRetryPolicy: CamberRetryPolicy;

  constructor(deps: CamberExecutionBackendDeps = {}) {
    // Use provided client or initialize default from environment
    this.camberApiClient = deps.camberApiClient || createDefaultCamberApiClient();
    this.defaultRetryPolicy = DEFAULT_CAMBER_RETRY_POLICY;
  }

  /**
   * Submits a job to Camber Cloud for execution.
   *
   * @param jobId - The unique job identifier
   * @throws Error if job submission fails (generic execution error)
   */
  async runJob(jobId: string): Promise<void> {
    try {
      const config: CamberJobConfig = {
        jobId,
        executionEnv: extractExecutionEnv(),
        timeout: getExecutionTimeout(),
        retryPolicy: this.defaultRetryPolicy,
      };

      await this.camberApiClient.submitJob(jobId, config);
    } catch (error) {
      // Bubble up as generic execution error (no Camber-specific semantics)
      const errorMessage = error instanceof Error ? error.message : String(error);
      throw new Error(`Failed to execute job ${jobId} on Camber: ${errorMessage}`);
    }
  }
}

/**
 * Extracts execution environment configuration from environment variables.
 * Only includes non-sensitive configuration; credentials are managed separately.
 */
function extractExecutionEnv(): Record<string, string> {
  return {
    // Placeholder for environment-specific configuration
    CAMBER_EXECUTION_REGION: process.env.CAMBER_EXECUTION_REGION || 'us-east-1',
    CAMBER_QUEUE_NAME: process.env.CAMBER_QUEUE_NAME || 'default',
  };
}

/**
 * Gets the execution timeout in milliseconds from environment or returns default.
 */
function getExecutionTimeout(): number {
  const timeoutStr = process.env.CAMBER_EXECUTION_TIMEOUT_MS;
  if (timeoutStr) {
    const timeout = parseInt(timeoutStr, 10);
    if (!isNaN(timeout) && timeout > 0) {
      return timeout;
    }
  }
  return 300000; // 5 minutes default
}

/**
 * Creates a default Camber API client from environment configuration.
 * Assumes Camber credentials are available via environment variables:
 * - CAMBER_API_KEY
 * - CAMBER_API_ENDPOINT
 */
function createDefaultCamberApiClient(): CamberApiClient {
  const apiKey = process.env.CAMBER_API_KEY;
  const apiEndpoint = process.env.CAMBER_API_ENDPOINT || 'https://api.camber.cloud';

  if (!apiKey) {
    throw new Error('CAMBER_API_KEY environment variable is required');
  }

  return new CamberApiClientImpl(apiEndpoint, apiKey);
}

/**
 * Default implementation of CamberApiClient.
 * This can be replaced with the actual Camber SDK client when available.
 */
class CamberApiClientImpl implements CamberApiClient {
  constructor(
    private readonly apiEndpoint: string,
    private readonly apiKey: string,
  ) { }

  async submitJob(jobId: string, config: CamberJobConfig): Promise<string> {
    // Construct request payload with only jobId and env/config
    const payload = {
      jobId,
      executionEnv: config.executionEnv,
      timeout: config.timeout,
      retryPolicy: config.retryPolicy,
    };

    // Make HTTP request to Camber API
    const response = await fetch(`${this.apiEndpoint}/v1/jobs/submit`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${this.apiKey}`,
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Camber API error (${response.status}): ${errorText}`);
    }

    const result = await response.json() as { executionId?: string; jobId?: string };
    return result.executionId || result.jobId || jobId;
  }
}
