import { blobStore } from '../storage/blobStore';
import { jobStateMachine, JobState } from '../jobs/stateMachine';
import { transitionJobState } from '../jobs/transitions';
import { defaultRetryPolicy, RetryPolicy } from '../jobs/retryPolicy';
import { logJobFailed, logJobStarted, logJobSucceeded } from '../observability/telemetry';
import { extractText, isOCRSuccess, OCRErrorCode } from './ocrAdapter';
import { SchemaTransformer, SchemaDefinition, TransformValidator } from '../transform/schemaTransform';
import { SchemaProvider, SchemaNotFoundError, DbSchemaProvider } from '../schema/schemaProvider';
import { SchemaStore, SchemaStoreDb } from '../schema/schemaStore';
import { normalizeText } from '../transform/normalizeText';
import { ProcessingError, ProcessingStage } from '../jobs/errors';

export interface WorkerJob {
  jobId: string;
  blobId: string;
  userId: string;
  state: JobState;
  createdAt: Date;
  updatedAt: Date;
  attempt: number;
  maxAttempts: number;
  nextVisibleAt: Date;
  ocrArtifactId?: string;
  schemaArtifactId?: string;
  qualityScore?: number;
  errorCode?: string;
  retryable?: boolean;
  // Optional schema selection metadata
  schemaId?: string;
  schemaVersion?: string;
}

export interface JobQueue {
  enqueue(job: Pick<WorkerJob, 'jobId' | 'blobId' | 'userId' | 'schemaId' | 'schemaVersion'>): Promise<WorkerJob>;
  getNextQueued(now?: Date): Promise<WorkerJob | null>;
  markRunning(jobId: string): Promise<WorkerJob>;
  markSucceeded(jobId: string, ocrArtifactId: string, schemaArtifactId: string, qualityScore: number): Promise<WorkerJob>;
  markFailed(jobId: string, error: ProcessingError): Promise<WorkerJob>;
  scheduleRetry(jobId: string, nextVisibleAt: Date, error: ProcessingError): Promise<WorkerJob>;
}

export type BlobFetcher = (blobId: string) => Promise<Buffer | null>;
export type ArtifactWriter = (bytes: Buffer, userId: string) => Promise<string>;
export type BlobProcessor = (bytes: Buffer) => Promise<Buffer>;

/**
 * Minimal in-memory queue suitable for single-process demos/tests.
 */
export class InMemoryJobQueue implements JobQueue {
  private jobs: Map<string, WorkerJob> = new Map();
  private readonly maxAttempts: number;

  constructor(maxRetries: number = 3) {
    // attempts = 1 initial + maxRetries
    this.maxAttempts = maxRetries + 1;
  }

  async enqueue(job: Pick<WorkerJob, 'jobId' | 'blobId' | 'userId' | 'schemaId' | 'schemaVersion'>): Promise<WorkerJob> {
    const now = new Date();
    const record: WorkerJob = {
      ...job,
      state: 'QUEUED',
      createdAt: now,
      updatedAt: now,
      attempt: 0,
      maxAttempts: this.maxAttempts,
      nextVisibleAt: now,
    };
    this.jobs.set(job.jobId, record);
    return record;
  }

  async getNextQueued(now: Date = new Date()): Promise<WorkerJob | null> {
    await this.promoteReadyRetries(now);
    const queued = Array.from(this.jobs.values())
      .filter(job => job.state === 'QUEUED' && job.nextVisibleAt.getTime() <= now.getTime())
      .sort((a, b) => a.createdAt.getTime() - b.createdAt.getTime());
    return queued.length > 0 ? queued[0] : null;
  }

  async markRunning(jobId: string): Promise<WorkerJob> {
    const job = this.requireJob(jobId);
    jobStateMachine.assertTransition(job.state, 'RUNNING');
    if (job.attempt >= job.maxAttempts) {
      throw new Error(`Attempt limit reached for job ${jobId}`);
    }
    const next: WorkerJob = {
      ...job,
      state: 'RUNNING',
      updatedAt: new Date(),
      attempt: job.attempt + 1,
      nextVisibleAt: job.nextVisibleAt,
    };
    this.jobs.set(jobId, next);
    logJobStarted(jobId);
    return next;
  }

  async markSucceeded(jobId: string, ocrArtifactId: string, schemaArtifactId: string, qualityScore: number): Promise<WorkerJob> {
    const job = this.requireJob(jobId);
    jobStateMachine.assertTransition(job.state, 'SUCCEEDED');
    const next: WorkerJob = {
      ...job,
      state: 'SUCCEEDED',
      updatedAt: new Date(),
      ocrArtifactId,
      schemaArtifactId,
      qualityScore,
      errorCode: undefined,
      retryable: false,
    };
    this.jobs.set(jobId, next);
    logJobSucceeded(jobId);
    return next;
  }

