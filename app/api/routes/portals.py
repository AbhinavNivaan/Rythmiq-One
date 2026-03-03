"""
Portals routes.
Owns: GET /portals — canonical portal registry with nested schema availability.

A portal (e.g. "NTA NEET") is the parent entity. It aggregates:
  - form_schemas   : document checklists for registration/exam forms
  - portal_schemas : image-processing specs used by the worker
  - (future)       : syllabi, result formats, counselling rounds, etc.

The mobile app drives its "Export for Portal" list entirely from this endpoint.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends
from supabase import Client

from app.api.db import get_db_client
from app.api.errors import InternalException

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/portals", tags=["portals"])


@router.get("")
async def list_portals(db: Client = Depends(get_db_client)) -> dict[str, Any]:
    """
    List all active portals with their available schema types.

    Each portal includes:
    - form_schemas[]   : document checklists (one per exam year / form version)
    - has_image_specs  : whether image-processing specs exist for the worker
    """
    try:
        portals_result = (
            db.table("portals")
            .select("id, display_name, short_name, category, country, official_website")
            .eq("is_active", True)
            .order("display_name")
            .execute()
        )
    except Exception as exc:
        logger.exception("Failed to fetch portals")
        raise InternalException("Could not retrieve portals") from exc

    if not portals_result.data:
        return {"portals": []}

    portal_ids = [p["id"] for p in portals_result.data]

    # Fetch active form schemas linked to these portals
    try:
        form_result = (
            db.table("form_schemas")
            .select(
                "id, schema_type, schema_version, display_name, short_name, "
                "category, conducting_body, applicable_year, portal_id, body"
            )
            .eq("is_active", True)
            .in_("portal_id", portal_ids)
            .order("applicable_year", desc=True)
            .execute()
        )
    except Exception as exc:
        logger.exception("Failed to fetch form_schemas for portals")
        raise InternalException("Could not retrieve form schemas") from exc

    # Collect portal IDs that have at least one active image spec
    try:
        image_result = (
            db.table("portal_schemas")
            .select("portal_id")
            .eq("is_active", True)
            .in_("portal_id", portal_ids)
            .execute()
        )
    except Exception as exc:
        logger.exception("Failed to fetch portal_schemas for portals")
        raise InternalException("Could not retrieve image specs") from exc

    # Index form schemas by portal_id
    form_schemas_by_portal: dict[str, list[dict[str, Any]]] = {}
    for row in form_result.data or []:
        pid = row.get("portal_id")
        if not pid:
            continue
        body: dict[str, Any] = row.get("body") or {}
        form_schemas_by_portal.setdefault(pid, []).append({
            "id": row["id"],
            "schema_type": row["schema_type"],
            "schema_version": row.get("schema_version"),
            "display_name": row["display_name"],
            "short_name": row["short_name"],
            "category": row["category"],
            "conducting_body": row.get("conducting_body"),
            "applicable_year": row.get("applicable_year"),
            "document_uploads": body.get("document_uploads", []),
            "key_dates": body.get("key_dates"),
        })

    portals_with_image_specs: set[str] = {
        row["portal_id"]
        for row in (image_result.data or [])
        if row.get("portal_id")
    }

    portals = [
        {
            **p,
            "has_form_schema": p["id"] in form_schemas_by_portal,
            "has_image_specs": p["id"] in portals_with_image_specs,
            "form_schemas": form_schemas_by_portal.get(p["id"], []),
        }
        for p in portals_result.data
    ]

    return {"portals": portals}
