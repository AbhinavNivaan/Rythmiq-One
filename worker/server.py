#!/usr/bin/env python3
"""
Cloud Run HTTP Server for Rythmiq Worker.

This FastAPI application wraps the worker pipeline and exposes it via HTTP.
Designed to run on Google Cloud Run with all dependencies pre-baked in the Docker image.

Request Flow:
1. Receive POST /process with job payload
2. Execute worker pipeline (FETCH → QUALITY → ENHANCE → SCHEMA → UPLOAD)
3. Return JSON result

Health check: GET /health

Environment:
- PORT: (default 8080) HTTP port (Cloud Run requirement)
- DO_SPACES_ENDPOINT: DigitalOcean Spaces endpoint
- DO_SPACES_REGION: DO region (e.g., sgp1)
- DO_SPACES_BUCKET: Bucket name
- DO_SPACES_ACCESS_KEY: S3-compatible access key
- DO_SPACES_SECRET_KEY: S3-compatible secret key
"""

import json
import logging
import os
import sys
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# Add worker directory to path so we can import worker modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


from worker import (
    parse_payload,
    process_job,
)
from models import JobPayload, SuccessResult, FailureResult
from errors import WorkerError
from logging_utils import RedactingFormatter, setup_redacting_logger

# ============================================================================
# Logging
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": "%(message)s"}',
)
logger = logging.getLogger(__name__)

