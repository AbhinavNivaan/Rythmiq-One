"""
Inject form schemas into the database.

Scans schemas/exam_forms/, schemas/recruitment/, and schemas/government_id/
for JSON files and upserts them into the Supabase form_schemas table.

Behaviour:
  - If the same (id, schema_version) already exists → update body + denormalised columns in-place.
  - If a different version exists as active → deactivate the old row, insert the new one.
  - Sets portal_id automatically based on the schema_id prefix.

Usage:
    python -m scripts.inject_form_schemas              # inject all
    python -m scripts.inject_form_schemas neet_2026_registration  # inject one by id
"""

import json
import logging
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap: project root on sys.path so app.* imports work if needed later
# ---------------------------------------------------------------------------
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from supabase import create_client

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SCHEMA_DIRS: dict[str, str] = {
    "exam_form":     "schemas/exam_forms",
    "recruitment":   "schemas/recruitment",
    "government_id": "schemas/government_id",
}

# Maps schema_id prefix → portals.id (from migration 006)
PORTAL_ID_MAP: list[tuple[str, str]] = [
    ("neet_",      "nta_neet"),
    ("jee_",       "nta_jee"),
    ("upsc_",      "upsc"),
    ("ssc_",       "ssc"),
    ("ibps_",      "ibps"),
    ("rrb_",       "rrb"),
    ("passport_",  "passport_seva"),
    ("aadhaar_",   "uidai"),
]


def infer_portal_id(schema_id: str) -> str | None:
    for prefix, portal_id in PORTAL_ID_MAP:
        if schema_id.startswith(prefix):
            return portal_id
    return None


# ---------------------------------------------------------------------------
# Load + validate JSON files
# ---------------------------------------------------------------------------

def load_schema_files(filter_id: str | None = None) -> list[dict]:
    schemas = []

    for schema_type, rel_dir in SCHEMA_DIRS.items():
        dir_path = project_root / rel_dir
        if not dir_path.exists():
            continue

        for json_file in sorted(dir_path.glob("*.json")):
            schema_id = json_file.stem

            if filter_id and schema_id != filter_id:
                continue

            with open(json_file) as f:
                try:
                    body = json.load(f)
                except json.JSONDecodeError as exc:
                    log.error("  Skipping %s — invalid JSON: %s", json_file, exc)
                    continue

            # Basic validation
            required_top = {"schema_id", "schema_type", "schema_version", "metadata", "document_uploads"}
            missing = required_top - body.keys()
            if missing:
                log.error("  Skipping %s — missing required fields: %s", json_file.name, missing)
                continue

            if body["schema_id"] != schema_id:
                log.error(
                    "  Skipping %s — schema_id '%s' does not match filename",
                    json_file.name, body["schema_id"]
                )
                continue

            schemas.append({"file": json_file, "body": body, "inferred_type": schema_type})

    return schemas


# ---------------------------------------------------------------------------
# Inject
# ---------------------------------------------------------------------------

def inject(schemas: list[dict], client) -> None:
    for entry in schemas:
        body: dict = entry["body"]
        meta: dict = body.get("metadata", {})

        schema_id:      str       = body["schema_id"]
        schema_version: str       = body["schema_version"]
        schema_type:    str       = body["schema_type"]
        display_name:   str       = meta.get("display_name", schema_id)
        short_name:     str       = meta.get("short_name", schema_id)
        category:       str       = meta.get("category", "")
        conducting_body: str|None = meta.get("conducting_body")
        applicable_year: int|None = meta.get("applicable_year")
        is_active:      bool      = body.get("status", "active") == "active"
        portal_id:      str|None  = infer_portal_id(schema_id)

        log.info("Processing %s  v%s ...", schema_id, schema_version)

        # ------------------------------------------------------------------
        # Check if this (id, version) row already exists
        # ------------------------------------------------------------------
        existing = (
            client.table("form_schemas")
            .select("id, schema_version, is_active")
            .eq("id", schema_id)
            .execute()
        )

        rows_by_version: dict[str, dict] = {
            r["schema_version"]: r for r in (existing.data or [])
        }

        row_data = {
            "id":             schema_id,
            "schema_type":    schema_type,
            "schema_version": schema_version,
            "display_name":   display_name,
            "short_name":     short_name,
            "category":       category,
            "conducting_body": conducting_body,
            "applicable_year": applicable_year,
            "body":           body,
            "is_active":      is_active,
            "portal_id":      portal_id,
        }

        if schema_version in rows_by_version:
            # Same version exists — update in-place
            client.table("form_schemas").update(row_data).eq("id", schema_id).eq("schema_version", schema_version).execute()
            log.info("  Updated  %s v%s", schema_id, schema_version)
        else:
            # New version — deactivate any currently active rows first
            active_rows = [r for r in rows_by_version.values() if r["is_active"]]
            if active_rows:
                client.table("form_schemas").update({"is_active": False}).eq("id", schema_id).eq("is_active", True).execute()
                log.info("  Deactivated old active version(s) of %s", schema_id)

            client.table("form_schemas").insert(row_data).execute()
            log.info("  Inserted  %s v%s", schema_id, schema_version)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    # Optional: filter to a single schema_id from CLI args
    filter_id: str | None = sys.argv[1] if len(sys.argv) > 1 else None

    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

    if not supabase_url or not supabase_key:
        log.error("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
        sys.exit(1)

    client = create_client(supabase_url, supabase_key)

    schemas = load_schema_files(filter_id)

    if not schemas:
        log.warning("No schema files found%s", f" matching '{filter_id}'" if filter_id else "")
        sys.exit(0)

    log.info("Found %d schema file(s) to inject", len(schemas))
    inject(schemas, client)
    log.info("Done.")


if __name__ == "__main__":
    env_file = project_root / ".env"
    if env_file.exists():
        from dotenv import load_dotenv
        load_dotenv(env_file)
    main()
