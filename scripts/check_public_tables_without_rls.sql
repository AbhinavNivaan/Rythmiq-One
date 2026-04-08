-- Guard query: list public schema tables that do not have RLS enabled.
-- Expected result: 0 rows.
-- Usage:
--   psql "$DATABASE_URL" -f scripts/check_public_tables_without_rls.sql
-- or run directly in Supabase SQL Editor.

SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    CASE WHEN c.relrowsecurity THEN 'enabled' ELSE 'disabled' END AS rls_status,
    CASE WHEN c.relforcerowsecurity THEN 'forced' ELSE 'not_forced' END AS force_status
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relkind IN ('r', 'p')
  AND c.relrowsecurity = false
ORDER BY c.relname;
