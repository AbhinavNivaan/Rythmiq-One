export interface StoredSchema {
  schemaId: string;
  version: string;
  name: string;
  jsonDefinition: unknown;
  createdAt: Date;
  deprecated: boolean;
}

export interface NewSchema {
  schemaId: string;
  version: string;
  name: string;
  jsonDefinition: unknown;
  deprecated?: boolean;
}

export interface SchemaStoreDb {
  query<T = any>(sql: string, params?: any[]): Promise<{ rows: T[] }>;
}

type DbSchemaRow = {
  schema_id: string;
  version: string;
  name: string;
  json_definition: unknown;
  created_at: Date | string;
  deprecated: boolean;
};

function mapRow(row: DbSchemaRow): StoredSchema {
  return {
    schemaId: row.schema_id,
    version: row.version,
    name: row.name,
    jsonDefinition: row.json_definition,
    createdAt: row.created_at instanceof Date ? row.created_at : new Date(row.created_at),
    deprecated: row.deprecated,
  };
}

export class SchemaStore {
  constructor(private readonly db: SchemaStoreDb) {}

  async insertSchema(schema: NewSchema): Promise<StoredSchema> {
    const rows = await this.db.query<DbSchemaRow>(
      `
      INSERT INTO schemas (schema_id, version, name, json_definition, deprecated)
      VALUES ($1, $2, $3, $4::jsonb, $5)
      RETURNING schema_id, version, name, json_definition, created_at, deprecated
      `,
      [
        schema.schemaId,
        schema.version,
        schema.name,
        JSON.stringify(schema.jsonDefinition),
        schema.deprecated ?? false,
      ],
    );

    if (rows.rows.length !== 1) {
      throw new Error('Failed to insert schema');
    }

    return mapRow(rows.rows[0]);
  }

  async getSchema(schemaId: string, version: string): Promise<StoredSchema | null> {
    const result = await this.db.query<DbSchemaRow>(
      `
      SELECT schema_id, version, name, json_definition, created_at, deprecated
      FROM schemas
      WHERE schema_id = $1 AND version = $2
      LIMIT 1
      `,
      [schemaId, version],
    );

    return result.rows[0] ? mapRow(result.rows[0]) : null;
  }

  async listVersions(schemaId: string): Promise<StoredSchema[]> {
    const result = await this.db.query<DbSchemaRow>(
      `
      SELECT schema_id, version, name, json_definition, created_at, deprecated
      FROM schemas
      WHERE schema_id = $1
      ORDER BY created_at DESC
      `,
      [schemaId],
    );

    return result.rows.map(mapRow);
  }

  async setDeprecated(schemaId: string, version: string, deprecated: boolean): Promise<void> {
    await this.db.query(
      `
      UPDATE schemas
      SET deprecated = $3
      WHERE schema_id = $1 AND version = $2
      `,
      [schemaId, version, deprecated],
    );
  }
}
