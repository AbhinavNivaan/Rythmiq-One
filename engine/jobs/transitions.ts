import { JobState } from './stateMachine';
import { ProcessingError } from './errors';

export type JobErrorDetails = Pick<ProcessingError, 'code' | 'retryable' | 'stage'>;

export type JobStateTransitionHandler = (
  jobId: string,
  from: JobState,
  to: JobState,
  error?: JobErrorDetails,
) => Promise<void>;

let handler: JobStateTransitionHandler | null = null;

export const registerJobStateTransitionHandler = (fn: JobStateTransitionHandler): void => {
  handler = fn;
};

export const transitionJobState = async (
  jobId: string,
  from: JobState,
  to: JobState,
  error?: JobErrorDetails,
): Promise<void> => {
  if (!handler) {
    // In worker context, transitions are handled via DB updates directly.
    // We can safely ignore this or log a warning.
    return;
  }

  await handler(jobId, from, to, error);
};
