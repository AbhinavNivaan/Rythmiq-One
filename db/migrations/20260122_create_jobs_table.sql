CREATE TABLE IF NOT EXISTS jobs (
  job_id UUID PRIMARY KEY,
  blob_id UUID NOT NULL,
  user_id TEXT NOT NULL,
  schema_id TEXT,
  schema_version TEXT,
  state TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  attempt INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 3,
  next_visible_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  ocr_artifact_id TEXT,
  schema_artifact_id TEXT,
  quality_score FLOAT,
  error_code TEXT,
  retryable BOOLEAN,
  CONSTRAINT jobs_state_check CHECK (state IN ('CREATED', 'QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'RETRYING'))
);

CREATE INDEX IF NOT EXISTS idx_jobs_state_next_visible ON jobs (state, next_visible_at);
CREATE INDEX IF NOT EXISTS idx_jobs_user_id ON jobs (user_id);
