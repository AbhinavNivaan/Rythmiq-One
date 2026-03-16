-- =============================================================================
-- Migration: Add colour_mode to portal_schemas requirements JSONB
-- =============================================================================
-- Stream 2 — ITU-T T.44 Tier 2 compliance
--
-- No ALTER TABLE required: colour_mode lives inside the requirements JSONB column.
-- This migration backfills colour_mode into existing rows that were seeded before
-- db/schema.sql was updated.
--
-- Safe to re-run: WHERE clause only targets rows missing the colour_mode key.
-- =============================================================================

-- Photo sub-schemas default to colour (no conversion)
UPDATE public.portal_schemas
SET schema_definition = jsonb_set(
        schema_definition,
        '{photo,colour_mode}',
        '"colour"'
    )
WHERE is_active = true
  AND (schema_definition -> 'photo' ->> 'colour_mode') IS NULL;

-- Signature sub-schemas default to greyscale (portal requirement)
UPDATE public.portal_schemas
SET schema_definition = jsonb_set(
        schema_definition,
        '{signature,colour_mode}',
        '"greyscale"'
    )
WHERE is_active = true
  AND (schema_definition -> 'signature' ->> 'colour_mode') IS NULL;
