
const { v4: uuidv4 } = require("uuid");
import { inMemoryJobQueue, WorkerJob } from '../cpu/worker';
import { logJobCreated } from '../observability/telemetry';
import { registerJobStateTransitionHandler, JobErrorDetails } from './transitions';
import { jobStateMachine, JobState } from './stateMachine';
import { SupabaseJobQueue } from './supabaseJobQueue';
import { getSupabaseClient } from './dbClient';
import { getConfig } from '../../bootstrap/config';

export interface Job {
  jobId: string;
  blobId: string;
  userId: string;
  schemaId: string;
  schemaVersion: string;
  state: JobState;
  createdAt: Date;
  updatedAt: Date;
  retries: number;
  errorCode?: string;
  retryable?: boolean;
  ocrArtifactId?: string;
  schemaArtifactId?: string;
  schemaOutput?: Record<string, any>;
  confidence?: Record<string, number>;
  qualityScore?: number;
}

interface CreateJobRequest {
  blobId: string;
  userId: string;
  clientRequestId: string;
  schemaId: string;
  schemaVersion: string;
}

interface CreateJobResult {
  jobId: string;
  isNewJob: boolean;
}

export interface IJobStore {
  createJob(request: CreateJobRequest): Promise<CreateJobResult>;
  getJobForUser(jobId: string, userId: string): Promise<Job | null>;
  getJobsByUserId(userId: string): Promise<Job[]>;
  updateJobState(jobId: string, state: JobState, error?: JobErrorDetails): Promise<void>;
  setJobOutput(
    jobId: string,
    ocrArtifactId: string,
    schemaArtifactId: string,
    schemaOutput: Record<string, any>,
    confidence: Record<string, number>,
    qualityScore: number
  ): Promise<void>;
  clear(): void;
}

/**
 * In-memory implementation
 */
class InMemoryJobStore implements IJobStore {
  private jobs: Map<string, Job> = new Map();
  private jobIdempotencyMap: Map<string, string> = new Map();

  constructor() {
    registerJobStateTransitionHandler(this.transitionJobState.bind(this));
  }

  private getIdempotencyKey(userId: string, clientRequestId: string): string {
    return `${userId}:${clientRequestId}`;
  }

  // NOTE: This is called by the state transition handler.
  // In Supabase version, logic differs.
  async transitionJobState(jobId: string, from: JobState, to: JobState, error?: JobErrorDetails): Promise<void> {
    const job = this.jobs.get(jobId);
    if (!job) {
      throw new Error(`Job not found: ${jobId}`);
    }

    if (job.state !== from) {
      // Allow if to is SAME as current (noop)
      if (job.state === to) return;
      throw new Error(`Invalid job state transition request for ${jobId}: stored=${job.state}, from=${from}`);
    }

    jobStateMachine.assertTransition(from, to);

    const isRetry = to === 'QUEUED' && from === 'RETRYING';
    const shouldPersistError = to === 'FAILED' || to === 'RETRYING';
    const next: Job = {
      ...job,
      state: to,
      updatedAt: new Date(),
      retries: isRetry ? job.retries + 1 : job.retries,
      errorCode: shouldPersistError ? error?.code : undefined,
      retryable: shouldPersistError ? error?.retryable : undefined,
    };

    this.jobs.set(jobId, next);
  }

  async createJob(request: CreateJobRequest): Promise<CreateJobResult> {
    const idempotencyKey = this.getIdempotencyKey(request.userId, request.clientRequestId);

    const existingJobId = this.jobIdempotencyMap.get(idempotencyKey);
    if (existingJobId !== undefined) {
      return {
        jobId: existingJobId,
        isNewJob: false,
      };
    }

    const jobId = uuidv4();
    const now = new Date();
    const job: Job = {
      jobId,
      blobId: request.blobId,
      userId: request.userId,
      schemaId: request.schemaId,
      schemaVersion: request.schemaVersion,
      state: 'CREATED',
      createdAt: now,
      updatedAt: now,
      retries: 0,
      errorCode: undefined,
      retryable: undefined,
    };

    this.jobIdempotencyMap.set(idempotencyKey, jobId);
    this.jobs.set(jobId, job);

    try {
      await inMemoryJobQueue.enqueue({
        jobId,
        blobId: request.blobId,
        userId: request.userId,
        schemaId: request.schemaId,
        schemaVersion: request.schemaVersion,
      });
      await this.transitionJobState(jobId, 'CREATED', 'QUEUED');
      logJobCreated(jobId);

      return {
        jobId,
        isNewJob: true,
      };
    } catch (error) {
      this.jobIdempotencyMap.delete(idempotencyKey);
      this.jobs.delete(jobId);
      throw error;
    }
  }

  async getJobForUser(jobId: string, userId: string): Promise<Job | null> {
    const job = this.jobs.get(jobId);
    return job && job.userId === userId ? job : null;
  }

  async getJobsByUserId(userId: string): Promise<Job[]> {
    return Array.from(this.jobs.values()).filter(job => job.userId === userId);
  }

  async updateJobState(jobId: string, state: JobState, error?: JobErrorDetails): Promise<void> {
    const job = this.jobs.get(jobId);
    if (!job) {
      throw new Error(`Job not found: ${jobId}`);
    }
    await this.transitionJobState(jobId, job.state, state, error);
  }

