-- ============================================================================
-- Rythmiq One — Phase 2A Database Schema Migration
-- Generated: 2026-01-26
-- Target: Supabase (PostgreSQL 15+)
-- ============================================================================

-- Enable UUID extension (Supabase typically has this enabled)
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================================
-- TABLE: portal_schemas
-- Purpose: Stores portal transformation rules as data. Versioned, code-free config.
-- ============================================================================

CREATE TABLE portal_schemas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0),
    schema_definition JSONB NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    
    CONSTRAINT uq_portal_schemas_name_version UNIQUE (name, version)
);

COMMENT ON TABLE portal_schemas IS 'Portal transformation rules. One active version per portal name.';

-- ============================================================================
-- TABLE: jobs
-- Purpose: Unit of async execution. Tracks document processing lifecycle.
-- ============================================================================

CREATE TABLE jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    portal_schema_version_id UUID REFERENCES portal_schemas(id) ON DELETE RESTRICT,
    input_metadata JSONB NOT NULL DEFAULT '{}',
    error_details JSONB,
    page_count INTEGER CHECK (page_count > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    
    -- Job state safety: completed_at only valid for terminal states
    CONSTRAINT chk_jobs_completed_at_state CHECK (
        (completed_at IS NULL AND status IN ('pending', 'processing'))
        OR (completed_at IS NOT NULL AND status IN ('completed', 'failed'))
    )
);

COMMENT ON TABLE jobs IS 'Unit of async execution. One job per document processing request.';
COMMENT ON COLUMN jobs.input_metadata IS 'Structure: {original_filename, mime_type, file_size_bytes, storage_path, upload_source}';
COMMENT ON COLUMN jobs.error_details IS 'Structure: {code, message, stage, retryable, timestamp}';

-- ============================================================================
-- TABLE: documents
-- Purpose: Canonical master document + portal-specific transformations.
-- ============================================================================

CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL UNIQUE REFERENCES jobs(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    canonical_output JSONB NOT NULL,
    portal_outputs JSONB NOT NULL DEFAULT '{}',
    ocr_text_hash TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE documents IS 'Canonical OCR output + portal transformations. 1:1 with completed jobs.';
COMMENT ON COLUMN documents.canonical_output IS 'Structure: {version, extracted_at, fields, raw_text_preview, page_extractions}. WARNING: Contains PII (patient names, DOB, etc). Ephemeral data subject to retention policy. Handle per data protection requirements.';
COMMENT ON COLUMN documents.portal_outputs IS 'Structure: {portal_name: {schema_version_id, transformed_at, payload}}';
COMMENT ON COLUMN documents.ocr_text_hash IS 'SHA-256 of raw OCR text. PII indicator without storing raw.';

-- ============================================================================
-- TABLE: user_credits
-- Purpose: Credit balance per user. Single source of truth for billing.
-- ============================================================================

CREATE TABLE user_credits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL UNIQUE REFERENCES auth.users(id) ON DELETE CASCADE,
    balance NUMERIC(12, 4) NOT NULL DEFAULT 0 CHECK (balance >= 0),
    lifetime_purchased NUMERIC(12, 4) NOT NULL DEFAULT 0,
    lifetime_consumed NUMERIC(12, 4) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE user_credits IS 'User credit balance. Invariant: balance = lifetime_purchased - lifetime_consumed';

-- ============================================================================
-- TABLE: cpu_usage
-- Purpose: CPU consumption per job stage. Append-only for billing audit.
-- ============================================================================

CREATE TABLE cpu_usage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    stage TEXT NOT NULL CHECK (stage IN ('ocr', 'transform', 'delivery')),
    cpu_milliseconds INTEGER NOT NULL CHECK (cpu_milliseconds >= 0),
    cost_credits NUMERIC(10, 6) NOT NULL CHECK (cost_credits >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE cpu_usage IS 'CPU consumption per job stage. Append-only for billing.';

-- ============================================================================
-- TABLE: metrics
-- Purpose: Operational observability. Ephemeral (90-day retention target).
-- ============================================================================

CREATE TABLE metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID REFERENCES jobs(id) ON DELETE SET NULL,
    metric_type TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    metric_value JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE metrics IS 'Operational metrics. Ephemeral data, 90-day retention target.';
COMMENT ON COLUMN metrics.metric_value IS 'Structure: {value, unit, dimensions}';

-- ============================================================================
-- INDEXES: Foreign Keys
-- Required for efficient CASCADE deletes and RLS filtering
-- ============================================================================

-- jobs: Filter by user for dashboard, RLS
CREATE INDEX idx_jobs_user_id ON jobs(user_id);

-- documents: RLS filtering, user document list
CREATE INDEX idx_documents_user_id ON documents(user_id);

-- cpu_usage: Cost aggregation per job
CREATE INDEX idx_cpu_usage_job_id ON cpu_usage(job_id);

-- cpu_usage: User billing summaries
CREATE INDEX idx_cpu_usage_user_id ON cpu_usage(user_id);

-- ============================================================================
-- INDEXES: Query Optimization
-- ============================================================================

-- HOT PATH: Dashboard queries - filter jobs by user and status
-- Used for: "Show me my pending jobs", "Show me completed jobs"
CREATE INDEX idx_jobs_user_status ON jobs(user_id, status);

-- HOT PATH: Job polling with ordering - user dashboard with status filter, newest first
-- Used for: Paginated job list sorted by creation time within status
CREATE INDEX idx_jobs_user_status_created ON jobs(user_id, status, created_at DESC);

-- Worker job pickup: Find pending jobs ordered by creation time
-- Used for: Backend worker polling for jobs to process
CREATE INDEX idx_jobs_status_created ON jobs(status, created_at);

-- Recent jobs list: User's jobs sorted by newest first
-- Used for: Dashboard default view, job history
CREATE INDEX idx_jobs_user_created_desc ON jobs(user_id, created_at DESC);

-- Active portal schema lookup: Find current active version per portal
-- Partial index only includes active schemas for efficiency
CREATE INDEX idx_portal_schemas_name_active ON portal_schemas(name) WHERE is_active = true;

-- Portal version lookup: Get latest version per portal name
-- Used for: Schema management UI, version history
CREATE INDEX idx_portal_schemas_name_version ON portal_schemas(name, version DESC);

-- Billing aggregation: Sum CPU usage per user within date range
-- Used for: Monthly billing calculations, usage reports
CREATE INDEX idx_cpu_usage_user_created ON cpu_usage(user_id, created_at);

-- Metrics dashboard: Query metrics by type within time range
-- Used for: Observability dashboards, alerting
CREATE INDEX idx_metrics_type_created ON metrics(metric_type, created_at);

-- Metrics aggregation: Query metrics by name with timestamp ordering
-- Used for: Aggregating specific metrics (e.g., "ocr_latency") over time periods
CREATE INDEX idx_metrics_name_created ON metrics(metric_name, created_at DESC);

-- Job observability: Get all metrics for a specific job
-- Used for: Job detail debugging, per-job diagnostics
CREATE INDEX idx_metrics_job_id ON metrics(job_id);

-- Metrics pruning: Efficiently delete old metrics by date
-- Used for: Retention policy enforcement (90-day cleanup)
CREATE INDEX idx_metrics_created_at ON metrics(created_at);

-- ============================================================================
-- ROW LEVEL SECURITY: Enable on all tables
-- ============================================================================

ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE portal_schemas ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_credits ENABLE ROW LEVEL SECURITY;
ALTER TABLE cpu_usage ENABLE ROW LEVEL SECURITY;
ALTER TABLE metrics ENABLE ROW LEVEL SECURITY;

-- Force RLS for table owners (defense in depth)
ALTER TABLE jobs FORCE ROW LEVEL SECURITY;
ALTER TABLE documents FORCE ROW LEVEL SECURITY;
ALTER TABLE portal_schemas FORCE ROW LEVEL SECURITY;
ALTER TABLE user_credits FORCE ROW LEVEL SECURITY;
ALTER TABLE cpu_usage FORCE ROW LEVEL SECURITY;
ALTER TABLE metrics FORCE ROW LEVEL SECURITY;

-- ============================================================================
-- RLS POLICIES: jobs
-- Users can only access their own jobs
-- ============================================================================

CREATE POLICY "users_select_own_jobs" ON jobs
    FOR SELECT
    TO authenticated
    USING (user_id = auth.uid());

CREATE POLICY "users_insert_own_jobs" ON jobs
    FOR INSERT
    TO authenticated
    WITH CHECK (user_id = auth.uid());

CREATE POLICY "users_update_own_jobs" ON jobs
    FOR UPDATE
    TO authenticated
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());

CREATE POLICY "users_delete_own_jobs" ON jobs
    FOR DELETE
    TO authenticated
    USING (user_id = auth.uid());

-- ============================================================================
-- RLS POLICIES: documents
-- Users can only access their own documents
-- ============================================================================

CREATE POLICY "users_select_own_documents" ON documents
    FOR SELECT
    TO authenticated
    USING (user_id = auth.uid());

CREATE POLICY "users_insert_own_documents" ON documents
    FOR INSERT
    TO authenticated
    WITH CHECK (user_id = auth.uid());

CREATE POLICY "users_update_own_documents" ON documents
    FOR UPDATE
    TO authenticated
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());

CREATE POLICY "users_delete_own_documents" ON documents
    FOR DELETE
    TO authenticated
    USING (user_id = auth.uid());

