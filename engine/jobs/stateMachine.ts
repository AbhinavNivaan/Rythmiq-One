export type JobState =
  | 'CREATED'
  | 'QUEUED'
  | 'RUNNING'
  | 'RETRYING'
  | 'SUCCEEDED'
  | 'FAILED';

export const terminalStates: ReadonlySet<JobState> = new Set(['SUCCEEDED', 'FAILED']);

const allowedTransitions: Record<JobState, ReadonlyArray<JobState>> = {
  CREATED: ['QUEUED'],
  QUEUED: ['RUNNING', 'FAILED'],
  RUNNING: ['SUCCEEDED', 'FAILED', 'RETRYING'],
  RETRYING: ['QUEUED'],
  SUCCEEDED: [],
  FAILED: [],
};

export class JobStateMachine {
  canTransition(from: JobState, to: JobState): boolean {
    return allowedTransitions[from]?.includes(to) ?? false;
  }

  assertTransition(from: JobState, to: JobState): void {
    if (terminalStates.has(from)) {
      throw new Error(`Cannot transition terminal job state ${from}`);
    }
    if (!this.canTransition(from, to)) {
      throw new Error(`Invalid job state transition: ${from} -> ${to}`);
    }
  }

  isTerminal(state: JobState): boolean {
    return terminalStates.has(state);
  }
}

export const jobStateMachine = new JobStateMachine();
