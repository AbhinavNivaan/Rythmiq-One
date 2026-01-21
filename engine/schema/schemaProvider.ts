import { SchemaStore, StoredSchema } from './schemaStore';

export type Schema = StoredSchema;

export interface SchemaProvider {
  getSchema(schemaId: string, version?: string): Promise<Schema>;
}

export class SchemaNotFoundError extends Error {
  readonly schemaId: string;
  readonly version?: string;

  constructor(schemaId: string, version?: string) {
    super(
      version
        ? `Schema not found for id="${schemaId}" version="${version}"`
        : `Schema not found for id="${schemaId}"`
    );
    this.name = 'SchemaNotFoundError';
    this.schemaId = schemaId;
    this.version = version;
  }
}

export class DbSchemaProvider implements SchemaProvider {
  private cache: Map<string, Schema> = new Map();
  private inflight: Map<string, Promise<Schema>> = new Map();

  constructor(private readonly store: SchemaStore) {}

  async getSchema(schemaId: string, version?: string): Promise<Schema> {
    const cacheKey = this.key(schemaId, version ?? 'latest');

    const cached = this.cache.get(cacheKey);
    if (cached) return cached;

    const inflight = this.inflight.get(cacheKey);
    if (inflight) return inflight;

    const fetchPromise = this.fetchAndCache(schemaId, version, cacheKey);
    this.inflight.set(cacheKey, fetchPromise);
    try {
      const schema = await fetchPromise;
      return schema;
    } finally {
      this.inflight.delete(cacheKey);
    }
  }

  private async fetchAndCache(
    schemaId: string,
    version: string | undefined,
    cacheKey: string
  ): Promise<Schema> {
    const resolvedVersion = await this.resolveVersion(schemaId, version);
    const schema = await this.store.getSchema(schemaId, resolvedVersion);
    if (!schema) {
      throw new SchemaNotFoundError(schemaId, resolvedVersion);
    }
    this.cache.set(cacheKey, schema);
    return schema;
  }

  private async resolveVersion(schemaId: string, version?: string): Promise<string> {
    if (version) return version;

    const versions = await this.store.listVersions(schemaId);
    const latestNonDeprecated = versions.find((v) => !v.deprecated);
    if (!latestNonDeprecated) {
      throw new SchemaNotFoundError(schemaId);
    }
    return latestNonDeprecated.version;
  }

  private key(schemaId: string, version: string): string {
    return `${schemaId}@${version}`;
  }
}
