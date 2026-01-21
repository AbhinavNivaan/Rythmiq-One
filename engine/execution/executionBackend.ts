import { CpuWorker } from '../cpu/worker';

export interface ExecutionBackend {
  runJob(jobId: string): Promise<void>;
}

export interface LocalExecutionBackendDeps {
  worker: CpuWorker;
}

export class LocalExecutionBackend implements ExecutionBackend {
  private readonly worker: CpuWorker;

  constructor(deps: LocalExecutionBackendDeps) {
    this.worker = deps.worker;
  }

  async runJob(jobId: string): Promise<void> {
    await this.worker.runOnce();
  }
}
