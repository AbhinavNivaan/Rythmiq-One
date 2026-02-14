-- ==============================================
-- Rythmiq One - Supabase Database Schema & RLS
-- ==============================================
-- Run this in your Supabase SQL editor
-- ==============================================

-- Enable necessary extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ==============================================
-- USERS TABLE (extends Supabase auth.users)
-- ==============================================
CREATE TABLE IF NOT EXISTS public.users (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT UNIQUE NOT NULL,
    encrypted_key_hash TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable RLS
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;

-- Users can only read/update their own record
CREATE POLICY "Users can view own profile" ON public.users
    FOR SELECT USING (auth.uid() = id);

CREATE POLICY "Users can update own profile" ON public.users
    FOR UPDATE USING (auth.uid() = id);

-- ==============================================
-- DOCUMENTS TABLE
-- ==============================================
CREATE TABLE IF NOT EXISTS public.documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    type TEXT NOT NULL CHECK (type IN ('voter_id', 'aadhaar', 'pan', 'photo', 'signature', 'marksheet', 'other')),
    filename TEXT NOT NULL,
    encrypted_path TEXT,
    master_path TEXT,
    quality_score DECIMAL(3,2) CHECK (quality_score >= 0 AND quality_score <= 1),
    status TEXT NOT NULL DEFAULT 'uploaded' CHECK (status IN ('uploaded', 'processing', 'master_ready', 'failed')),
    error_code TEXT,
    error_message TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable RLS
ALTER TABLE public.documents ENABLE ROW LEVEL SECURITY;

-- Users can only access their own documents
CREATE POLICY "Users can view own documents" ON public.documents
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own documents" ON public.documents
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own documents" ON public.documents
    FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own documents" ON public.documents
    FOR DELETE USING (auth.uid() = user_id);

-- Index for faster user document lookups
CREATE INDEX IF NOT EXISTS idx_documents_user_id ON public.documents(user_id);
CREATE INDEX IF NOT EXISTS idx_documents_status ON public.documents(status);

-- ==============================================
-- JOBS TABLE
-- ==============================================
CREATE TABLE IF NOT EXISTS public.jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    document_id UUID REFERENCES public.documents(id) ON DELETE SET NULL,
    job_type TEXT NOT NULL CHECK (job_type IN ('process', 'adapt')),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    input_artifact_path TEXT,
    output_artifact_path TEXT,
    target_portal TEXT,
    quality_score DECIMAL(3,2) CHECK (quality_score >= 0 AND quality_score <= 1),
    error_code TEXT,
    error_message TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

-- Enable RLS
ALTER TABLE public.jobs ENABLE ROW LEVEL SECURITY;

-- Users can only access their own jobs
CREATE POLICY "Users can view own jobs" ON public.jobs
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own jobs" ON public.jobs
    FOR INSERT WITH CHECK (auth.uid() = user_id);

-- Service role can update any job (for webhooks)
CREATE POLICY "Service role can update jobs" ON public.jobs
    FOR UPDATE USING (true);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_jobs_user_id ON public.jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON public.jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_document_id ON public.jobs(document_id);

-- ==============================================
-- PORTAL SCHEMAS TABLE
-- ==============================================
CREATE TABLE IF NOT EXISTS public.portal_schemas (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'other',
    requirements JSONB NOT NULL,
    active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable RLS (public read, admin write)
ALTER TABLE public.portal_schemas ENABLE ROW LEVEL SECURITY;

-- Anyone can read active schemas
CREATE POLICY "Anyone can view active schemas" ON public.portal_schemas
    FOR SELECT USING (active = true);

-- Only service role can modify schemas
CREATE POLICY "Service role can manage schemas" ON public.portal_schemas
    FOR ALL USING (true);

-- ==============================================
-- AUDIT LOG TABLE (for transparency)
-- ==============================================
CREATE TABLE IF NOT EXISTS public.audit_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    document_id UUID REFERENCES public.documents(id) ON DELETE SET NULL,
    job_id UUID REFERENCES public.jobs(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    details JSONB DEFAULT '{}',
    ip_address INET,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable RLS
ALTER TABLE public.audit_log ENABLE ROW LEVEL SECURITY;

-- Users can only view their own audit logs
CREATE POLICY "Users can view own audit logs" ON public.audit_log
    FOR SELECT USING (auth.uid() = user_id);

-- Service role can insert audit logs
CREATE POLICY "Service role can insert audit logs" ON public.audit_log
    FOR INSERT WITH CHECK (true);

-- Index for user lookups
CREATE INDEX IF NOT EXISTS idx_audit_log_user_id ON public.audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_document_id ON public.audit_log(document_id);

-- ==============================================
-- FUNCTIONS
-- ==============================================

-- Auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply to tables
CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON public.users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER update_documents_updated_at
    BEFORE UPDATE ON public.documents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER update_portal_schemas_updated_at
    BEFORE UPDATE ON public.portal_schemas
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ==============================================
-- SEED DATA: Portal Schemas
-- ==============================================
INSERT INTO public.portal_schemas (id, name, category, requirements) VALUES
('NEET_2026', 'NEET 2026', 'exam', '{
    "photo": {"dimensions": [400, 600], "dpi": 300, "max_kb": 200, "format": "jpg"},
    "signature": {"dimensions": [200, 100], "dpi": 200, "max_kb": 50, "format": "jpg"}
}'::jsonb),
('JEE_MAIN_2026', 'JEE Main 2026', 'exam', '{
    "photo": {"dimensions": [400, 600], "dpi": 300, "max_kb": 200, "format": "jpg"},
    "signature": {"dimensions": [200, 100], "dpi": 200, "max_kb": 50, "format": "jpg"}
}'::jsonb),
('UPSC_CSE_2026', 'UPSC CSE 2026', 'government', '{
    "photo": {"dimensions": [400, 600], "dpi": 300, "max_kb": 300, "format": "jpg"},
    "signature": {"dimensions": [200, 100], "dpi": 200, "max_kb": 50, "format": "jpg"}
}'::jsonb),
('CAT_2026', 'CAT 2026', 'exam', '{
    "photo": {"dimensions": [400, 600], "dpi": 300, "max_kb": 200, "format": "jpg"},
    "signature": {"dimensions": [200, 100], "dpi": 200, "max_kb": 50, "format": "jpg"}
}'::jsonb),
('GATE_2026', 'GATE 2026', 'exam', '{
    "photo": {"dimensions": [480, 640], "dpi": 300, "max_kb": 200, "format": "jpg"},
    "signature": {"dimensions": [240, 120], "dpi": 200, "max_kb": 50, "format": "jpg"}
}'::jsonb)
ON CONFLICT (id) DO NOTHING;

-- ==============================================
-- GRANT PERMISSIONS
-- ==============================================
GRANT USAGE ON SCHEMA public TO anon, authenticated;
GRANT SELECT ON public.portal_schemas TO anon, authenticated;
GRANT ALL ON public.users TO authenticated;
GRANT ALL ON public.documents TO authenticated;
GRANT ALL ON public.jobs TO authenticated;
GRANT SELECT ON public.audit_log TO authenticated;
