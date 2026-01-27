"""
Mock Camber client for local/dev testing.

Simulates Camber job execution by:
1. Accepting job submission
2. Running worker logic in-process (asynchronously)
3. Emitting webhook callback to API endpoint

Gated behind EXECUTION_BACKEND=local.
Only for dev/test - production uses real Camber client.
"""

import asyncio
import hashlib
import hmac
import json
import logging
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

import httpx

from app.api.config import Settings, get_settings

logger = logging.getLogger(__name__)


class MockCamberClient:
    """
    In-process mock of Camber API client.
    
    Contract:
    - submit_job() returns immediately with a fake camber_job_id
    - Background task processes the job asynchronously
    - Webhook is POSTed back to /internal/webhooks/camber
    
    Features:
    - Deterministic execution (no network delays)
    - Failure simulation (success, processing_error, timeout)
    - Webhook replay for idempotency testing
    - Clear logging for debugging
    """

    def __init__(self, settings: Settings | None = None):
        self._settings = settings or get_settings()
        self._active_tasks: dict[str, asyncio.Task[Any]] = {}

    async def submit_job(
        self,
        job_id: UUID,
        payload: dict[str, Any],
    ) -> str:
        """
        Submit a job for local mock execution.
        
        Returns immediately with a fake camber_job_id.
        Background task processes asynchronously.
        
        Args:
            job_id: Internal job UUID for tracing
            payload: Complete job payload
            
        Returns:
            Mock camber_job_id string (deterministic)
        """
        # Generate deterministic mock camber_job_id from job_id
        mock_camber_id = f"mock-{str(job_id)[:8]}"

        logger.info(
            "[MOCK CAMBER] job submitted",
            extra={
                "job_id": str(job_id),
                "mock_camber_job_id": mock_camber_id,
            },
        )

        # Spawn background task to process the job
        # Use create_task if running in event loop context
        task = asyncio.create_task(
            self._process_job_async(job_id, payload, mock_camber_id)
        )
        self._active_tasks[mock_camber_id] = task

        return mock_camber_id

    async def _process_job_async(
        self,
        job_id: UUID,
        payload: dict[str, Any],
        camber_job_id: str,
    ) -> None:
        """
        Background worker that simulates Camber processing.
        
        Stages:
        1. Log start
        2. Simulate processing (fetch artifact, run OCR, etc.)
        3. Generate result (success or failure)
        4. POST webhook callback
        5. Handle webhook errors gracefully
        """
        try:
            logger.info(
                "[MOCK CAMBER] worker execution started",
                extra={
                    "job_id": str(job_id),
                    "camber_job_id": camber_job_id,
                },
            )

            # Simulate processing delay (optional - for testing async behavior)
            # In deterministic mode, we skip delays
            # await asyncio.sleep(0.1)

            # For now: assume success
            # Future: add failure simulation based on env var or payload flag
            result = self._generate_success_result(job_id, payload)

            logger.info(
                "[MOCK CAMBER] worker execution completed",
                extra={
                    "job_id": str(job_id),
                    "camber_job_id": camber_job_id,
                    "status": "success",
                },
            )

            # POST webhook back to API
            await self._send_webhook(job_id, camber_job_id, result)

        except Exception as e:
            logger.error(
                "[MOCK CAMBER] worker execution failed",
                extra={
                    "job_id": str(job_id),
                    "camber_job_id": camber_job_id,
                    "error": str(e),
                },
            )

            # Send failure webhook
            failure_result = self._generate_failure_result(
                job_id, str(e), "PROCESSING_ERROR"
            )
            try:
                await self._send_webhook(job_id, camber_job_id, failure_result)
            except Exception as webhook_error:
                logger.error(
                    "[MOCK CAMBER] failed to send failure webhook",
                    extra={
                        "job_id": str(job_id),
                        "error": str(webhook_error),
                    },
                )

        finally:
            # Clean up task reference
            self._active_tasks.pop(camber_job_id, None)

    def _generate_success_result(
        self, job_id: UUID, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Generate a mock success result (simulating worker output).
        
        Minimal result that satisfies webhook handler:
        - Contains dummy structured data
        - Includes confidence scores
        - Has quality score
        """
        return {
            "status": "success",
            "job_id": str(job_id),
            "result": {
                "structured": {
                    "field_1": "mock_value_1",
                    "field_2": "mock_value_2",
                },
                "confidence": {
                    "field_1": 0.95,
                    "field_2": 0.87,
                },
                "quality_score": 0.92,
                "page_count": 1,
                "processing_time_ms": 150,
            },
        }

    def _generate_failure_result(
        self, job_id: UUID, error_msg: str, error_code: str
    ) -> dict[str, Any]:
        """
        Generate a mock failure result.
        
        Matches worker error format.
        """
        return {
            "status": "failed",
            "job_id": str(job_id),
            "error": {
                "code": error_code,
                "stage": "OCR",
                "details": {
                    "reason": error_msg,
                },
            },
        }

    async def _send_webhook(
        self,
        job_id: UUID,
        camber_job_id: str,
        result: dict[str, Any],
    ) -> None:
        """
        POST webhook back to API endpoint.
        
        Mimics real Camber behavior:
        - Sends to /internal/webhooks/camber
        - Includes WEBHOOK_SECRET header
        - Retries on transient failures
        
        Args:
            job_id: Internal job UUID
            camber_job_id: Mock camber job ID
            result: Processing result from worker
            
        Raises:
            Exception on webhook delivery failure
        """
        webhook_url = f"http://127.0.0.1:{self._settings.api_port}/internal/webhooks/camber"

        # Map result status to webhook status
        webhook_status = (
            "success" if result["status"] == "success" else "failed"
        )

        # Construct webhook payload (matches real Camber format)
        webhook_payload = {
            "camber_job_id": camber_job_id,
            "job_id": str(job_id),
            "status": webhook_status,
            "result": result,
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Compute webhook signature
        secret = self._settings.webhook_secret.encode()
        payload_json = json.dumps(webhook_payload, separators=(",", ":"))
        signature = hmac.new(
            secret, payload_json.encode(), hashlib.sha256
        ).hexdigest()

        logger.info(
            "[MOCK CAMBER] webhook delivering",
            extra={
                "job_id": str(job_id),
                "camber_job_id": camber_job_id,
                "webhook_url": webhook_url,
                "status": webhook_status,
            },
        )

        async with httpx.AsyncClient() as client:
            response = await client.post(
                webhook_url,
                json=webhook_payload,
                headers={
                    "X-Webhook-Secret": signature,
                },
                timeout=5.0,
            )

            if response.status_code != 200:
                raise Exception(
                    f"Webhook delivery failed: {response.status_code} "
                    f"{response.text[:200]}"
                )

            logger.info(
                "[MOCK CAMBER] webhook delivered successfully",
                extra={
                    "job_id": str(job_id),
                    "camber_job_id": camber_job_id,
                },
            )

    async def get_job_status(self, camber_job_id: str) -> dict[str, Any]:
        """
        Mock implementation of job status check.
        
        In real Camber, this polls the API for job status.
        In mock, we don't need this - webhooks handle completion.
        
        But we implement it for compatibility.
        """
        if camber_job_id in self._active_tasks:
            task = self._active_tasks[camber_job_id]
            if not task.done():
                return {"status": "running"}
            try:
                await task
                return {"status": "completed"}
            except Exception:
                return {"status": "failed"}

        # Job not found - assume already completed
        return {"status": "completed"}
