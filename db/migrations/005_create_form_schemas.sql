-- =============================================================================
-- Migration 005: Create form_schemas table
-- =============================================================================
-- Purpose: Store complete registration/application form schemas (field definitions,
--          document upload specs, fee structures, key dates) for exam forms,
--          recruitment forms, and government ID applications.
--
-- Separate from portal_schemas (which stores image-processing specs).
-- Managed via scripts/inject_schema.py — do not insert rows manually.
--
-- Run in Supabase SQL Editor.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Table
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.form_schemas (

    -- Human-readable primary key slug, e.g. "neet_2026_registration".
    -- Pattern enforced: snake_case, 3-80 chars, starts with a letter.
    -- Must match the file name (without .json) and the schema_id field in the JSON body.
    id TEXT PRIMARY KEY
        CONSTRAINT form_schemas_id_format
        CHECK (id ~ '^[a-z][a-z0-9_]{2,79}$'),

    -- Controls which sections are required. See schemas/spec/SCHEMA_SPEC.md.
    schema_type TEXT NOT NULL
        CONSTRAINT form_schemas_type_values
        CHECK (schema_type IN ('exam_form', 'recruitment', 'government_id')),

    -- Semantic version stored as a column for queryability (e.g. "1.0.0").
    schema_version TEXT NOT NULL DEFAULT '1.0.0'
        CONSTRAINT form_schemas_version_format
        CHECK (schema_version ~ '^\d+\.\d+\.\d+$'),

    -- Denormalized from body.metadata for efficient list queries.
    -- These must always match the corresponding values inside body.
    display_name    TEXT NOT NULL,
    short_name      TEXT NOT NULL,
    category        TEXT NOT NULL,
    conducting_body TEXT,
    applicable_year INTEGER
        CONSTRAINT form_schemas_year_range
        CHECK (applicable_year IS NULL OR (applicable_year BETWEEN 2000 AND 2100)),

    -- Full validated schema payload (see schemas/spec/SCHEMA_SPEC.md for structure).
    body JSONB NOT NULL,

    -- Lifecycle
    is_active  BOOLEAN     NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Allows multiple version rows per schema_id (old versions kept as is_active=false).
    -- Only one row per (id, schema_version) pair is permitted.
    CONSTRAINT uq_form_schemas_id_version UNIQUE (id, schema_version)
);

COMMENT ON TABLE public.form_schemas IS
    'Complete exam/recruitment/government form schemas. '
    'Separate from portal_schemas (image processing rules). '
    'Managed via scripts/inject_schema.py.';

COMMENT ON COLUMN public.form_schemas.id IS
    'Human-readable slug PK. Convention: {exam_or_org}_{year}_{type}. '
    'Must match the filename in schemas/ and the schema_id field in body.';

COMMENT ON COLUMN public.form_schemas.body IS
    'Full validated schema JSON. Structure varies by schema_type but always contains: '
    'metadata, form_sections[], document_uploads[], fee_structure. '
    'See schemas/spec/SCHEMA_SPEC.md.';

COMMENT ON COLUMN public.form_schemas.is_active IS
    'Only one version per schema_id should be is_active=true at any time. '
    'Old versions are retained with is_active=false for audit history.';

-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------

-- Hot path: list active schemas by type (mobile app schema browser)
CREATE INDEX IF NOT EXISTS idx_form_schemas_type_active
    ON public.form_schemas (schema_type, is_active)
    WHERE is_active = true;

-- Hot path: filter by year (users typically want current year only)
CREATE INDEX IF NOT EXISTS idx_form_schemas_year_active
    ON public.form_schemas (applicable_year, is_active)
    WHERE is_active = true;

-- Category filter (e.g. medical_entrance vs engineering_entrance)
CREATE INDEX IF NOT EXISTS idx_form_schemas_category_active
    ON public.form_schemas (category, is_active)
    WHERE is_active = true;

-- GIN index for JSONB search inside body (admin tooling, not mobile hot path)
CREATE INDEX IF NOT EXISTS idx_form_schemas_body_gin
    ON public.form_schemas USING gin (body jsonb_path_ops);

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------
ALTER TABLE public.form_schemas ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.form_schemas FORCE ROW LEVEL SECURITY;

-- Authenticated users (and anonymous) can read active schemas.
-- Mirrors the access model of portal_schemas.
CREATE POLICY "read_active_form_schemas"
    ON public.form_schemas
    FOR SELECT
    TO anon, authenticated
    USING (is_active = true);

-- service_role bypasses RLS in Supabase by default — no explicit write policy needed.
-- inject_schema.py uses SUPABASE_SERVICE_ROLE_KEY for all write operations.

GRANT SELECT ON public.form_schemas TO anon, authenticated;
GRANT ALL    ON public.form_schemas TO service_role;

-- ---------------------------------------------------------------------------
-- Auto-update trigger (reuses the function defined in db/schema.sql)
-- ---------------------------------------------------------------------------
CREATE TRIGGER update_form_schemas_updated_at
    BEFORE UPDATE ON public.form_schemas
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ---------------------------------------------------------------------------
-- Verification queries (run after applying this migration)
-- ---------------------------------------------------------------------------
-- SELECT id, schema_type, display_name, applicable_year
--   FROM public.form_schemas;
-- -- Expected: 0 rows (empty table, ready for injection)
--
-- SELECT tablename, rowsecurity
--   FROM pg_tables
--  WHERE tablename = 'form_schemas';
-- -- Expected: rowsecurity = true
