"""
Webhook routes.
Owns: Internal worker callbacks from Camber.

Camber is NOT TRUSTED. All webhook payloads are treated as untrusted input.
"""

import hmac
import logging
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request

from app.api.config import Settings, get_settings
from app.api.db import (
    get_service_db_client,
    transition_job_state,
    get_job_by_camber_id,
    TERMINAL_STATES,
)
from app.api.errors import (
    InvalidInputException,
    NotFoundException,
    StateTransitionException,
    WebhookAuthException,
)
from app.api.services.packaging import PackagingService, get_packaging_service
from .models import CamberWebhookRequest, WebhookResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/internal/webhooks", tags=["webhooks"])


def verify_webhook_secret(
    x_webhook_secret: Annotated[str | None, Header()] = None,
    settings: Settings = Depends(get_settings),
) -> bool:
    """
    Verify the webhook secret using constant-time comparison.
    
    Raises:
        WebhookAuthException: Secret missing or invalid
    """
    if not x_webhook_secret:
        logger.warning("Webhook request missing secret header")
        raise WebhookAuthException("Missing webhook secret")

    if not hmac.compare_digest(x_webhook_secret, settings.webhook_secret):
        logger.warning("Webhook request with invalid secret")
        raise WebhookAuthException("Invalid webhook secret")

    return True


@router.post("/camber", response_model=WebhookResponse)
async def webhook_camber(
    request: Request,
    body: CamberWebhookRequest,
    _auth: Annotated[bool, Depends(verify_webhook_secret)],
    packaging: Annotated[PackagingService, Depends(get_packaging_service)],
) -> WebhookResponse:
    """
    Handle Camber worker completion webhook.
    
    Expected payload:
    {
        "camber_job_id": "string",
        "job_id": "uuid",
        "status": "success | failed",
        "result": { ...worker stdout... }
    }
    
    Requirements:
    - Verify WEBHOOK_SECRET
    - Idempotent handling (safe to replay)
    - Accept only terminal states
    - Package outputs on success
    """
    correlation_id = getattr(request.state, "correlation_id", "unknown")

    logger.info(
        "Camber webhook received",
        extra={
            "camber_job_id": body.camber_job_id,
            "job_id": str(body.job_id),
            "status": body.status,
            "correlation_id": correlation_id,
        },
    )

    # -------------------------------------------------------------------------
    # 1. Validate webhook status (only accept terminal states)
    # -------------------------------------------------------------------------
    if body.status not in ("success", "failed"):
        logger.warning(
            "Invalid webhook status",
            extra={"status": body.status, "job_id": str(body.job_id)},
        )
        raise InvalidInputException(
            f"Invalid status: {body.status}. Expected 'success' or 'failed'."
        )

    # Map Camber status to internal status
    new_state = "completed" if body.status == "success" else "failed"

    # -------------------------------------------------------------------------
    # 2. Fetch job and verify ownership
    # -------------------------------------------------------------------------
    db = get_service_db_client()

    job_result = (
        db.table("jobs")
        .select("id, status, user_id, camber_job_id")
        .eq("id", str(body.job_id))
        .limit(1)
        .execute()
    )

    if not job_result.data:
        # Try lookup by camber_job_id as fallback
        if body.camber_job_id:
            job = get_job_by_camber_id(body.camber_job_id)
            if job:
                logger.info(
                    "Job found by camber_job_id",
                    extra={
                        "job_id": job["id"],
                        "camber_job_id": body.camber_job_id,
                    },
                )
            else:
                raise NotFoundException(f"Job {body.job_id} not found")
        else:
            raise NotFoundException(f"Job {body.job_id} not found")
    else:
        job = job_result.data[0]

    current_status = job["status"]
    job_id = UUID(job["id"])
    user_id = UUID(job["user_id"])

    # -------------------------------------------------------------------------
    # 3. Idempotency check: if already in terminal state, acknowledge silently
    # -------------------------------------------------------------------------
    if current_status in TERMINAL_STATES:
        logger.info(
            "Webhook received for already terminal job (idempotent)",
            extra={
                "job_id": str(job_id),
                "current_status": current_status,
                "requested_status": new_state,
                "correlation_id": correlation_id,
            },
        )
        return WebhookResponse(acknowledged=True)

    # -------------------------------------------------------------------------
    # 4. Prepare payload based on status
    # -------------------------------------------------------------------------
    transition_payload: dict[str, Any] | None = None

    if new_state == "failed":
        # Extract error details from worker result
        error_info = _extract_error_info(body.result)
        transition_payload = error_info

    # -------------------------------------------------------------------------
    # 5. Transition job state
    # -------------------------------------------------------------------------
    try:
        transition_job_state(
            job_id=job_id,
            new_state=new_state,
            payload=transition_payload,
        )
    except StateTransitionException as e:
        # Concurrent update or invalid transition
        logger.warning(
            "State transition rejected",
            extra={
                "job_id": str(job_id),
                "current_status": current_status,
                "requested_status": new_state,
                "error": e.message,
                "correlation_id": correlation_id,
            },
        )
        # Still acknowledge to prevent retries
        return WebhookResponse(acknowledged=True)

    logger.info(
        "Job state transitioned via webhook",
        extra={
            "job_id": str(job_id),
            "old_status": current_status,
            "new_status": new_state,
            "correlation_id": correlation_id,
        },
    )

    # -------------------------------------------------------------------------
    # 6. On success: package outputs
    # -------------------------------------------------------------------------
    if new_state == "completed" and body.result:
        try:
            output_path = packaging.package_job_output(
                job_id=job_id,
                user_id=user_id,
                worker_result=body.result,
            )
            logger.info(
                "Output packaged successfully",
                extra={
                    "job_id": str(job_id),
                    "output_path": output_path,
                    "correlation_id": correlation_id,
                },
            )

            # Store output metadata in job record
            try:
                db.table("jobs").update({
                    "output_metadata": {
                        "output_path": output_path,
                        "packaged": True,
                    }
                }).eq("id", str(job_id)).execute()
            except Exception as e:
                logger.error(
                    "Failed to update output metadata",
                    extra={"job_id": str(job_id), "error": str(e)},
                )

        except Exception as e:
            logger.error(
                "Failed to package output",
                extra={
                    "job_id": str(job_id),
                    "error": str(e),
                    "correlation_id": correlation_id,
                },
            )
            # Don't fail the webhook - job is still completed
            # Packaging can be retried later

    # -------------------------------------------------------------------------
    # 7. Persist worker result to documents table (if success)
    # -------------------------------------------------------------------------
    if new_state == "completed" and body.result:
        _persist_worker_output(db, job_id, user_id, body.result, correlation_id)

    return WebhookResponse(acknowledged=True)


