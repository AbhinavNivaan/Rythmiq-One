-- Migration: Add master_path + adapted_from_job_id columns to jobs table
-- Date: 2026-03-05
-- Description:
--   master_path        — Stores the DO Spaces path to the encrypted master blob.
--                        Format: master/{user_id}/{job_id}/{job_id}.enc
--                        Populated only for mode=master jobs after successful processing.
--
--   adapted_from_job_id — Links an adapt job back to the master job it was derived from.
--                         Replaces the overloaded source_job_id stored in input_metadata JSONB.
--                         FK to jobs(id) — NULL for master jobs, set for adapt jobs.

ALTER TABLE public.jobs ADD COLUMN IF NOT EXISTS master_path TEXT;
ALTER TABLE public.jobs ADD COLUMN IF NOT EXISTS adapted_from_job_id UUID REFERENCES public.jobs(id) ON DELETE SET NULL;

COMMENT ON COLUMN public.jobs.master_path IS
  'DO Spaces path to the encrypted master image blob. Format: master/{user_id}/{job_id}/{job_id}.enc. NULL for adapt jobs.';

COMMENT ON COLUMN public.jobs.adapted_from_job_id IS
  'FK to the master job this adapt job was derived from. NULL for master jobs.';

-- Index so we can quickly find all adapt jobs for a given master
CREATE INDEX IF NOT EXISTS idx_jobs_adapted_from ON public.jobs(adapted_from_job_id)
    WHERE adapted_from_job_id IS NOT NULL;
