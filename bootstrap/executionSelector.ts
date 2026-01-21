import { ExecutionBackend } from '../engine/execution/executionBackend';
import { LocalExecutionBackend, LocalExecutionBackendDeps } from '../engine/execution/executionBackend';
import { CamberExecutionBackend, CamberExecutionBackendDeps } from '../engine/execution/camberBackend';
import { DigitalOceanExecutionBackend, DigitalOceanExecutionBackendDeps } from '../engine/execution/digitalOceanBackend';
import { HerokuExecutionBackend, HerokuExecutionBackendDeps } from '../engine/execution/herokuBackend';

/**
 * Supported execution backend types.
 */
export type ExecutionBackendType = 'local' | 'camber' | 'do' | 'heroku';

/**
 * Dependencies for initializing the execution backend selector.
 * This should contain any resources needed by local execution (e.g., CpuWorker).
 */
export interface ExecutionSelectorDeps {
  localDeps?: LocalExecutionBackendDeps;
  camberDeps?: CamberExecutionBackendDeps;
  doDeps?: DigitalOceanExecutionBackendDeps;
  herokuDeps?: HerokuExecutionBackendDeps;
}

/**
 * Selects and instantiates the appropriate ExecutionBackend based on
 * the EXECUTION_BACKEND environment variable.
 *
 * Environment variable: EXECUTION_BACKEND
 * Supported values: local | camber | do | heroku
 * Default: local
 *
 * @param deps Dependencies needed by the selected backend
 * @returns Instantiated ExecutionBackend
 * @throws Error if invalid backend type is specified or required dependencies are missing
 */
export function selectExecutionBackend(deps: ExecutionSelectorDeps = {}): ExecutionBackend {
  const backendType = (process.env.EXECUTION_BACKEND || 'local').toLowerCase().trim() as ExecutionBackendType;

  switch (backendType) {
    case 'local':
      return createLocalBackend(deps);

    case 'camber':
      return createCamberBackend(deps);

    case 'do':
      return createDigitalOceanBackend(deps);

    case 'heroku':
      return createHerokuBackend(deps);

    default:
      throw new Error(
        `Invalid EXECUTION_BACKEND: "${backendType}". ` +
        `Supported values: local, camber, do, heroku. Defaulting to local if unset.`,
      );
  }
}

/**
 * Creates a LocalExecutionBackend.
 * Requires localDeps with a CpuWorker instance.
 */
function createLocalBackend(deps: ExecutionSelectorDeps): LocalExecutionBackend {
  if (!deps.localDeps || !deps.localDeps.worker) {
    throw new Error('LocalExecutionBackend requires localDeps.worker (CpuWorker instance)');
  }
  return new LocalExecutionBackend(deps.localDeps);
}

/**
 * Creates a CamberExecutionBackend.
 * Uses environment variables for Camber configuration if not provided in deps.
 */
function createCamberBackend(deps: ExecutionSelectorDeps): CamberExecutionBackend {
  return new CamberExecutionBackend(deps.camberDeps || {});
}

/**
 * Creates a DigitalOceanExecutionBackend.
 * Uses environment variables for DO configuration if not provided in deps.
 */
function createDigitalOceanBackend(deps: ExecutionSelectorDeps): DigitalOceanExecutionBackend {
  return new DigitalOceanExecutionBackend(deps.doDeps || {});
}

/**
 * Creates a HerokuExecutionBackend.
 * Uses environment variables for Heroku configuration if not provided in deps.
 */
function createHerokuBackend(deps: ExecutionSelectorDeps): HerokuExecutionBackend {
  return new HerokuExecutionBackend(deps.herokuDeps || {});
}

/**
 * Convenience function to get the selected backend type for logging/diagnostics.
 */
export function getSelectedBackendType(): ExecutionBackendType {
  return (process.env.EXECUTION_BACKEND || 'local').toLowerCase().trim() as ExecutionBackendType;
}
