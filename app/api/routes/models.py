"""
Route models.
Owns: Request/response schemas for all routes.
"""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# =============================================================================
# Job Models
# =============================================================================


class CreateJobRequest(BaseModel):
    job_type: Literal["master", "adapt"] = Field(default="master")
    document_type: Literal["photo", "signature", "document"] = Field(default="document")
    document_category: str | None = Field(default=None, max_length=50)
    document_subtype: str | None = Field(default=None, max_length=100)
    # --- New form-schema intake path (NEET 2026+) ---
    # When form_schema_id + doc_id are both provided, the pixel spec is resolved
    # from the form_schemas table instead of the legacy portal_schemas table.
    form_schema_id: str | None = Field(default=None, max_length=100)
    doc_id: str | None = Field(default=None, max_length=100)
    # --- Legacy portal_schemas path (still required for non-NEET portals) ---
    portal_schema_name: str | None = Field(default=None, min_length=1, max_length=100)
    # For adapt jobs: reference an existing completed master job instead of uploading a new file.
    # When provided, filename/mime_type/file_size_bytes are not required.
    source_job_id: UUID | None = Field(default=None)
    filename: str | None = Field(default=None, max_length=255)
    mime_type: str | None = Field(default=None, pattern=r"^(image|application)/(jpeg|jpg|png|pdf)$")
    file_size_bytes: int | None = Field(default=None, gt=0, le=52_428_800)  # 50MB max
    defer_processing: bool = Field(
        default=False,
        description="If true, creates pending job + upload URL without dispatching processing. Client must call /jobs/{job_id}/submit after upload.",
    )
    # User's Storage Encryption Key passed at dispatch time (zero-knowledge model).
    # Required for adapt-from-master jobs when source is an encrypted master blob.
    # Never stored server-side.
    sek_b64: str | None = Field(default=None)

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if ".." in v or "/" in v or "\\" in v:
            raise ValueError("Invalid filename")
        return v

    @field_validator("portal_schema_name")
    @classmethod
    def validate_portal_schema_name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        value = v.strip()
        return value or None


class CreateJobResponse(BaseModel):
    job_id: UUID
    # None for adapt jobs created from an existing source_job_id (no upload step needed).
    upload_url: str | None = None
    upload_expires_at: datetime | None = None


class SubmitJobRequest(BaseModel):
    output_format: str = "jpeg"  # "jpeg" | "jpeg2000" | "pdf_mrc"


class SubmitJobResponse(BaseModel):
    job_id: UUID
    status: str


class JobStatusResponse(BaseModel):
    """
    GET /jobs/{id} response.
    
    Includes:
    - status: pending | processing | completed | failed
    - error: null | { code, message } for failed jobs
    - download_url: null | signed-url for completed jobs
    - input_quality_score: quality of the raw uploaded image (0–1)
    - output_quality_score: quality of the processed output image (0–1)
    """
    job_id: UUID
    status: str
    portal_schema_name: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_details: dict[str, Any] | None = None
    download_url: str | None = None
    preview_url: str | None = None
    input_quality_score: float | None = None
    output_quality_score: float | None = None


class JobOutputResponse(BaseModel):
    job_id: UUID
    portal_output: dict[str, Any]
    download_url: str | None = None


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


