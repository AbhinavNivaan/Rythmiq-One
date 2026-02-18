-- ==============================================
-- Migration: Add missing columns to portal_schemas
-- ==============================================
-- Run this in Supabase SQL editor

-- Add version column if not exists
ALTER TABLE public.portal_schemas 
ADD COLUMN IF NOT EXISTS version INTEGER DEFAULT 1;

-- Rename 'active' to 'is_active' if needed
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'portal_schemas' AND column_name = 'active'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'portal_schemas' AND column_name = 'is_active'
    ) THEN
        ALTER TABLE public.portal_schemas RENAME COLUMN active TO is_active;
    END IF;
END $$;

-- Add is_active column if neither exists
ALTER TABLE public.portal_schemas 
ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT true;

-- Add schema_definition column if not exists (renamed from requirements)
ALTER TABLE public.portal_schemas 
ADD COLUMN IF NOT EXISTS schema_definition JSONB;

-- Copy data from requirements to schema_definition if needed
UPDATE public.portal_schemas 
SET schema_definition = jsonb_build_object('requirements', requirements)
WHERE schema_definition IS NULL AND requirements IS NOT NULL;

-- Update RLS policy to use is_active
DROP POLICY IF EXISTS "Anyone can view active schemas" ON public.portal_schemas;
CREATE POLICY "Anyone can view active schemas" ON public.portal_schemas
    FOR SELECT USING (is_active = true);

-- ==============================================
-- Seed more comprehensive portal schemas
-- ==============================================
INSERT INTO public.portal_schemas (id, name, category, is_active, version, schema_definition, requirements) VALUES
('passport_photo', 'Passport Photo', 'government', true, 1, 
 '{"requirements": {"target_width": 413, "target_height": 531, "target_dpi": 300, "max_kb": 300, "output_format": "jpeg"}}',
 '{"target_width": 413, "target_height": 531, "target_dpi": 300, "max_kb": 300, "output_format": "jpeg"}'::jsonb),
('upsc_photo', 'UPSC Photo', 'government', true, 1,
 '{"requirements": {"target_width": 140, "target_height": 180, "target_dpi": 300, "max_kb": 40, "output_format": "jpeg"}}',
 '{"target_width": 140, "target_height": 180, "target_dpi": 300, "max_kb": 40, "output_format": "jpeg"}'::jsonb),
('upsc_signature', 'UPSC Signature', 'government', true, 1,
 '{"requirements": {"target_width": 140, "target_height": 60, "target_dpi": 200, "max_kb": 20, "output_format": "jpeg"}}',
 '{"target_width": 140, "target_height": 60, "target_dpi": 200, "max_kb": 20, "output_format": "jpeg"}'::jsonb),
('neet_photo', 'NEET Photo', 'exam', true, 1,
 '{"requirements": {"target_width": 181, "target_height": 244, "target_dpi": 200, "max_kb": 200, "output_format": "jpeg"}}',
 '{"target_width": 181, "target_height": 244, "target_dpi": 200, "max_kb": 200, "output_format": "jpeg"}'::jsonb),
('neet_signature', 'NEET Signature', 'exam', true, 1,
 '{"requirements": {"target_width": 181, "target_height": 89, "target_dpi": 200, "max_kb": 50, "output_format": "jpeg"}}',
 '{"target_width": 181, "target_height": 89, "target_dpi": 200, "max_kb": 50, "output_format": "jpeg"}'::jsonb),
('jee_photo', 'JEE Photo', 'exam', true, 1,
 '{"requirements": {"target_width": 181, "target_height": 244, "target_dpi": 200, "max_kb": 200, "output_format": "jpeg"}}',
 '{"target_width": 181, "target_height": 244, "target_dpi": 200, "max_kb": 200, "output_format": "jpeg"}'::jsonb),
('jee_signature', 'JEE Signature', 'exam', true, 1,
 '{"requirements": {"target_width": 181, "target_height": 89, "target_dpi": 200, "max_kb": 50, "output_format": "jpeg"}}',
 '{"target_width": 181, "target_height": 89, "target_dpi": 200, "max_kb": 50, "output_format": "jpeg"}'::jsonb),
('ssc_photo', 'SSC Photo', 'government', true, 1,
 '{"requirements": {"target_width": 100, "target_height": 120, "target_dpi": 100, "max_kb": 100, "output_format": "jpeg"}}',
 '{"target_width": 100, "target_height": 120, "target_dpi": 100, "max_kb": 100, "output_format": "jpeg"}'::jsonb),
('ssc_signature', 'SSC Signature', 'government', true, 1,
 '{"requirements": {"target_width": 140, "target_height": 60, "target_dpi": 100, "max_kb": 50, "output_format": "jpeg"}}',
 '{"target_width": 140, "target_height": 60, "target_dpi": 100, "max_kb": 50, "output_format": "jpeg"}'::jsonb),
('ibps_photo', 'IBPS Photo', 'government', true, 1,
 '{"requirements": {"target_width": 200, "target_height": 230, "target_dpi": 200, "max_kb": 50, "output_format": "jpeg"}}',
 '{"target_width": 200, "target_height": 230, "target_dpi": 200, "max_kb": 50, "output_format": "jpeg"}'::jsonb),
('ibps_signature', 'IBPS Signature', 'government', true, 1,
 '{"requirements": {"target_width": 140, "target_height": 60, "target_dpi": 200, "max_kb": 20, "output_format": "jpeg"}}',
 '{"target_width": 140, "target_height": 60, "target_dpi": 200, "max_kb": 20, "output_format": "jpeg"}'::jsonb)
ON CONFLICT (id) DO UPDATE SET
    schema_definition = EXCLUDED.schema_definition,
    requirements = EXCLUDED.requirements,
    is_active = true,
    version = 1;
