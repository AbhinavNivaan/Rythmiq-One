type JobEvent = 'job_created' | 'job_started' | 'job_succeeded' | 'job_failed';

type JobMetric = 'jobs_created' | 'jobs_succeeded' | 'jobs_failed';

type MetricsSnapshot = Record<JobMetric, number>;

const metrics: MetricsSnapshot = {
  jobs_created: 0,
  jobs_succeeded: 0,
  jobs_failed: 0,
};

const recordedJobCreations = new Set<string>();

function logEvent(event: JobEvent, jobId: string): void {
  console.info({
    event,
    jobId,
    timestamp: new Date().toISOString(),
  });
}

function increment(metric: JobMetric): void {
  metrics[metric] += 1;
}

export function logJobCreated(jobId: string): void {
  if (!recordedJobCreations.has(jobId)) {
    recordedJobCreations.add(jobId);
    increment('jobs_created');
  }
  logEvent('job_created', jobId);
}

export function logJobStarted(jobId: string): void {
  logEvent('job_started', jobId);
}

export function logJobSucceeded(jobId: string): void {
  increment('jobs_succeeded');
  logEvent('job_succeeded', jobId);
}

export function logJobFailed(jobId: string): void {
  increment('jobs_failed');
  logEvent('job_failed', jobId);
}

export function getJobMetrics(): MetricsSnapshot {
  return { ...metrics };
}
