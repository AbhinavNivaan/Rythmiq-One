-- Enable uuid extension if not already enabled (no-op if already active)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE public.document_extractions (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id        UUID NOT NULL REFERENCES public.jobs(id) ON DELETE CASCADE,
    user_id       UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    document_type TEXT,
    extracted_at  TIMESTAMPTZ DEFAULT NOW(),
    fields        JSONB NOT NULL DEFAULT '{}',
    confidence    JSONB NOT NULL DEFAULT '{}',
    model_version TEXT,
    status        TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'completed', 'failed')),
    error         TEXT
);

ALTER TABLE public.document_extractions ENABLE ROW LEVEL SECURITY;

-- Users can read their own extractions; service role bypasses RLS for writes
CREATE POLICY "Users can view own extractions"
    ON public.document_extractions
    FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users cannot insert extractions"
    ON public.document_extractions
    FOR INSERT
    WITH CHECK (false);

CREATE UNIQUE INDEX idx_extractions_job_id ON public.document_extractions(job_id);
CREATE INDEX idx_extractions_user_id ON public.document_extractions(user_id);
CREATE INDEX idx_extractions_fields ON public.document_extractions USING GIN(fields);