  async markFailed(jobId: string, error: ProcessingError): Promise<WorkerJob> {
    const job = this.requireJob(jobId);
    jobStateMachine.assertTransition(job.state, 'FAILED');
    const next: WorkerJob = {
      ...job,
      state: 'FAILED',
      updatedAt: new Date(),
      errorCode: error.code,
      retryable: error.retryable,
    };
    this.jobs.set(jobId, next);
    logJobFailed(jobId);
    return next;
  }

  async scheduleRetry(jobId: string, nextVisibleAt: Date, error: ProcessingError): Promise<WorkerJob> {
    const job = this.requireJob(jobId);
    jobStateMachine.assertTransition(job.state, 'RETRYING');
    const next: WorkerJob = {
      ...job,
      state: 'RETRYING',
      updatedAt: new Date(),
      nextVisibleAt,
      errorCode: error.code,
      retryable: error.retryable,
    };
    this.jobs.set(jobId, next);
    return next;
  }

  private async promoteReadyRetries(now: Date): Promise<void> {
    const nowMs = now.getTime();
    for (const job of this.jobs.values()) {
      if (job.state !== 'RETRYING' || job.nextVisibleAt.getTime() > nowMs) {
        continue;
      }
      jobStateMachine.assertTransition(job.state, 'QUEUED');
      await transitionJobState(job.jobId, 'RETRYING', 'QUEUED');
      const promoted: WorkerJob = {
        ...job,
        state: 'QUEUED',
        updatedAt: now,
        nextVisibleAt: now,
      };
      this.jobs.set(job.jobId, promoted);
    }
  }

  private requireJob(jobId: string): WorkerJob {
    const job = this.jobs.get(jobId);
    if (!job) {
      throw new Error(`Job not found: ${jobId}`);
    }
    return job;
  }
}

const defaultBlobFetcher: BlobFetcher = async (blobId: string) => {
  return blobStore.get(blobId);
};

const defaultArtifactWriter: ArtifactWriter = async (bytes: Buffer, userId: string) => {
  return blobStore.put(bytes, {
    size: bytes.length,
    userId,
    timestamp: Date.now(),
  });
};

/**
 * Processing result containing OCR and schema artifacts
 */
export interface ProcessingResult {
  ocrArtifactId: string;
  schemaArtifactId: string;
  qualityScore: number;
}

/**
 * Default schema for invoice processing
 */
const defaultSchema: SchemaDefinition = {
  name: 'invoice',
  fields: {
    invoiceNumber: {
      sourceFields: ['invoice_number', 'invoice_no', 'invoice_id'],
      required: true,
      confidence: 1.0,
    },
    date: {
      sourceFields: ['date', 'invoice_date', 'billing_date'],
      required: true,
      confidence: 1.0,
    },
    total: {
      sourceFields: ['total', 'amount_due', 'total_amount'],
      required: true,
      confidence: 1.0,
    },
  },
};

export type DocumentProcessor = (bytes: Buffer, userId: string, job?: WorkerJob) => Promise<ProcessingResult>;

const isProcessingStage = (value: unknown): value is ProcessingStage =>
  value === 'OCR' || value === 'NORMALIZE' || value === 'TRANSFORM';

const isProcessingError = (error: unknown): error is ProcessingError => {
  if (!error || typeof error !== 'object') {
    return false;
  }
  const candidate = error as ProcessingError;
  return (
    typeof (candidate as ProcessingError).code === 'string' &&
    typeof (candidate as ProcessingError).retryable === 'boolean' &&
    isProcessingStage(candidate.stage)
  );
};

const toProcessingError = (error: unknown, fallbackStage: ProcessingStage): ProcessingError => {
  if (isProcessingError(error)) {
    return error;
  }

  if (error && typeof error === 'object') {
    const candidate = error as { code?: unknown; retryable?: unknown; stage?: unknown };
    if (typeof candidate.code === 'string') {
      const stage = isProcessingStage(candidate.stage) ? candidate.stage : fallbackStage;
      const retryable = typeof candidate.retryable === 'boolean' ? candidate.retryable : false;
      return { code: candidate.code, retryable, stage };
    }
  }

  return { code: 'INTERNAL_ERROR', retryable: false, stage: fallbackStage };
};

/**
 * Default document processor: OCR + schema transformation
 * - Reads schemaId (+ optional version) from job metadata
 * - Fetches schema JSON via provided SchemaProvider
 */
