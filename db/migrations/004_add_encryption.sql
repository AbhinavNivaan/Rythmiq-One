-- ==============================================
-- Phase 1 Encryption-at-Rest
-- Creates users/documents tables if missing,
-- then adds SEK and encryption metadata columns.
-- Safe to run multiple times (all IF NOT EXISTS).
-- ==============================================

-- Enable UUID extension (likely already enabled)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ==============================================
-- 1. Create users table (if missing)
-- ==============================================
CREATE TABLE IF NOT EXISTS public.users (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT UNIQUE NOT NULL,
    encrypted_key_hash TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;

-- RLS policies (CREATE POLICY does not support IF NOT EXISTS, so use DO block)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'users' AND policyname = 'Users can view own profile'
    ) THEN
        CREATE POLICY "Users can view own profile" ON public.users
            FOR SELECT USING (auth.uid() = id);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'users' AND policyname = 'Users can update own profile'
    ) THEN
        CREATE POLICY "Users can update own profile" ON public.users
            FOR UPDATE USING (auth.uid() = id);
    END IF;
END
$$;

-- ==============================================
-- 2. Create documents table (if missing)
-- ==============================================
CREATE TABLE IF NOT EXISTS public.documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    type TEXT NOT NULL DEFAULT 'other' CHECK (type IN ('voter_id', 'aadhaar', 'pan', 'photo', 'signature', 'marksheet', 'other')),
    filename TEXT NOT NULL DEFAULT 'document',
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

ALTER TABLE public.documents ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'documents' AND policyname = 'Users can view own documents'
    ) THEN
        CREATE POLICY "Users can view own documents" ON public.documents
            FOR SELECT USING (auth.uid() = user_id);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'documents' AND policyname = 'Users can insert own documents'
    ) THEN
        CREATE POLICY "Users can insert own documents" ON public.documents
            FOR INSERT WITH CHECK (auth.uid() = user_id);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'documents' AND policyname = 'Users can update own documents'
    ) THEN
        CREATE POLICY "Users can update own documents" ON public.documents
            FOR UPDATE USING (auth.uid() = user_id);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'documents' AND policyname = 'Users can delete own documents'
    ) THEN
        CREATE POLICY "Users can delete own documents" ON public.documents
            FOR DELETE USING (auth.uid() = user_id);
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_documents_user_id ON public.documents(user_id);
CREATE INDEX IF NOT EXISTS idx_documents_status ON public.documents(status);

-- ==============================================
-- 3. Add optional columns used by webhooks
--    (job_id, portal_outputs, canonical_output)
-- ==============================================
ALTER TABLE public.documents ADD COLUMN IF NOT EXISTS job_id UUID;
ALTER TABLE public.documents ADD COLUMN IF NOT EXISTS portal_outputs JSONB DEFAULT '{}';
ALTER TABLE public.documents ADD COLUMN IF NOT EXISTS canonical_output JSONB DEFAULT '{}';

CREATE INDEX IF NOT EXISTS idx_documents_job_id ON public.documents(job_id);

-- ==============================================
-- 4. Encryption-at-rest columns
-- ==============================================

-- Per-user Storage Encryption Key (base64-encoded 256-bit)
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS storage_encryption_key TEXT;

-- Per-document encryption metadata
ALTER TABLE public.documents ADD COLUMN IF NOT EXISTS encrypted BOOLEAN DEFAULT FALSE;
ALTER TABLE public.documents ADD COLUMN IF NOT EXISTS encryption_nonce TEXT;

CREATE INDEX IF NOT EXISTS idx_documents_encrypted ON public.documents(encrypted);

-- ==============================================
-- 5. Grants (ensure PostgREST can see the tables)
-- ==============================================
GRANT USAGE ON SCHEMA public TO anon, authenticated;
GRANT ALL ON public.users TO authenticated;
GRANT ALL ON public.documents TO authenticated;

-- Service role needs full access for webhooks and backfill
GRANT ALL ON public.users TO service_role;
GRANT ALL ON public.documents TO service_role;

-- ==============================================
-- 6. Auto-update triggers
-- ==============================================
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Drop existing triggers first to avoid duplicates, then recreate
DROP TRIGGER IF EXISTS update_users_updated_at ON public.users;
CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON public.users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

DROP TRIGGER IF EXISTS update_documents_updated_at ON public.documents;
CREATE TRIGGER update_documents_updated_at
    BEFORE UPDATE ON public.documents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
