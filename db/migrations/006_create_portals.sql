-- =============================================================================
-- Migration 006: Create portals table
-- =============================================================================
-- Purpose: Introduce portals as the canonical parent entity.
--          portal_schemas (image specs) and form_schemas (document checklists)
--          both get a portal_id FK, allowing future schema types to link the
--          same way without touching existing table structure.
--
-- Run in Supabase SQL Editor.
-- =============================================================================


-- ---------------------------------------------------------------------------
-- 1. Portals table — one row per exam body / portal identity
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.portals (

    -- Stable slug PK: snake_case, used as FK in all child tables.
    -- Convention: {org}_{exam} for exams (nta_neet, nta_jee),
    --             {org} for general portals (upsc, ssc, ibps, rrb).
    id TEXT PRIMARY KEY
        CONSTRAINT portals_id_format
        CHECK (id ~ '^[a-z][a-z0-9_]{1,49}$'),

    display_name TEXT NOT NULL,   -- "NTA NEET"
    short_name   TEXT NOT NULL,   -- "NEET"
    category     TEXT NOT NULL    -- mirrors form_schemas.category values
        CONSTRAINT portals_category_values
        CHECK (category IN (
            'medical_entrance', 'engineering_entrance', 'management_entrance',
            'government', 'recruitment', 'government_id', 'banking', 'railways'
        )),

    country          TEXT NOT NULL DEFAULT 'IN',
    official_website TEXT,

    is_active  BOOLEAN     NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.portals IS
    'Canonical portal registry. Parent of portal_schemas (image specs), '
    'form_schemas (document checklists), and any future schema types.';


-- ---------------------------------------------------------------------------
-- 2. Seed known portals
-- ---------------------------------------------------------------------------
INSERT INTO public.portals (id, display_name, short_name, category, official_website)
VALUES
    ('nta_neet',      'NTA NEET',      'NEET',     'medical_entrance',     'https://neet.nta.nic.in'),
    ('nta_jee',       'NTA JEE',       'JEE',      'engineering_entrance', 'https://jeemain.nta.ac.in'),
    ('upsc',          'UPSC',          'UPSC',     'government',           'https://upsc.gov.in'),
    ('ssc',           'SSC',           'SSC',      'recruitment',          'https://ssc.nic.in'),
    ('ibps',          'IBPS',          'IBPS',     'banking',              'https://ibps.in'),
    ('rrb',           'RRB',           'RRB',      'railways',             'https://indianrailways.gov.in'),
    ('passport_seva', 'Passport Seva', 'Passport', 'government_id',        'https://passportindia.gov.in'),
    ('uidai',         'UIDAI',         'Aadhaar',  'government_id',        'https://uidai.gov.in')
ON CONFLICT (id) DO NOTHING;


-- ---------------------------------------------------------------------------
-- 3. Add portal_id FK to portal_schemas
--    portal_schemas.name follows the pattern "{portal_prefix}_{doc_type}"
--    e.g. "neet_photo" → nta_neet, "jee_signature" → nta_jee
-- ---------------------------------------------------------------------------
ALTER TABLE public.portal_schemas
    ADD COLUMN IF NOT EXISTS portal_id TEXT REFERENCES public.portals(id);

UPDATE public.portal_schemas
SET portal_id = CASE
    WHEN name LIKE 'neet_%'      THEN 'nta_neet'
    WHEN name LIKE 'jee_%'       THEN 'nta_jee'
    WHEN name LIKE 'upsc_%'      THEN 'upsc'
    WHEN name LIKE 'ssc_%'       THEN 'ssc'
    WHEN name LIKE 'ibps_%'      THEN 'ibps'
    WHEN name LIKE 'rrb_%'       THEN 'rrb'
    WHEN name LIKE 'passport_%'  THEN 'passport_seva'
    WHEN name LIKE 'aadhaar_%'   THEN 'uidai'
    ELSE NULL
END
WHERE portal_id IS NULL;

CREATE INDEX IF NOT EXISTS idx_portal_schemas_portal_id
    ON public.portal_schemas (portal_id)
    WHERE portal_id IS NOT NULL;


-- ---------------------------------------------------------------------------
-- 4. Add portal_id FK to form_schemas
--    form_schemas.id follows "{portal_prefix}_{year}_{type}"
--    e.g. "neet_2026_registration" → nta_neet
-- ---------------------------------------------------------------------------
ALTER TABLE public.form_schemas
    ADD COLUMN IF NOT EXISTS portal_id TEXT REFERENCES public.portals(id);

UPDATE public.form_schemas
SET portal_id = CASE
    WHEN id LIKE 'neet_%' THEN 'nta_neet'
    WHEN id LIKE 'jee_%'  THEN 'nta_jee'
    WHEN id LIKE 'upsc_%' THEN 'upsc'
    WHEN id LIKE 'ssc_%'  THEN 'ssc'
    WHEN id LIKE 'ibps_%' THEN 'ibps'
    WHEN id LIKE 'rrb_%'  THEN 'rrb'
    ELSE NULL
END
WHERE portal_id IS NULL;

CREATE INDEX IF NOT EXISTS idx_form_schemas_portal_id
    ON public.form_schemas (portal_id)
    WHERE portal_id IS NOT NULL;


-- ---------------------------------------------------------------------------
-- 5. RLS for portals (mirrors form_schemas: public read)
-- ---------------------------------------------------------------------------
ALTER TABLE public.portals ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.portals FORCE ROW LEVEL SECURITY;

CREATE POLICY "read_active_portals"
    ON public.portals
    FOR SELECT
    TO anon, authenticated
    USING (is_active = true);

GRANT SELECT ON public.portals TO anon, authenticated;
GRANT ALL    ON public.portals TO service_role;


-- ---------------------------------------------------------------------------
-- 6. Auto-update trigger (reuses the shared update_updated_at function)
-- ---------------------------------------------------------------------------
CREATE TRIGGER update_portals_updated_at
    BEFORE UPDATE ON public.portals
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();


-- ---------------------------------------------------------------------------
-- Verification queries (run after applying this migration)
-- ---------------------------------------------------------------------------
-- SELECT id, display_name, category FROM public.portals ORDER BY id;
-- -- Expected: 8 rows
--
-- SELECT p.id, COUNT(ps.id) AS image_specs, COUNT(fs.id) AS form_schemas
--   FROM public.portals p
--   LEFT JOIN public.portal_schemas ps ON ps.portal_id = p.id
--   LEFT JOIN public.form_schemas   fs ON fs.portal_id = p.id
--  GROUP BY p.id ORDER BY p.id;
-- -- Expected: nta_neet → 2 image_specs, 1 form_schema; others → image_specs only
