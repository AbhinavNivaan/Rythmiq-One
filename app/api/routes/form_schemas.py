"""
Form schemas routes.
Owns: GET /form-schemas — list active exam/form schemas with document upload requirements.

Separate from portal_schemas (image-processing specs used by the worker).
form_schemas describe the full document checklist for a registration form.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends
from supabase import Client

from app.api.db import get_db_client
from app.api.errors import InternalException

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/form-schemas", tags=["form-schemas"])


@router.get("")
async def list_form_schemas(db: Client = Depends(get_db_client)) -> dict[str, Any]:
    """List all active form schemas with their document upload requirements."""
    try:
        result = (
            db.table("form_schemas")
            .select(
                "id, schema_type, schema_version, display_name, short_name, "
                "category, conducting_body, applicable_year, body"
            )
            .eq("is_active", True)
            .order("applicable_year", desc=True)
            .execute()
        )
    except Exception as exc:
        logger.exception("Failed to fetch form_schemas from DB")
        raise InternalException("Could not retrieve form schemas") from exc

    schemas: list[dict[str, Any]] = []
    for row in result.data or []:
        body: dict[str, Any] = row.get("body") or {}
        schemas.append({
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

    return {"schemas": schemas}