-- ============================================================================
-- RLS POLICIES: portal_schemas
-- All authenticated users can read; no direct user writes
-- ============================================================================

CREATE POLICY "authenticated_read_portal_schemas" ON portal_schemas
    FOR SELECT
    TO authenticated
    USING (true);

-- No INSERT/UPDATE/DELETE policies for authenticated users
-- Only service_role can modify portal_schemas

-- ============================================================================
-- RLS POLICIES: user_credits
-- Users can read own credits; no direct user writes (backend only)
-- ============================================================================

CREATE POLICY "users_select_own_credits" ON user_credits
    FOR SELECT
    TO authenticated
    USING (user_id = auth.uid());

-- No INSERT/UPDATE/DELETE policies for authenticated users
-- Only service_role can modify user_credits

-- ============================================================================
-- RLS POLICIES: cpu_usage
-- Users can read own usage; no direct user writes (backend only)
-- ============================================================================

CREATE POLICY "users_select_own_cpu_usage" ON cpu_usage
    FOR SELECT
    TO authenticated
    USING (user_id = auth.uid());

-- No INSERT/UPDATE/DELETE policies for authenticated users
-- Only service_role can modify cpu_usage

-- ============================================================================
-- RLS POLICIES: metrics
-- No user access; backend/service_role only
-- ============================================================================

-- No policies for authenticated users
-- Only service_role can read/write metrics

-- ============================================================================
-- SEED DATA: Portal Schemas
-- 5 realistic portal configurations
-- ============================================================================

INSERT INTO portal_schemas (name, version, schema_definition, is_active, created_at) VALUES

-- NEET 2026: Medical entrance exam photo requirements
('NEET 2026', 1, '{
    "target_format": "json",
    "requirements": {
        "dimensions": {"width_px": 200, "height_px": 230},
        "aspect_ratio": "35:40",
        "dpi": 200,
        "max_file_size_kb": 100,
        "min_file_size_kb": 10,
        "allowed_formats": ["jpg", "jpeg"],
        "background_color": "white",
        "face_coverage_percent": {"min": 50, "max": 75}
    },
    "field_mappings": [
        {"source_path": "$.fields.candidate_name.value", "target_path": "CandidateName", "transform": "uppercase", "required": true},
        {"source_path": "$.fields.date_of_birth.value", "target_path": "DOB", "transform": "date_ddmmyyyy", "required": true},
        {"source_path": "$.fields.category.value", "target_path": "Category", "transform": null, "required": true},
        {"source_path": "$.fields.state_code.value", "target_path": "StateCode", "transform": "uppercase", "required": true}
    ],
    "validation_rules": [
        {"field": "CandidateName", "rule": "regex", "params": {"pattern": "^[A-Z\\s]{2,100}$"}},
        {"field": "DOB", "rule": "regex", "params": {"pattern": "^\\d{2}/\\d{2}/\\d{4}$"}},
        {"field": "Category", "rule": "enum", "params": {"values": ["GENERAL", "OBC", "SC", "ST", "EWS"]}}
    ]
}', true, now()),

-- JEE Main 2026: Engineering entrance exam photo requirements
('JEE Main 2026', 1, '{
    "target_format": "json",
    "requirements": {
        "dimensions": {"width_px": 150, "height_px": 200},
        "aspect_ratio": "3:4",
        "dpi": 200,
        "max_file_size_kb": 80,
        "min_file_size_kb": 10,
        "allowed_formats": ["jpg", "jpeg"],
        "background_color": "white",
        "face_coverage_percent": {"min": 50, "max": 75}
    },
    "field_mappings": [
        {"source_path": "$.fields.candidate_name.value", "target_path": "Name", "transform": "uppercase", "required": true},
        {"source_path": "$.fields.application_number.value", "target_path": "ApplicationNo", "transform": null, "required": true},
        {"source_path": "$.fields.date_of_birth.value", "target_path": "DateOfBirth", "transform": "date_ddmmyyyy", "required": true},
        {"source_path": "$.fields.father_name.value", "target_path": "FatherName", "transform": "uppercase", "required": true},
        {"source_path": "$.fields.exam_center.value", "target_path": "ExamCenter", "transform": null, "required": false}
    ],
    "validation_rules": [
        {"field": "Name", "rule": "regex", "params": {"pattern": "^[A-Z\\s]{2,100}$"}},
        {"field": "ApplicationNo", "rule": "regex", "params": {"pattern": "^[0-9]{12}$"}},
        {"field": "DateOfBirth", "rule": "regex", "params": {"pattern": "^\\d{2}/\\d{2}/\\d{4}$"}}
    ]
}', true, now()),

