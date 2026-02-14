"""
Adapt routes.
Owns: Schema adaptation endpoints.

Handles adapting completed documents to specific portal requirements.
"""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from postgrest.exceptions import APIError

from app.api.auth import AuthenticatedUser, get_current_user
from app.api.db import get_db_client, transition_job_state
from app.api.errors import (
    CamberException,
    InternalException,
    InvalidInputException,
    JobNotCompleteException,
    NotFoundException,
    SchemaNotFoundException,
)
from app.api.services.camber import CamberService, get_camber_service
from app.api.services.packaging import PackagingService, get_packaging_service
from .models import AdaptRequest, AdaptResponse, AdaptOutputResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/adapt", tags=["adapt"])


@router.post("", response_model=AdaptResponse)
async def adapt_document(
    request: Request,
    body: AdaptRequest,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    camber: Annotated[CamberService, Depends(get_camber_service)],
) -> AdaptResponse:
    """
    Adapt a completed document to a specific portal schema.
    
    Flow:
    1. Verify source document/job exists and is completed
    2. Verify target portal schema exists
    3. Create new adaptation job
    4. Submit to worker for schema-specific processing
    5. Return job ID for status polling
    """
    correlation_id = getattr(request.state, "correlation_id", "unknown")
    db = get_db_client()
    
    # -------------------------------------------------------------------------
    # 1. Verify source document exists and is completed
    # -------------------------------------------------------------------------
    source_job = (
        db.table("jobs")
        .select("id, status, user_id, portal_schema_version_id")
        .eq("id", str(body.document_id))
        .eq("user_id", str(user.id))
        .limit(1)
        .execute()
    )
    
    if not source_job.data:
        raise NotFoundException(f"Document {body.document_id} not found")
    
    source = source_job.data[0]
    
    if source["status"] != "completed":
        raise JobNotCompleteException(
            f"Document {body.document_id} is not ready for adaptation",
            details={"current_status": source["status"]},
        )
    
    # -------------------------------------------------------------------------
    # 2. Verify target portal schema exists
    # -------------------------------------------------------------------------
    schema_result = (
        db.table("portal_schemas")
        .select("id, name, schema_definition")
        .eq("name", body.portal_id)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )
    
    if not schema_result.data:
        raise SchemaNotFoundException(
            f"Portal schema '{body.portal_id}' not found or not active"
        )
    
    portal_schema = schema_result.data[0]
    
    # -------------------------------------------------------------------------
    # 3. Create adaptation job
    # -------------------------------------------------------------------------
    job_data = {
        "user_id": str(user.id),
        "status": "pending",
        "portal_schema_version_id": portal_schema["id"],
        "input_metadata": {
            "source_job_id": str(body.document_id),
            "target_portal": body.portal_id,
            "mode": "adapt",
            "correlation_id": correlation_id,
        },
    }
    
    try:
        job_result = db.table("jobs").insert(job_data).execute()
    except APIError as e:
        logger.error("Failed to create adaptation job", extra={"error": str(e)})
        raise InternalException("Failed to create adaptation job")
    
    if not job_result.data:
        raise InternalException("Failed to create adaptation job")
    
    job = job_result.data[0]
    job_id = UUID(job["id"])
    
    logger.info(
        "Adaptation job created",
        extra={
            "job_id": str(job_id),
            "source_job_id": str(body.document_id),
            "target_portal": body.portal_id,
            "correlation_id": correlation_id,
        },
    )
    
    # -------------------------------------------------------------------------
    # 4. Submit to Camber for processing
    # -------------------------------------------------------------------------
    camber_payload = {
        "job_id": str(job_id),
        "user_id": str(user.id),
        "mode": "adapt",
        "source_job_id": str(body.document_id),
        "portal_schema_id": str(portal_schema["id"]),
        "portal_schema_name": body.portal_id,
        "schema_definition": portal_schema.get("schema_definition", {}),
        "correlation_id": correlation_id,
    }
    
    try:
        camber_job_id = await camber.submit_job(job_id=job_id, payload=camber_payload)
    except CamberException as e:
        logger.error(
            "Camber submission failed for adaptation",
            extra={"job_id": str(job_id), "error": e.message},
        )
        try:
            transition_job_state(
                job_id=job_id,
                new_state="failed",
                payload={
                    "code": "CAMBER_SUBMISSION_FAILED",
                    "message": "Failed to submit adaptation job",
                },
            )
        except Exception:
            pass
        raise InternalException("Failed to submit adaptation job")
    
    # -------------------------------------------------------------------------
    # 5. Transition to processing
    # -------------------------------------------------------------------------
    try:
        transition_job_state(job_id=job_id, new_state="processing", camber_job_id=camber_job_id)
    except Exception as e:
        logger.error("Failed to transition adaptation job", extra={"error": str(e)})
    
    return AdaptResponse(job_id=job_id, status="processing")


@router.get("/{job_id}", response_model=AdaptOutputResponse)
async def get_adapt_status(
    job_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    packaging: Annotated[PackagingService, Depends(get_packaging_service)],
) -> AdaptOutputResponse:
    """
    Get adaptation job status and download URL if complete.
    """
    db = get_db_client()
    
    result = (
        db.table("jobs")
        .select("id, status, user_id, error_details, completed_at")
        .eq("id", str(job_id))
        .eq("user_id", str(user.id))
        .limit(1)
        .execute()
    )
    
    if not result.data:
        raise NotFoundException(f"Adaptation job {job_id} not found")
    
    job = result.data[0]
    
    # Get download URL if completed
    zip_url = None
    expires_at = None
    
    if job["status"] == "completed":
        url_result = packaging.get_output_download_url(job_id, user.id)
        if url_result:
            zip_url, expires_at = url_result
    
    # Format error
    error = None
    if job["error_details"]:
        error = {
            "code": job["error_details"].get("code", "UNKNOWN_ERROR"),
            "message": job["error_details"].get("message", "Adaptation failed"),
        }
    
    return AdaptOutputResponse(
        job_id=UUID(job["id"]),
        status=job["status"],
        zip_url=zip_url,
        expires_at=expires_at,
        error=error,
    )