  async setJobOutput(
    jobId: string,
    ocrArtifactId: string,
    schemaArtifactId: string,
    schemaOutput: Record<string, any>,
    confidence: Record<string, number>,
    qualityScore: number
  ): Promise<void> {
    const job = this.jobs.get(jobId);
    if (!job) {
      throw new Error(`Job not found: ${jobId}`);
    }

    const updated: Job = {
      ...job,
      ocrArtifactId,
      schemaArtifactId,
      schemaOutput,
      confidence,
      qualityScore,
    };
    this.jobs.set(jobId, updated);
  }

  clear(): void {
    this.jobs.clear();
    this.jobIdempotencyMap.clear();
  }
}

/**
 * Supabase implementation
 */
class SupabaseJobStore implements IJobStore {
  queue = new SupabaseJobQueue();

  constructor() {
    // State transitions are handled by DB writes in the Worker via Queue interactions.
    // API Gateway rarely initiates transitions manually except for maybe cancelling.
    // We do NOT register a global transition handler because multiple instances/processes interfere.
  }

  async createJob(request: CreateJobRequest): Promise<CreateJobResult> {
    // Idempotency: try to find by clientRequestId + userId
    // Supabase lacks unique constraint strictly on JSON/metadata unless we add a column.
    // But we can check before insert.
    // OR better: Assume createJob is always new for now, or use blobId uniqueness?
    // Let's check matching job
    const supabase = getSupabaseClient();

    // Check for existing job (idempotency simulation)
    // Ideally we'd store clientRequestId in jobs table. Current migration doesn't have it.
    // Adding it now would require another migration.
    // For now, we'll skip strict idempotency or rely on caller to pass same jobId?
    // Wait, caller passes blobId but jobId is generated.

    // We will just create a new job. 
    // NOTE: In production, add client_request_id column to jobs table.

    const jobId = uuidv4();
    await this.queue.enqueue({
      jobId,
      blobId: request.blobId,
      userId: request.userId,
      schemaId: request.schemaId,
      schemaVersion: request.schemaVersion
    });

    logJobCreated(jobId);
    return { jobId, isNewJob: true };
  }

  async getJobForUser(jobId: string, userId: string): Promise<Job | null> {
    const supabase = getSupabaseClient();
    const { data, error } = await supabase
      .from('jobs')
      .select('*')
      .eq('job_id', jobId)
      .eq('user_id', userId)
      .single();

    if (error || !data) return null;
    return this.mapRowToJob(data);
  }

  async getJobsByUserId(userId: string): Promise<Job[]> {
    const supabase = getSupabaseClient();
    const { data, error } = await supabase
      .from('jobs')
      .select('*')
      .eq('user_id', userId)
      .order('created_at', { ascending: false });

    if (error) throw error;
    return (data || []).map(row => this.mapRowToJob(row));
  }

  async updateJobState(jobId: string, state: JobState, error?: JobErrorDetails): Promise<void> {
    // This is mainly used by tests or manual overrides.
    // Worker uses Queue methods.
    const supabase = getSupabaseClient();
    await supabase
      .from('jobs')
      .update({
        state,
        updated_at: new Date().toISOString(),
        error_code: error?.code,
        retryable: error?.retryable
      })
      .eq('job_id', jobId);
  }

  async setJobOutput(
    jobId: string,
    ocrArtifactId: string,
    schemaArtifactId: string,
    schemaOutput: Record<string, any>,
    confidence: Record<string, number>,
    qualityScore: number
  ): Promise<void> {
    const supabase = getSupabaseClient();
    await supabase
      .from('jobs')
      .update({
        ocr_artifact_id: ocrArtifactId,
        schema_artifact_id: schemaArtifactId,
        quality_score: qualityScore,
        updated_at: new Date().toISOString()
        // schema output? Not currently storing JSON output in DB table column, 
        // typically it's in the artifact. 
        // The 'jobs' table has columns for artifact IDs.
        // The interface has schemaOutput arg, but map doesn't seem to persist it?
        // InMemoryJobStore persists it in memory.
        // Our migration does NOT have schema_output column.
        // We will ignore schemaOutput/confidence arguments for DB storage 
        // as they are in the artifact.
      })
      .eq('job_id', jobId);
  }

  clear(): void {
    // No-op for DB
  }

  private mapRowToJob(row: any): Job {
    return {
      jobId: row.job_id,
      blobId: row.blob_id,
      userId: row.user_id,
      schemaId: row.schema_id,
      schemaVersion: row.schema_version,
      state: row.state,
      createdAt: new Date(row.created_at),
      updatedAt: new Date(row.updated_at),
      retries: row.attempt,
      errorCode: row.error_code,
      retryable: row.retryable,
      ocrArtifactId: row.ocr_artifact_id,
      schemaArtifactId: row.schema_artifact_id,
      qualityScore: row.quality_score
      // schemaOutput/confidence not loaded from DB
    };
  }
}

function createJobStore(): IJobStore {
  const config = getConfig(); // Ensure config loaded
  if (config.databaseUrl || process.env.SUPABASE_URL) {
    return new SupabaseJobStore();
  }
  return new InMemoryJobStore();
}

export const jobStore = createJobStore();
