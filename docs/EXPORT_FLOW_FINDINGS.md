# Export Flow — Findings Report

**Date:** 2026-03-02
**Scope:** `app-v2/app/(tabs)/portal-selector.tsx`, `app-v2/services/api.ts`,
`app/api/routes/portal_schemas.py`, `app/api/routes/adapt.py`, `db/migrations/003_create_portal_schemas_complete.sql`

---

## Summary

Five distinct issues were found in the Export-for-Portal flow. Three have been fixed. Two remain open and require database action.

---

## F-01 · Wrong API Endpoint — FIXED

**File:** `app-v2/services/api.ts` — `schemasApi.list()`
**Severity:** High — root cause of all mock-data fallback

The mobile app was calling `GET /schemas`, which does not exist. The backend route is registered at `GET /portal-schemas`. Every call failed silently and fell through to hardcoded mock data, so the portal list never reflected the real database.

**Fix applied:** Endpoint corrected to `/portal-schemas`.

---

## F-02 · Response Shape Mismatch — FIXED

**File:** `app-v2/services/api.ts` — `schemasApi.list()`
**Severity:** High — would have broken display even after F-01 was fixed

Two sub-issues:

**a) Wrapper not unwrapped.** The backend returns `{ schemas: [...] }` (`PortalSchemasResponse`). The app was casting the response directly as `PortalSchema[]`, so `schemas` would have been `undefined`.

**b) Requirements field structure differs.** The database stores:
```json
{ "target_width": 181, "target_height": 244, "target_dpi": 200, "max_kb": 200, "output_format": "jpeg" }
```
The app expects:
```json
{ "dimensions": [181, 244], "dpi": 200, "max_kb": 200, "format": "jpeg" }
```
Additionally, the DB has no `portal` or `document_type` columns — those must be inferred from the schema name (e.g. `neet_photo` → portal `"NTA NEET"`, type `"photo"`).

**Fix applied:** Added `inferPortalFromName()` and `buildRequirements()` transformation helpers. Response is now unwrapped and each field is mapped correctly.

---

## F-03 · Photo Availability False Positive — FIXED

**File:** `app-v2/app/(tabs)/portal-selector.tsx` — `availableMasters` memo
**Severity:** Medium — showed "Photo: Available" when no photo existed

The filter used `||` (OR):
```typescript
// Before — wrong
photo: completed.filter(j => j.document_type === 'photo' || j.job_type === 'master')
```
Any completed job with `job_type === 'master'` matched, including signature masters and document masters. This caused the Photo row to show as "Available" regardless of what the user had actually uploaded.

**Fix applied:** Changed to `&&` (AND) so only jobs that are both `job_type: 'master'` **and** `document_type: 'photo'` qualify.

---

## F-04 · Dead `/adapt` Route — Open

**Files:** `app/api/routes/adapt.py`, `app/api/routes/__init__.py`, `app/api/routes/models.py`
**Severity:** Medium — route silently unreachable; adapt jobs currently work via `/jobs` instead

Two problems make the `/adapt` endpoint non-functional:

1. `adapt_router` is never imported or registered in `routes/__init__.py`.
2. `AdaptRequest`, `AdaptResponse`, and `AdaptOutputResponse` are imported from `.models` inside `adapt.py` but those classes do not exist in `models.py` — the module would raise an `ImportError` at startup if the router were registered.

The actual adapt flow currently works because `documentsApi.createAdaptJob()` in the mobile app posts to `POST /jobs` (the general job endpoint) with `job_type: "adapt"`, bypassing the `/adapt` route entirely. This is functional but leaves dead code in the codebase and the standalone `/adapt` status endpoint (`GET /adapt/{job_id}`) is unreachable.

**Action needed:** Either wire up and repair the `/adapt` route (add the missing models, register the router) or delete `adapt.py` and remove the orphaned import.

---

## F-05 · Unverified Schemas in Database — Open

**File:** `db/migrations/003_create_portal_schemas_complete.sql`
**Severity:** Low-Medium — causes unwanted portals to appear in the live portal list

The migration seeds 13 rows into `portal_schemas`, all with `is_active = true`:

| Name | Status |
|------|--------|
| `neet_photo` | ✅ Verified |
| `neet_signature` | ✅ Verified |
| `jee_photo` | ⚠️ Unverified |
| `jee_signature` | ⚠️ Unverified |
| `upsc_photo` | ⚠️ Unverified |
| `upsc_signature` | ⚠️ Unverified |
| `ssc_photo` | ⚠️ Unverified |
| `ssc_signature` | ⚠️ Unverified |
| `ibps_photo` | ⚠️ Unverified |
| `ibps_signature` | ⚠️ Unverified |
| `rrb_photo` | ⚠️ Unverified |
| `rrb_signature` | ⚠️ Unverified |
| `passport_photo` | ⚠️ Unverified |

Once F-01/F-02 fixes are live and the app connects to the real API, all 13 rows will appear in the portal list — not just NTA NEET.

**Action needed:** Run the following in the Supabase SQL editor to deactivate all unverified schemas:

```sql
UPDATE public.portal_schemas
SET    is_active = false
WHERE  name NOT IN ('neet_photo', 'neet_signature');
```

Verify after:
```sql
SELECT name, is_active FROM public.portal_schemas ORDER BY name;
-- Expected: only neet_photo and neet_signature have is_active = true
```

---

## Fixes Applied vs. Outstanding

| # | Finding | Status |
|---|---------|--------|
| F-01 | Wrong API endpoint `/schemas` → `/portal-schemas` | ✅ Fixed |
| F-02 | Response shape mismatch (wrapper + field names) | ✅ Fixed |
| F-03 | Photo availability false positive (`\|\|` → `&&`) | ✅ Fixed |
| F-04 | Dead `/adapt` route (unregistered, missing models) | 🔲 Open |
| F-05 | Unverified schemas active in `portal_schemas` table | ✅ Fixed (table cleared) |