-- Aadhaar Update: UIDAI photo requirements
('Aadhaar Update', 1, '{
    "target_format": "json",
    "requirements": {
        "dimensions": {"width_px": 350, "height_px": 450},
        "aspect_ratio": "35:45",
        "dpi": 300,
        "max_file_size_kb": 200,
        "min_file_size_kb": 20,
        "allowed_formats": ["jpg", "jpeg", "png"],
        "background_color": "white",
        "face_coverage_percent": {"min": 60, "max": 80}
    },
    "field_mappings": [
        {"source_path": "$.fields.full_name.value", "target_path": "ResidentName", "transform": "titlecase", "required": true},
        {"source_path": "$.fields.aadhaar_number.value", "target_path": "UID", "transform": "mask_aadhaar", "required": true},
        {"source_path": "$.fields.address.value", "target_path": "Address", "transform": null, "required": true},
        {"source_path": "$.fields.date_of_birth.value", "target_path": "DOB", "transform": "date_ddmmyyyy", "required": true},
        {"source_path": "$.fields.gender.value", "target_path": "Gender", "transform": "uppercase", "required": true}
    ],
    "validation_rules": [
        {"field": "UID", "rule": "regex", "params": {"pattern": "^XXXX-XXXX-\\d{4}$"}},
        {"field": "Gender", "rule": "enum", "params": {"values": ["MALE", "FEMALE", "OTHER"]}},
        {"field": "DOB", "rule": "regex", "params": {"pattern": "^\\d{2}/\\d{2}/\\d{4}$"}}
    ]
}', true, now()),

-- Passport India: MEA passport photo requirements
('Passport India', 1, '{
    "target_format": "json",
    "requirements": {
        "dimensions": {"width_px": 413, "height_px": 531},
        "aspect_ratio": "35:45",
        "dpi": 300,
        "max_file_size_kb": 300,
        "min_file_size_kb": 20,
        "allowed_formats": ["jpg", "jpeg"],
        "background_color": "white",
        "face_coverage_percent": {"min": 70, "max": 80}
    },
    "field_mappings": [
        {"source_path": "$.fields.surname.value", "target_path": "Surname", "transform": "uppercase", "required": true},
        {"source_path": "$.fields.given_name.value", "target_path": "GivenName", "transform": "uppercase", "required": true},
        {"source_path": "$.fields.date_of_birth.value", "target_path": "DateOfBirth", "transform": "date_ddmmyyyy", "required": true},
        {"source_path": "$.fields.place_of_birth.value", "target_path": "PlaceOfBirth", "transform": "uppercase", "required": true},
        {"source_path": "$.fields.nationality.value", "target_path": "Nationality", "transform": null, "required": true, "default_value": "INDIAN"},
        {"source_path": "$.fields.passport_number.value", "target_path": "PassportNo", "transform": "uppercase", "required": false}
    ],
    "validation_rules": [
        {"field": "Surname", "rule": "regex", "params": {"pattern": "^[A-Z\\s]{1,50}$"}},
        {"field": "GivenName", "rule": "regex", "params": {"pattern": "^[A-Z\\s]{1,50}$"}},
        {"field": "DateOfBirth", "rule": "regex", "params": {"pattern": "^\\d{2}/\\d{2}/\\d{4}$"}},
        {"field": "PassportNo", "rule": "regex", "params": {"pattern": "^[A-Z][0-9]{7}$"}}
    ]
}', true, now()),

-- College Generic: Generic academic document requirements
('College Generic', 1, '{
    "target_format": "json",
    "requirements": {
        "dimensions": {"width_px": 150, "height_px": 200},
        "aspect_ratio": "3:4",
        "dpi": 150,
        "max_file_size_kb": 50,
        "min_file_size_kb": 5,
        "allowed_formats": ["jpg", "jpeg", "png"],
        "background_color": "any",
        "face_coverage_percent": {"min": 40, "max": 80}
    },
    "field_mappings": [
        {"source_path": "$.fields.student_name.value", "target_path": "StudentName", "transform": "titlecase", "required": true},
        {"source_path": "$.fields.enrollment_number.value", "target_path": "EnrollmentNo", "transform": "uppercase", "required": true},
        {"source_path": "$.fields.course.value", "target_path": "Course", "transform": null, "required": true},
        {"source_path": "$.fields.batch_year.value", "target_path": "BatchYear", "transform": null, "required": true},
        {"source_path": "$.fields.department.value", "target_path": "Department", "transform": null, "required": false}
    ],
    "validation_rules": [
        {"field": "StudentName", "rule": "regex", "params": {"pattern": "^[A-Za-z\\s]{2,100}$"}},
        {"field": "EnrollmentNo", "rule": "regex", "params": {"pattern": "^[A-Z0-9]{6,20}$"}},
        {"field": "BatchYear", "rule": "range", "params": {"min": 2000, "max": 2030}}
    ]
}', true, now());

-- ============================================================================
-- END OF MIGRATION
-- ============================================================================
