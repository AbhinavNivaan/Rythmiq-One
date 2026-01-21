import { ProcessingError } from './errors';

export interface RetryDecision {
  shouldRetry: boolean;
  delayMs: number;
  reason: string;
  terminal: boolean;
  attempt: number;
}

export interface FailureClassification {
  retryable: boolean;
  reason: string;
  code?: string | number;
}

const DEFAULT_MAX_RETRIES = 3;
const DEFAULT_BASE_DELAY_MS = 500;
const DEFAULT_MAX_DELAY_MS = 30_000;

const asProcessingFailure = (error: unknown): FailureClassification => {
  if (error && typeof error === 'object') {
    const candidate = error as Partial<ProcessingError> & { message?: unknown; code?: unknown };
    const retryable = candidate.retryable === true;
    const code = typeof candidate.code === 'string' || typeof candidate.code === 'number' ? candidate.code : undefined;
    const reason = typeof candidate.message === 'string'
      ? candidate.message
      : code !== undefined
      ? String(code)
      : 'Unknown error';
    return { retryable, reason, code };
  }

  return {
    retryable: false,
    reason: String(error ?? 'Unknown error'),
  };
};

export class RetryPolicy {
  private readonly maxRetries: number;
  private readonly baseDelayMs: number;
  private readonly maxDelayMs: number;

  constructor(options?: { maxRetries?: number; baseDelayMs?: number; maxDelayMs?: number }) {
    this.maxRetries = options?.maxRetries ?? DEFAULT_MAX_RETRIES;
    this.baseDelayMs = options?.baseDelayMs ?? DEFAULT_BASE_DELAY_MS;
    this.maxDelayMs = options?.maxDelayMs ?? DEFAULT_MAX_DELAY_MS;
  }

  classify(error: unknown): FailureClassification {
    return asProcessingFailure(error);
  }

  private computeDelayMs(nextAttemptNumber: number): number {
    const raw = this.baseDelayMs * 2 ** (nextAttemptNumber - 1);
    return Math.min(raw, this.maxDelayMs);
  }

  decide(currentAttempt: number, error: unknown): RetryDecision {
    // currentAttempt is 1-indexed (1 is the first attempt that just failed)
    const classification = this.classify(error);
    const retriesSoFar = currentAttempt - 1;
    const remainingRetries = this.maxRetries - retriesSoFar;

    if (!classification.retryable) {
      return {
        shouldRetry: false,
        delayMs: 0,
        reason: classification.reason,
        terminal: true,
        attempt: currentAttempt,
      };
    }

    if (remainingRetries <= 0) {
      return {
        shouldRetry: false,
        delayMs: 0,
        reason: `Retry limit reached (${this.maxRetries}) after attempt ${currentAttempt}: ${classification.reason}`,
        terminal: true,
        attempt: currentAttempt,
      };
    }

    const delayMs = this.computeDelayMs(currentAttempt);
    return {
      shouldRetry: true,
      delayMs,
      reason: classification.reason,
      terminal: false,
      attempt: currentAttempt,
    };
  }
}

export const defaultRetryPolicy = new RetryPolicy();
