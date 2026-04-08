-- =============================================================================
-- Migration: Secure feedback_reports with RLS
-- =============================================================================
-- Resolves Supabase security warning: RLS Disabled in Public for feedback_reports.
-- Access model: backend-only writes/reads via service_role key.
-- =============================================================================

ALTER TABLE public.feedback_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.feedback_reports FORCE ROW LEVEL SECURITY;

-- Remove any direct PostgREST table access for client roles.
REVOKE ALL ON TABLE public.feedback_reports FROM anon, authenticated;

-- Ensure backend access via service role remains intact.
GRANT ALL ON TABLE public.feedback_reports TO service_role;
