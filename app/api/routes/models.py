"""
Route models.
Owns: Request/response schemas for all routes.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# =============================================================================
# Job Models
# =============================================================================


class CreateJobRequest(BaseModel):
    portal_schema_name: str = Field(..., min_length=1, max_length=100)
    filename: str = Field(..., min_length=1, max_length=255)
    mime_type: str = Field(..., pattern=r"^(image|application)/(jpeg|jpg|png|pdf)$")
    file_size_bytes: int = Field(..., gt=0, le=52_428_800)  # 50MB max

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, v: str) -> str:
        if ".." in v or "/" in v or "\\" in v:
            raise ValueError("Invalid filename")
        return v


class CreateJobResponse(BaseModel):
    job_id: UUID
    upload_url: str
    upload_expires_at: datetime


class JobStatusResponse(BaseModel):
    """
    GET /jobs/{id} response.
    
    Includes:
    - status: pending | processing | completed | failed
    - error: null | { code, message } for failed jobs
    - download_url: null | signed-url for completed jobs
    """
    job_id: UUID
    status: str
    portal_schema_name: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_details: dict[str, Any] | None = None
    download_url: str | None = None


class JobOutputResponse(BaseModel):
    job_id: UUID
    portal_output: dict[str, Any]
    download_url: str | None = None


# =============================================================================
# Portal Schema Models
# =============================================================================


class PortalSchemaItem(BaseModel):
    id: UUID
    name: str
    version: int
    requirements_summary: dict[str, Any] | None


class PortalSchemasResponse(BaseModel):
    schemas: list[PortalSchemaItem]


# =============================================================================
# Webhook Models
# =============================================================================


class CamberWebhookRequest(BaseModel):
    """
    Camber worker completion webhook payload.
    
    Expected from Camber when a job completes (success or failure).
    """
    camber_job_id: str = Field(..., min_length=1, description="Camber's internal job ID")
    job_id: UUID = Field(..., description="Rythmiq job ID")
    status: str = Field(..., pattern=r"^(success|failed)$", description="Terminal status")
    result: dict[str, Any] | None = Field(
        default=None,
        description="Worker stdout parsed as JSON. Contains output artifacts on success, error details on failure.",
    )

    @field_validator("result", mode="before")
    @classmethod
    def validate_result(cls, v: Any) -> dict[str, Any] | None:
        """Ensure result is a dict or None."""
        if v is None:
            return None
        if isinstance(v, dict):
            return v
        # Try to handle string JSON (shouldn't happen, but defensive)
        if isinstance(v, str):
            import json
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return {"raw": v}
        return {"raw": str(v)}


class WebhookResponse(BaseModel):
    """Standard webhook acknowledgement response."""
    acknowledged: bool = True


# Legacy model for backwards compatibility
class WebhookJobCompleteRequest(BaseModel):
    """Legacy webhook model. Use CamberWebhookRequest instead."""
    job_id: UUID
    status: str = Field(..., pattern=r"^(completed|failed)$")
    error_details: dict[str, Any] | None = None
    output_storage_path: str | None = None