const makeDefaultDocumentProcessor = (schemaProvider: SchemaProvider): DocumentProcessor => async (
  bytes: Buffer,
  userId: string,
  job?: WorkerJob,
): Promise<ProcessingResult> => {
  // Step 1: Run OCR
  const ocrResult = await extractText(bytes);

  if (!isOCRSuccess(ocrResult)) {
    const code = ocrResult.error?.code ?? OCRErrorCode.OCR_FAILURE;
    const retryable = code === OCRErrorCode.TIMEOUT;
    throw { code, retryable, stage: 'OCR' } as ProcessingError;
  }

  // Step 2: Persist OCR text artifact (no plaintext logging)
  const ocrText = ocrResult.pages.map(p => p.text).join('\n');
  const ocrArtifactId = await blobStore.put(
    Buffer.from(JSON.stringify({ pages: ocrResult.pages, totalPages: ocrResult.totalPages })),
    { size: ocrText.length, userId, timestamp: Date.now() }
  );

  // Step 3: Normalize and transform to schema
  const normalizedResult = (() => {
    try {
      return normalizeText(ocrText);
    } catch (_err) {
      throw { code: 'NORMALIZE_FAILED', retryable: false, stage: 'NORMALIZE' } as ProcessingError;
    }
  })();
  const normalizedFields: Record<string, string> = {};

  // Extract simple key-value pairs from normalized text segments
  for (const segment of normalizedResult.segments) {
    if (segment.type === 'line') {
      const parts = segment.text.split(':');
      if (parts.length === 2) {
        const key = parts[0].trim().toLowerCase().replace(/\s+/g, '_');
        const value = parts[1].trim();
        normalizedFields[key] = value;
      }
    }
  }

  // Step 3b: Resolve schema from job metadata via provider
  let effectiveSchema: SchemaDefinition;
  try {
    const schemaId = job?.schemaId;
    const schemaVersion = job?.schemaVersion;

    if (!schemaId || schemaId.trim() === '') {
      throw { code: 'SCHEMA_ID_MISSING', retryable: false, stage: 'TRANSFORM' } as ProcessingError;
    }

    const stored = await schemaProvider.getSchema(schemaId, schemaVersion);
    // Pass schema JSON unchanged to transformer
    effectiveSchema = stored.jsonDefinition as SchemaDefinition;
  } catch (err) {
    if (err instanceof SchemaNotFoundError) {
      throw { code: 'SCHEMA_NOT_FOUND', retryable: false, stage: 'TRANSFORM' } as ProcessingError;
    }
    throw toProcessingError(err, 'TRANSFORM');
  }

  const transformer = new SchemaTransformer(effectiveSchema);
  const transformResult = (() => {
    try {
      return transformer.transform(normalizedFields);
    } catch (_err) {
      throw { code: 'TRANSFORM_ERROR', retryable: false, stage: 'TRANSFORM' } as ProcessingError;
    }
  })();

  // Map deterministic transform outcomes to processing errors
  switch (transformResult.outcome) {
    case 'SUCCESS':
      break;
    case 'MISSING_REQUIRED_FIELD':
      throw { code: 'MISSING_REQUIRED_FIELD', retryable: false, stage: 'TRANSFORM' } as ProcessingError;
    case 'AMBIGUOUS_FIELD':
      throw { code: 'AMBIGUOUS_FIELD', retryable: false, stage: 'TRANSFORM' } as ProcessingError;
    case 'TRANSFORM_ERROR':
    default:
      throw { code: 'TRANSFORM_ERROR', retryable: false, stage: 'TRANSFORM' } as ProcessingError;
  }

  // Step 4: Persist schema output artifact (no plaintext logging)
  const schemaArtifactId = await blobStore.put(
    Buffer.from(JSON.stringify(transformResult.structured)),
    { size: JSON.stringify(transformResult.structured).length, userId, timestamp: Date.now() }
  );

  // Step 5: Calculate quality score
  const qualityReport = TransformValidator.getQualityReport(transformResult);
  const qualityScore = Math.round(qualityReport.avgConfidence * 100) / 100;

  return {
    ocrArtifactId,
    schemaArtifactId,
    qualityScore,
  };
};

export interface CpuWorkerDeps {
  queue: JobQueue;
  fetchBlob?: BlobFetcher;
  processor?: DocumentProcessor;
  schemaProvider: SchemaProvider;
  retryPolicy?: RetryPolicy;
}

export class CpuWorker {
  private readonly queue: JobQueue;
  private readonly fetchBlob: BlobFetcher;
  private readonly processor: DocumentProcessor;
  private readonly retryPolicy: RetryPolicy;
  private readonly schemaProvider: SchemaProvider;

