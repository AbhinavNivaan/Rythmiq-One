# Form Schema Authoring & Injection

How to add or update exam / recruitment / government-ID form schemas.

---

## 1. File locations

| Schema type      | Directory                      | DB `schema_type` value |
|------------------|--------------------------------|------------------------|
| Exam form        | `schemas/exam_forms/`          | `exam_form`            |
| Recruitment form | `schemas/recruitment/`         | `recruitment`          |
| Government ID    | `schemas/government_id/`       | `government_id`        |

File name = `{schema_id}.json`. The `schema_id` inside the JSON must match the filename stem.

---

## 2. Creating a new schema

Copy the appropriate template from `schemas/_templates/` and fill it in.
Full field reference: `schemas/spec/SCHEMA_SPEC.md`.

**Critical fields in `document_uploads`** — every upload slot that maps to a vault document
must include:

| Field                     | Purpose                                                                 |
|---------------------------|-------------------------------------------------------------------------|
| `document_category`       | Vault category (`photograph`, `signature`, `academic`, `identity`, …)  |
| `document_subtype`        | Exact subtype label the user will store the file under                  |
| `seeds_document_subtypes` | Array of subtypes to inject into the upload UI. **Required whenever `document_subtype` is not already in the base list** (see §6.1 of SCHEMA_SPEC.md). Without this the user won't see the subtype as a selectable option. |

Example — postcard photo (non-standard subtype, so seeding is required):

```json
{
  "doc_id":                   "photograph_postcard",
  "label":                    "Postcard-size Photograph (4x6 inch)",
  "allowed_formats":          ["JPG", "JPEG"],
  "size_max_kb":              200,
  "required":                 true,
  "required_if":              null,
  "document_category":        "photograph",
  "document_subtype":         "Postcard Photo",
  "seeds_document_subtypes":  ["Postcard Photo"]
}
```

Standard subtypes that **do not** need seeding (already in the base upload-UI lists):
- `photograph`: Passport Photo, Profile Photo, ID Photo, Document Photo
- `signature`: Personal Signature
- `academic`: Certificate, Diploma, Degree, Transcript, Grade Card
- `identity`: Aadhaar Card, PAN Card, Passport, Voter ID, Driving Licence, Ration Card

---

## 3. Versioning

| Change type                                   | Bump       | Example          |
|-----------------------------------------------|------------|------------------|
| Label fix, note added, fee amount corrected   | PATCH      | 1.0.0 → 1.0.1   |
| New optional field or document slot added     | MINOR      | 1.0.0 → 1.1.0   |
| Required field added/removed, field renamed   | MAJOR      | 1.0.0 → 2.0.0   |

The old active row is kept in the DB with `is_active = false` for audit history.
Only one version per `schema_id` should be `is_active = true` at any time.

---

## 4. Injecting into the database

Run from the project root with the virtual environment active:

```bash
# Inject all schemas found in schemas/
python -m scripts.inject_form_schemas

# Inject one specific schema by id
python -m scripts.inject_form_schemas neet_2026_registration
```

The script (`scripts/inject_form_schemas.py`) will:
- **Update in-place** if the same `(id, schema_version)` already exists in the DB.
- **Deactivate the old version and insert a new row** if the version number has changed.
- Set `portal_id` automatically from the `schema_id` prefix (e.g. `neet_` → `nta_neet`).

Required env vars (loaded automatically from `.env`):
```
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
```

---

## 5. Portal ID mapping

`portal_id` is inferred from the `schema_id` prefix at injection time:

| Prefix        | `portal_id`     |
|---------------|-----------------|
| `neet_`       | `nta_neet`      |
| `jee_`        | `nta_jee`       |
| `upsc_`       | `upsc`          |
| `ssc_`        | `ssc`           |
| `ibps_`       | `ibps`          |
| `rrb_`        | `rrb`           |
| `passport_`   | `passport_seva` |
| `aadhaar_`    | `uidai`         |
| _(no match)_  | `NULL`          |

To add a new portal, add a row to the `portals` table first (see `db/migrations/006_create_portals.sql`), then add its prefix to `PORTAL_ID_MAP` in `scripts/inject_form_schemas.py`.

---

## 6. How vault-mapping drives the upload UI

The mobile upload screen (`app-v2/app/(tabs)/upload.tsx`) fetches all active form schemas on mount and calls `useSeededDocumentCategories`, which:

1. Reads every `seeds_document_subtypes` array across all schemas.
2. Merges those subtypes into the base type list for the matching `document_category`.
3. The merged list is what appears in the "Document Type" dropdown.

This means a non-standard subtype like "Postcard Photo" will only be selectable if at least one active schema seeds it. If a schema is deactivated or a seeding entry is missing, the subtype silently disappears from the UI.
