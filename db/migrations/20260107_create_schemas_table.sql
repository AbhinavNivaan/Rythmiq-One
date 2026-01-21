CREATE TABLE IF NOT EXISTS schemas (
  schema_id TEXT NOT NULL,
  version TEXT NOT NULL,
  name TEXT NOT NULL,
  json_definition JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  deprecated BOOLEAN NOT NULL DEFAULT false,
  PRIMARY KEY (schema_id, version)
);

CREATE INDEX IF NOT EXISTS idx_schemas_schema_id_version ON schemas (schema_id, version);

CREATE OR REPLACE FUNCTION schemas_immutable_except_deprecated() RETURNS trigger AS $$
BEGIN
  IF NEW.schema_id IS DISTINCT FROM OLD.schema_id
     OR NEW.version IS DISTINCT FROM OLD.version
     OR NEW.name IS DISTINCT FROM OLD.name
     OR NEW.json_definition IS DISTINCT FROM OLD.json_definition
     OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
    RAISE EXCEPTION 'schemas rows are immutable except deprecated';
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_schemas_immutable_except_deprecated ON schemas;
CREATE TRIGGER trg_schemas_immutable_except_deprecated
BEFORE UPDATE ON schemas
FOR EACH ROW
EXECUTE FUNCTION schemas_immutable_except_deprecated();
