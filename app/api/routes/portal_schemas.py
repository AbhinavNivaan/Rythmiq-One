"""
Portal schemas routes.
Owns: Read-only portal schema listing.
"""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.auth import AuthenticatedUser, get_current_user
from app.api.db import get_db_client
from app.api.errors import InternalException
from .models import PortalSchemaItem, PortalSchemasResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/portal-schemas", tags=["portal-schemas"])


@router.get("", response_model=PortalSchemasResponse)
async def list_portal_schemas(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> PortalSchemasResponse:
    db = get_db_client()

    result = (
        db.table("portal_schemas")
        .select("id, name, version, schema_definition")
        .eq("is_active", True)
        .order("name")
        .execute()
    )

    if result.data is None:
        raise InternalException("Failed to fetch portal schemas")

    schemas = []
    for row in result.data:
        schema_def = row.get("schema_definition", {})
        requirements = schema_def.get("requirements", None)

        schemas.append(
            PortalSchemaItem(
                id=UUID(row["id"]),
                name=row["name"],
                version=row["version"],
                requirements_summary=requirements,
            )
        )

    return PortalSchemasResponse(schemas=schemas)