  constructor(deps: CpuWorkerDeps) {
    this.queue = deps.queue;
    this.fetchBlob = deps.fetchBlob ?? defaultBlobFetcher;
    this.schemaProvider = deps.schemaProvider;
    this.processor = deps.processor ?? makeDefaultDocumentProcessor(this.schemaProvider);
    this.retryPolicy = deps.retryPolicy ?? defaultRetryPolicy;
  }

  /**
   * Process a single queued job, if available.
   * Returns the terminal job record or null when no work was found.
   */
  async runOnce(): Promise<WorkerJob | null> {
    const queued = await this.queue.getNextQueued();
    if (!queued) {
      return null;
    }

    const running = await this.queue.markRunning(queued.jobId);
    await transitionJobState(queued.jobId, 'QUEUED', 'RUNNING');

    try {
      const sourceBytes = await this.fetchBlob(running.blobId);
      if (!sourceBytes) {
        throw { code: 'BLOB_NOT_FOUND', retryable: false, stage: 'OCR' } as ProcessingError;
      }

      // Process document: OCR + schema transformation
      const result = await this.processor(sourceBytes, running.userId, running);

      // Update job with success and artifacts (no plaintext in response)
      const succeeded = await this.queue.markSucceeded(
        running.jobId,
        result.ocrArtifactId,
        result.schemaArtifactId,
        result.qualityScore
      );
      await transitionJobState(running.jobId, 'RUNNING', 'SUCCEEDED');
      return succeeded;
    } catch (error) {
      const processingError = toProcessingError(error, 'OCR');
      const decision = this.retryPolicy.decide(running.attempt, processingError);

      const shouldRetry = decision.shouldRetry;

      if (shouldRetry) {
        const nextVisibleAt = new Date(Date.now() + decision.delayMs);
        const retrying = await this.queue.scheduleRetry(running.jobId, nextVisibleAt, processingError);
        await transitionJobState(running.jobId, 'RUNNING', 'RETRYING', {
          code: processingError.code,
          retryable: true,
          stage: processingError.stage,
        });
        return retrying;
      }

      const terminalError: ProcessingError = { ...processingError };
      const failed = await this.queue.markFailed(running.jobId, terminalError);
      await transitionJobState(running.jobId, 'RUNNING', 'FAILED', {
        code: terminalError.code,
        retryable: terminalError.retryable,
        stage: terminalError.stage,
      });
      return failed;
    }
  }

  /**
   * Process up to maxJobs queued jobs without blocking indefinitely.
   */
  async runBatch(maxJobs: number = 1): Promise<WorkerJob[]> {
    const results: WorkerJob[] = [];
    for (let i = 0; i < maxJobs; i += 1) {
      const result = await this.runOnce();
      if (!result) {
        break;
      }
      results.push(result);
    }
    return results;
  }
}

export const inMemoryJobQueue = new InMemoryJobQueue();

/**
 * In-memory SchemaStoreDb implementation suitable for single-process demos/tests.
 * Seeds required schemas at initialization for E2E validation.
 */
class InMemorySchemaStoreDb implements SchemaStoreDb {
  private schemas: Map<string, any[]> = new Map();

  constructor() {
    // Seed invoice schema for E2E validation
    this.seedSchema({
      schema_id: 'invoice',
      version: 'v1',
      name: 'Invoice Schema',
      json_definition: defaultSchema,
      created_at: new Date(),
      deprecated: false,
    });
  }

  private seedSchema(row: any): void {
    const key = `${row.schema_id}:${row.version}`;
    this.schemas.set(key, [row]);
  }

  async query<T = any>(sql: string, params?: any[]): Promise<{ rows: T[] }> {
    // Handle schema lookup queries
    if (sql.includes('SELECT') && sql.includes('FROM schemas')) {
      const schemaId = params?.[0];
      const version = params?.[1];

      if (schemaId && version) {
        // Exact lookup
        const key = `${schemaId}:${version}`;
        const rows = this.schemas.get(key) || [];
        return { rows: rows as T[] };
      } else if (schemaId) {
        // List versions
        const rows: any[] = [];
        for (const [key, schemaRows] of this.schemas) {
          if (key.startsWith(`${schemaId}:`)) {
            rows.push(...schemaRows);
          }
        }
        return { rows: rows as T[] };
      }
    }

    return { rows: [] };
  }
}

const schemaStoreDb = new InMemorySchemaStoreDb();
const schemaStore = new SchemaStore(schemaStoreDb);
export const schemaProvider = new DbSchemaProvider(schemaStore);

export const cpuWorker = new CpuWorker({ queue: inMemoryJobQueue, schemaProvider });
