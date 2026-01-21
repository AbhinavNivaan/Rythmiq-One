export interface Config {
  executionBackend: 'local' | 'camber' | 'do' | 'heroku';
  databaseUrl: string;
  artifactStore: {
    type: 's3' | 'local';
    bucket?: string;
    path?: string;
  };
  jwtPublicKey: string;
  serviceEnv: 'dev' | 'staging' | 'prod';
}

class ConfigProvider {
  private config: Config | null = null;

  load(): Config {
    if (this.config) {
      return this.config;
    }

    const executionBackend = this.getEnv('EXECUTION_BACKEND', 'local') as 'local' | 'camber' | 'do' | 'heroku';
    const databaseUrl = this.getEnv('DATABASE_URL', process.env.SUPABASE_URL);
    const jwtPublicKey = this.getEnv('JWT_PUBLIC_KEY');
    const serviceEnv = this.getEnv('SERVICE_ENV', 'dev') as 'dev' | 'staging' | 'prod';

    const artifactStoreType = this.getEnv('ARTIFACT_STORE_TYPE', 'local') as 's3' | 'local';
    const artifactStore = this.buildArtifactStore(artifactStoreType);

    this.validateExecutionBackend(executionBackend);
    this.validateServiceEnv(serviceEnv);

    this.config = {
      executionBackend,
      databaseUrl,
      artifactStore,
      jwtPublicKey,
      serviceEnv,
    };

    return this.config;
  }

  private getEnv(key: string, defaultValue?: string): string {
    const value = process.env[key];
    if (!value && !defaultValue) {
      throw new Error(`Missing required environment variable: ${key}`);
    }
    return value || defaultValue || '';
  }

  private buildArtifactStore(type: 's3' | 'local') {
    if (type === 's3') {
      const bucket = process.env.ARTIFACT_STORE_BUCKET || process.env.SPACES_BUCKET;
      if (!bucket) {
        throw new Error('ARTIFACT_STORE_BUCKET required when ARTIFACT_STORE_TYPE=s3');
      }
      return { type: 's3' as const, bucket };
    }

    const path = process.env.ARTIFACT_STORE_PATH || './artifacts';
    return { type: 'local' as const, path };
  }

  private validateExecutionBackend(backend: string) {
    const valid = ['local', 'camber', 'do', 'heroku'];
    if (!valid.includes(backend)) {
      throw new Error(
        `Invalid EXECUTION_BACKEND: "${backend}". Supported: local, camber, do, heroku`,
      );
    }
  }

  private validateServiceEnv(env: string) {
    const valid = ['dev', 'staging', 'prod'];
    if (!valid.includes(env)) {
      throw new Error(
        `Invalid SERVICE_ENV: "${env}". Supported: dev, staging, prod`,
      );
    }
  }
}

export const configProvider = new ConfigProvider();

export function getConfig(): Config {
  return configProvider.load();
}