# Enable redacting formatter to prevent SEK and tokens from appearing in logs
root_logger = logging.getLogger()
for handler in root_logger.handlers:
    handler.setFormatter(
        RedactingFormatter(
            fmt='{"timestamp": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": "%(message)s"}',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    )
setup_redacting_logger(root_logger)
logger.info("SECURITY: Log redaction enabled - sensitive data will be filtered from all logs")

# ============================================================================
# FastAPI App
# ============================================================================

app = FastAPI(
    title="Rythmiq One Worker",
    version="1.0.0",
    description="Cloud Run HTTP worker for document processing pipeline",
)


# ============================================================================
# Request/Response Models
# ============================================================================

class ProcessRequest(BaseModel):
    """Incoming job payload for processing."""
    
    # All fields are forwarded directly to the worker pipeline
    # The worker will validate the payload structure
    class Config:
        extra = "allow"  # Allow any additional fields
        json_schema_extra = {
            "example": {
                "job_id": "550e8400-e29b-41d4-a716-446655440000",
                "artifact_source": {
                    "type": "spaces",
                    "endpoint": "https://rythmiq-one-artifacts.sgp1.digitaloceanspaces.com",
                    "bucket": "rythmiq-one-artifacts",
                    "region": "sgp1",
                    "path": "uploads/user123/image.jpg",
                    "access_key": "...",
                    "secret_key": "...",
                },
                "output_artifact_destination": {
                    "type": "spaces",
                    "endpoint": "https://rythmiq-one-artifacts.sgp1.digitaloceanspaces.com",
                    "bucket": "rythmiq-one-artifacts",
                    "region": "sgp1",
                    "path": "results/user123/job456.json",
                    "access_key": "...",
                    "secret_key": "...",
                },
                "portal": "neet",
                "quality_threshold": 0.80,
                "enhancement_options": {
                    "resize_max": 2048,
                    "color_correction": True,
                    "sharpen": True,
                },
            }
        }


class ProcessResponse(BaseModel):
    """Response from worker (either success or failure)."""
    
    success: bool
    job_id: str | None = None
    status: str | None = None
    output: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    metrics: dict[str, Any] | None = None


# ============================================================================
# Supabase Integration
# ============================================================================

async def _update_job_status_in_db(result: SuccessResult | FailureResult) -> None:
    """
    Update job status in Supabase after processing completes.
    
    Args:
        result: Processing result (SuccessResult or FailureResult)
    """
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    
    if not supabase_url or not supabase_key:
        logger.warning(
            "Supabase credentials not configured, skipping job status update",
            extra={"job_id": str(result.job_id)},
        )
        return
    
    try:
        from supabase import create_client
        from datetime import datetime, timezone
        
        client = create_client(supabase_url, supabase_key)
        
        # Determine status and prepare update payload
        if isinstance(result, SuccessResult):
            update_data = {
                "status": "completed",
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
        else:
            update_data = {
                "status": "failed",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "error_details": {
                    "code": result.error.code,
                    "message": result.error.message,
                    "stage": result.error.stage,
                    "details": result.error.details,
                },
            }
        
        # Update job in database
        client.table("jobs").update(update_data).eq("id", str(result.job_id)).execute()
        
        logger.info(
            "Job status updated in Supabase",
            extra={
                "job_id": str(result.job_id),
                "status": update_data["status"],
            },
        )
        
    except ImportError:
        logger.warning(
            "supabase package not installed, cannot update job status",
            extra={"job_id": str(result.job_id)},
        )
    except Exception as e:
        logger.error(
            f"Failed to update job status in Supabase: {str(e)}",
            extra={"job_id": str(result.job_id)},
        )


# ============================================================================
# Routes
# ============================================================================

@app.get("/health")
async def health_check() -> dict[str, str]:
    """
    Health check endpoint for Cloud Run liveness probe.
    
    Cloud Run uses this to verify the service is running and responsive.
    """
    logger.info("Health check request")
    return {"status": "ok", "service": "rythmiq-worker"}


@app.post("/process")
async def process_document(request: ProcessRequest) -> ProcessResponse:
    """
    Process a document through the full Rythmiq pipeline.
    
    Receives a job payload, executes:
    - FETCH: Download image from artifact source
    - QUALITY: Assess image quality
    - ENHANCE: Image enhancement (resize, color correction, sharpen)
    - SCHEMA: Adapt result to portal specification
    - UPLOAD: Upload result to destination
    
    Args:
        request: Job payload
        
    Returns:
        ProcessResponse: Result with success/output or error details
        
    Raises:
        HTTPException: If processing fails unrecoverably
    """
    logger.info(
        "Processing request received",
        extra={
            "job_id": request.__dict__.get("job_id", "unknown"),
        },
    )
    
    try:
        # Convert request to dict for worker processing
        payload_dict = request.dict()
        
        # Parse and validate payload
        try:
            parsed = parse_payload(json.dumps(payload_dict))
            job_payload = JobPayload.from_dict(parsed)
        except Exception as e:
            logger.error(f"Payload validation failed: {str(e)}")
            return ProcessResponse(
                success=False,
                job_id=payload_dict.get("job_id"),
                error={
                    "code": "PAYLOAD_INVALID",
                    "message": str(e),
                },
            )
        
        # Execute worker pipeline
        result = process_job(job_payload)
        
        # Update job status in Supabase
        await _update_job_status_in_db(result)
        
        # Return result (success or failure from pipeline)
        if isinstance(result, SuccessResult):
            result_dict = result.to_dict()
            return ProcessResponse(
                success=True,
                job_id=str(result.job_id),
                status="completed",
                output=result_dict,
                metrics=result.metrics.to_dict(),
            )
        elif isinstance(result, FailureResult):
            return ProcessResponse(
                success=False,
                job_id=str(result.job_id),
                status="failed",
                error=result.error.to_dict(),
            )
        else:
            # Unexpected result type
            logger.error(f"Unexpected result type: {type(result)}")
            return ProcessResponse(
                success=False,
                job_id=payload_dict.get("job_id"),
                error={
                    "code": "INTERNAL_ERROR",
                    "message": "Worker returned unexpected result type",
                },
            )
            
    except WorkerError as e:
        # Handled worker error
        logger.error(
            f"Worker error: {e.error.code}",
            extra={
                "job_id": request.__dict__.get("job_id", "unknown"),
                "error_code": e.error.code,
                "error_message": e.error.message,
            },
        )
        return ProcessResponse(
            success=False,
            job_id=request.__dict__.get("job_id"),
            error={
                "code": e.error.code,
                "message": e.error.message,
                "stage": e.error.stage,
                "details": e.error.details,
            },
        )
    except Exception as e:
        # Unexpected error
        logger.exception(
            f"Unexpected error in /process: {str(e)}",
            extra={
                "job_id": request.__dict__.get("job_id", "unknown"),
            },
        )
        raise HTTPException(
            status_code=500,
            detail="Internal server error",
        )


# ============================================================================
# Error Handlers
# ============================================================================

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all exception handler for unexpected errors."""
    logger.exception(f"Unhandled exception: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "Internal server error",
            },
        },
    )


# ============================================================================
# Startup
# ============================================================================

@app.on_event("startup")
async def startup() -> None:
    """Cloud Run startup hook."""
    port = os.getenv("PORT", "8080")
    logger.info(f"Rythmiq One Worker starting on port {port}")


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", "8080"))
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_config={
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": "%(message)s"}',
                },
            },
            "handlers": {
                "default": {
                    "formatter": "default",
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stdout",
                },
            },
            "root": {
                "level": "INFO",
                "handlers": ["default"],
            },
        },
    )
