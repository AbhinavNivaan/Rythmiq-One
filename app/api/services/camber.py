"""
Camber service.
Owns: Job submission to Camber workers and status retrieval.
"""

import logging
from typing import Any
from uuid import UUID

import httpx

from app.api.config import Settings, get_settings
from app.api.errors import CamberException, CamberTimeoutException

logger = logging.getLogger(__name__)

# Timeouts (seconds)
CONNECT_TIMEOUT = 5.0
READ_TIMEOUT = 30.0
WRITE_TIMEOUT = 30.0


class CamberService:
    """
    Async client for Camber worker API.
    
    Camber is treated as untrusted stateless compute.
    All responses must be validated by the caller.
    """

    def __init__(self, settings: Settings | None = None):
        self._settings = settings or get_settings()
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._settings.camber_api_url,
                headers={
                    "Authorization": f"Bearer {self._settings.camber_api_key}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(
                    connect=CONNECT_TIMEOUT,
                    read=READ_TIMEOUT,
                    write=WRITE_TIMEOUT,
                    pool=5.0,
                ),
            )
        return self._client

    async def submit_job(
        self,
        job_id: UUID,
        payload: dict[str, Any],
    ) -> str:
        """
        Submit a job to Camber.
        
        Args:
            job_id: Internal job UUID for tracing
            payload: Complete job payload including input paths and metadata
            
        Returns:
            Camber job ID string
            
        Raises:
            CamberException: API call failed
            CamberTimeoutException: Request timed out
        """
        client = await self._get_client()

        # Build webhook URL if base URL is configured
        webhook_url = None
        if self._settings.webhook_base_url:
            webhook_url = f"{self._settings.webhook_base_url.rstrip('/')}/internal/webhooks/camber"

        request_payload = {
            "app": self._settings.camber_app_name,
            "input": payload,
            "metadata": {
                "job_id": str(job_id),
            },
        }
        
        # Include webhook configuration if URL is set
        if webhook_url:
            request_payload["webhook"] = {
                "url": webhook_url,
                "headers": {
                    "X-Webhook-Secret": self._settings.webhook_secret,
                },
            }

        try:
            response = await client.post("/jobs", json=request_payload)
            response.raise_for_status()
            data = response.json()

            # Camber may return id or job_id
            camber_job_id = data.get("id") or data.get("job_id")
            if not camber_job_id:
                logger.error(
                    "Camber response missing job ID",
                    extra={"job_id": str(job_id), "response": data},
                )
                raise CamberException(
                    "Camber returned invalid response",
                    details={"job_id": str(job_id)},
                )

            logger.info(
                "Camber job submitted",
                extra={
                    "job_id": str(job_id),
                    "camber_job_id": camber_job_id,
                },
            )
            return str(camber_job_id)

        except httpx.TimeoutException as e:
            logger.error(
                "Camber submission timed out",
                extra={"job_id": str(job_id), "error": str(e)},
            )
            raise CamberTimeoutException(
                "Camber request timed out",
                details={"job_id": str(job_id)},
            )
        except httpx.HTTPStatusError as e:
            logger.error(
                "Camber submission failed",
                extra={
                    "job_id": str(job_id),
                    "status_code": e.response.status_code,
                    "response_body": e.response.text[:500],
                },
            )
            raise CamberException(
                f"Camber API error: {e.response.status_code}",
                details={
                    "job_id": str(job_id),
                    "status_code": e.response.status_code,
                },
            )
        except httpx.RequestError as e:
            logger.error(
                "Camber request failed",
                extra={"job_id": str(job_id), "error": str(e)},
            )
            raise CamberException(
                "Failed to connect to Camber",
                details={"job_id": str(job_id)},
            )

    async def get_job_status(self, camber_job_id: str) -> dict[str, Any]:
        """
        Get status of a Camber job.
        
        Args:
            camber_job_id: Camber's job identifier
            
        Returns:
            Status dict with at minimum: {"status": "...", ...}
            
        Raises:
            CamberException: API call failed
            CamberTimeoutException: Request timed out
        """
        client = await self._get_client()

        try:
            response = await client.get(f"/jobs/{camber_job_id}")
            response.raise_for_status()
            data = response.json()

            logger.debug(
                "Camber job status retrieved",
                extra={"camber_job_id": camber_job_id, "status": data.get("status")},
            )
            return data

        except httpx.TimeoutException as e:
            logger.error(
                "Camber status check timed out",
                extra={"camber_job_id": camber_job_id, "error": str(e)},
            )
            raise CamberTimeoutException(
                "Camber status request timed out",
                details={"camber_job_id": camber_job_id},
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(
                    "Camber job not found",
                    extra={"camber_job_id": camber_job_id},
                )
                raise CamberException(
                    "Camber job not found",
                    details={"camber_job_id": camber_job_id, "status_code": 404},
                )
            logger.error(
                "Camber status check failed",
                extra={
                    "camber_job_id": camber_job_id,
                    "status_code": e.response.status_code,
                },
            )
            raise CamberException(
                f"Camber API error: {e.response.status_code}",
                details={
                    "camber_job_id": camber_job_id,
                    "status_code": e.response.status_code,
                },
            )
        except httpx.RequestError as e:
            logger.error(
                "Camber status request failed",
                extra={"camber_job_id": camber_job_id, "error": str(e)},
            )
            raise CamberException(
                "Failed to connect to Camber",
                details={"camber_job_id": camber_job_id},
            )

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None


# Singleton instance
_camber_service: CamberService | None = None


def get_camber_service() -> CamberService:
    """
    Factory: Get singleton CamberService instance.
    
    Returns:
    - MockCamberClient if EXECUTION_BACKEND=local
    - Real CamberService if EXECUTION_BACKEND=camber
    
    Gating:
    - NO conditionals scattered in code
    - ONE clean factory entry point
    - Interface-compatible (both implement submit_job, get_job_status)
    """
    global _camber_service
    if _camber_service is None:
        settings = get_settings()
        
        if settings.execution_backend.lower() == "local":
            logger.info(
                "[MOCK CAMBER] Using in-process mock client (EXECUTION_BACKEND=local)"
            )
            # Import here to avoid circular dependency at module load time
            from app.api.services.mock_camber_client import MockCamberClient
            _camber_service = MockCamberClient(settings)  # type: ignore
        else:
            logger.info(
                "[CAMBER] Using real Camber integration (EXECUTION_BACKEND=camber)"
            )
            _camber_service = CamberService(settings)
    
    return _camber_service