def _extract_error_info(result: dict[str, Any] | None) -> dict[str, Any]:
    """Extract error information from worker result."""
    if not result:
        return {
            "code": "WORKER_ERROR",
            "message": "Worker failed without error details",
        }

    # Worker error format from Prompt 1.4
    error = result.get("error", {})
    if isinstance(error, dict):
        return {
            "code": error.get("code", "WORKER_ERROR"),
            "message": error.get("message", "Worker processing failed"),
            "details": error.get("details"),
        }

    # Fallback: use status message
    return {
        "code": "WORKER_ERROR",
        "message": str(error) if error else "Worker processing failed",
    }


def _persist_worker_output(
    db,
    job_id: UUID,
    user_id: UUID,
    result: dict[str, Any],
    correlation_id: str,
) -> None:
    """
    Persist worker output to the documents table.
    
    This is idempotent: if document already exists, update it.
    """
    try:
        output = result.get("output", {})
        portal_outputs = output.get("portal_output", {})
        canonical_output = output.get("canonical_output", {})

        doc_data = {
            "job_id": str(job_id),
            "user_id": str(user_id),
            "portal_outputs": portal_outputs if isinstance(portal_outputs, dict) else {"default": portal_outputs},
            "canonical_output": canonical_output,
        }

        # Upsert: try insert, update on conflict
        existing = (
            db.table("documents")
            .select("id")
            .eq("job_id", str(job_id))
            .limit(1)
            .execute()
        )

        if existing.data:
            db.table("documents").update({
                "portal_outputs": doc_data["portal_outputs"],
                "canonical_output": doc_data["canonical_output"],
            }).eq("job_id", str(job_id)).execute()
        else:
            db.table("documents").insert(doc_data).execute()

        logger.info(
            "Worker output persisted",
            extra={"job_id": str(job_id), "correlation_id": correlation_id},
        )

    except Exception as e:
        logger.error(
            "Failed to persist worker output",
            extra={
                "job_id": str(job_id),
                "error": str(e),
                "correlation_id": correlation_id,
            },
        )
        # Don't fail the webhook - this can be recovered


# Legacy endpoint for backwards compatibility
@router.post("/job-complete", response_model=WebhookResponse)
async def webhook_job_complete_legacy(
    request: Request,
    body: CamberWebhookRequest,
    _auth: Annotated[bool, Depends(verify_webhook_secret)],
    packaging: Annotated[PackagingService, Depends(get_packaging_service)],
) -> WebhookResponse:
    """Legacy endpoint. Redirects to /camber."""
    return await webhook_camber(request, body, _auth, packaging)
