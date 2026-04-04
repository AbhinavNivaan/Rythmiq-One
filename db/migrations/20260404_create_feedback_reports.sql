-- =============================================================================
-- Migration: Create feedback_reports table
-- =============================================================================
-- Stores bad-output reports from users. job_id is nullable so reports survive
-- if the parent job is later deleted. unique index on job_id enforces one report
-- per job and prevents duplicate Slack alerts on double-tap or retry.
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.feedback_reports (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id            UUID        REFERENCES public.jobs(id) ON DELETE SET NULL,
    user_id           UUID,
    report_type       VARCHAR(20) NOT NULL DEFAULT 'full',
    category          VARCHAR(30) NOT NULL,
    note              TEXT,
    consent_granted   BOOLEAN     NOT NULL DEFAULT TRUE,
    raw_feedback_path TEXT,
    master_path       TEXT,
    pipeline_snapshot JSONB,
    status            VARCHAR(20) NOT NULL DEFAULT 'pending',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewed_at       TIMESTAMPTZ,
    resolved_at       TIMESTAMPTZ
);

COMMENT ON TABLE public.feedback_reports IS
    'Bad-output reports submitted by users from the Document Preview screen.';

COMMENT ON COLUMN public.feedback_reports.raw_feedback_path IS
    'GCS path to the archived raw upload (plaintext JPEG). gs://rythmiq-one-feedback/{job_id}/raw.jpg. NULL for output_only reports.';

COMMENT ON COLUMN public.feedback_reports.master_path IS
    'DO Spaces path to the master file (reference only — not copied). Used to generate preview signed URL.';

COMMENT ON COLUMN public.feedback_reports.pipeline_snapshot IS
    'Snapshot of pipeline metadata at report time: quality_score, stages_used, quad_source, tflite_confidence, etc.';

-- Enforces one report per job. Also prevents duplicate Slack alerts on retry.
CREATE UNIQUE INDEX IF NOT EXISTS idx_feedback_reports_job_id
    ON public.feedback_reports(job_id)
    WHERE job_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_feedback_reports_status
    ON public.feedback_reports(status);

CREATE INDEX IF NOT EXISTS idx_feedback_reports_created_at
    ON public.feedback_reports(created_at DESC);
