-- Fix extraction persistence FK mismatch:
-- jobs.user_id maps to auth user UUIDs, but document_extractions.user_id
-- was incorrectly constrained to public.users(id), which can be absent.

ALTER TABLE public.document_extractions
    DROP CONSTRAINT IF EXISTS document_extractions_user_id_fkey;

ALTER TABLE public.document_extractions
    ADD CONSTRAINT document_extractions_user_id_fkey
    FOREIGN KEY (user_id)
    REFERENCES auth.users(id)
    ON DELETE CASCADE;
