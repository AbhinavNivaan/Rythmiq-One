-- ==============================================
-- COMPLETE Portal Schemas Table Setup
-- ==============================================
-- Run this ENTIRE script in Supabase SQL Editor
-- ==============================================

-- Drop existing table if it has wrong structure
DROP TABLE IF EXISTS public.portal_schemas CASCADE;

-- Create portal_schemas table with correct structure
CREATE TABLE public.portal_schemas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    version INTEGER DEFAULT 1,
    is_active BOOLEAN DEFAULT true,
    schema_definition JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable RLS (public read, service role write)
ALTER TABLE public.portal_schemas ENABLE ROW LEVEL SECURITY;

-- Anyone can read active schemas
CREATE POLICY "Anyone can view active schemas" ON public.portal_schemas
    FOR SELECT USING (is_active = true);

-- Service role can do everything
CREATE POLICY "Service role can manage schemas" ON public.portal_schemas
    FOR ALL USING (true);

-- Auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_portal_schemas_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_portal_schemas_updated_at
    BEFORE UPDATE ON public.portal_schemas
    FOR EACH ROW EXECUTE FUNCTION update_portal_schemas_updated_at();

-- Grant permissions
GRANT SELECT ON public.portal_schemas TO anon, authenticated;
GRANT ALL ON public.portal_schemas TO service_role;

-- ==============================================
-- Seed portal schemas
-- ==============================================
INSERT INTO public.portal_schemas (name, version, is_active, schema_definition) VALUES
('passport_photo', 1, true, '{"requirements": {"target_width": 413, "target_height": 531, "target_dpi": 300, "max_kb": 300, "output_format": "jpeg"}}'),
('upsc_photo', 1, true, '{"requirements": {"target_width": 140, "target_height": 180, "target_dpi": 300, "max_kb": 40, "output_format": "jpeg"}}'),
('upsc_signature', 1, true, '{"requirements": {"target_width": 140, "target_height": 60, "target_dpi": 200, "max_kb": 20, "output_format": "jpeg"}}'),
('neet_photo', 1, true, '{"requirements": {"target_width": 181, "target_height": 244, "target_dpi": 200, "max_kb": 200, "output_format": "jpeg"}}'),
('neet_signature', 1, true, '{"requirements": {"target_width": 181, "target_height": 89, "target_dpi": 200, "max_kb": 50, "output_format": "jpeg"}}'),
('jee_photo', 1, true, '{"requirements": {"target_width": 181, "target_height": 244, "target_dpi": 200, "max_kb": 200, "output_format": "jpeg"}}'),
('jee_signature', 1, true, '{"requirements": {"target_width": 181, "target_height": 89, "target_dpi": 200, "max_kb": 50, "output_format": "jpeg"}}'),
('ssc_photo', 1, true, '{"requirements": {"target_width": 100, "target_height": 120, "target_dpi": 100, "max_kb": 100, "output_format": "jpeg"}}'),
('ssc_signature', 1, true, '{"requirements": {"target_width": 140, "target_height": 60, "target_dpi": 100, "max_kb": 50, "output_format": "jpeg"}}'),
('ibps_photo', 1, true, '{"requirements": {"target_width": 200, "target_height": 230, "target_dpi": 200, "max_kb": 50, "output_format": "jpeg"}}'),
('ibps_signature', 1, true, '{"requirements": {"target_width": 140, "target_height": 60, "target_dpi": 200, "max_kb": 20, "output_format": "jpeg"}}'),
('rrb_photo', 1, true, '{"requirements": {"target_width": 165, "target_height": 213, "target_dpi": 200, "max_kb": 50, "output_format": "jpeg"}}'),
('rrb_signature', 1, true, '{"requirements": {"target_width": 165, "target_height": 55, "target_dpi": 200, "max_kb": 30, "output_format": "jpeg"}}');

-- Verify
SELECT name, is_active FROM public.portal_schemas ORDER BY name;
