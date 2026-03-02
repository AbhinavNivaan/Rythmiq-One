"""
Cloud Run client service.
Owns: Job submission to Cloud Run worker and result retrieval.

Implements the same interface as CamberService:
- submit_job(job_id, payload) -> worker_job_id
- get_job_status(worker_job_id) -> status dict

Unlike Camber's async workflow (submit → webhook callback), Cloud Run executes
synchronously: submit blocks until result is ready, then returns JSON response.
This eliminates the need for webhook callbacks, ngrok, and async polling.
"""

import json
import logging
from typing import Any
from uuid import UUID

import httpx

from app.api.config import Settings, get_settings
from app.api.errors import CamberException, CamberTimeoutException

logger = logging.getLogger(__name__)

# Timeouts (seconds)
# Cloud Run jobs are typically 13-15s (processing) + 5-15s (cold start)
# Set to 120s (2 minutes) to allow for cold starts + processing + network overhead
CONNECT_TIMEOUT = 5.0
READ_TIMEOUT = 120.0  # Must be large enough for full processing + cold start
WRITE_TIMEOUT = 30.0


class CloudRunClient:
    """
    Synchronous client for Cloud Run worker.
    
    Cloud Run is treated as untrusted stateless compute.
    All responses must be validated by the caller.
    
    Key difference from Camber:
    - POST /process blocks until completion
    - No webhook callbacks
    - Result is returned directly in HTTP response
    - No polling needed
    
    Interface compatibility:
    - submit_job() — POST to Cloud Run, wait for result, return status
    - get_job_status() — Return cached result (or error if lost)
    
    Since Cloud Run blocks until completion, there's no "pending" state.
    Job is either "completed" or "failed".
    """

    def __init__(self, settings: Settings | None = None):
        self._settings = settings or get_settings()
        self._client: httpx.AsyncClient | None = None
        self._fallback_client: Any | None = None
        # Cache job results (key: cloud_run_job_id, value: full response)
        # In production, this would be persisted to Redis/database
        self._result_cache: dict[str, dict[str, Any]] = {}

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            headers: dict[str, str] = {
                "Content-Type": "application/json",
            }
            
            # Optional: Add API key auth if CLOUD_RUN_API_KEY is set
            if hasattr(self._settings, 'cloud_run_api_key') and self._settings.cloud_run_api_key:
                headers["Authorization"] = f"Bearer {self._settings.cloud_run_api_key}"
            
            self._client = httpx.AsyncClient(
                base_url=self._settings.cloud_run_worker_url.rstrip('/'),
                headers=headers,
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
        Submit a job to Cloud Run and wait for completion.
        
        This is a synchronous operation:
        1. POST payload to /process
        2. Block until Cloud Run returns result (13-15s + cold start)
        3. Return Cloud Run result wrapped as job status
        
        Args:
            job_id: Internal job UUID for tracing
            payload: Complete job payload
            
        Returns:
            Cloud Run worker job ID (same as input job_id for simplicity)
            
        Raises:
            CamberException: API call failed or worker returned error
            CamberTimeoutException: Request timed out
        """
        client = await self._get_client()
        cloud_run_job_id = str(job_id)

        logger.info(
            "Cloud Run job submitted",
            extra={
                "job_id": str(job_id),
                "cloud_run_worker_url": self._settings.cloud_run_worker_url,
            },
        )

        try:
            # POST payload to /process endpoint
            response = await client.post("/process", json=payload)
            response.raise_for_status()
            
            result = response.json()
            
            # Validate response structure
            if not isinstance(result, dict):
                logger.error(
                    "Cloud Run returned non-dict response",
                    extra={
                        "job_id": str(job_id),
                        "response_type": type(result).__name__,
                    },
                )
                raise CamberException(
                    "Cloud Run returned invalid response format",
                    details={"job_id": str(job_id)},
                )
            
            # Cache the result for later retrieval via get_job_status()
            self._result_cache[cloud_run_job_id] = result
            
            # Check if worker reported success or failure
            if result.get("success") is False:
                logger.warning(
                    "Cloud Run worker reported failure",
                    extra={
                        "job_id": str(job_id),
                        "error": result.get("error"),
                    },
                )
                # Return the job_id anyway - caller will query status and get the error
            else:
                logger.info(
                    "Cloud Run job completed successfully",
                    extra={
                        "job_id": str(job_id),
                        "cloud_run_job_id": cloud_run_job_id,
                    },
                )
            
            return cloud_run_job_id

        except httpx.TimeoutException as e:
            logger.error(
                "Cloud Run request timed out",
                extra={"job_id": str(job_id), "error": str(e)},
            )
            raise CamberTimeoutException(
                "Cloud Run request timed out",
                details={"job_id": str(job_id)},
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (401, 403) and self._settings.service_env != "prod":
                logger.warning(
                    "Cloud Run auth denied in non-prod, falling back to local mock backend",
                    extra={
                        "job_id": str(job_id),
                        "status_code": e.response.status_code,
                        "service_env": self._settings.service_env,
                    },
                )
                if self._fallback_client is None:
                    from app.api.services.mock_camber_client import MockCamberClient
                    self._fallback_client = MockCamberClient(self._settings)
                return await self._fallback_client.submit_job(job_id=job_id, payload=payload)

            logger.error(
                "Cloud Run HTTP error",
                extra={
                    "job_id": str(job_id),
                    "status_code": e.response.status_code,
                    "response_body": e.response.text[:500],
                },
            )
            raise CamberException(
                f"Cloud Run API error: {e.response.status_code}",
                details={
                    "job_id": str(job_id),
                    "status_code": e.response.status_code,
                },
            )
        except httpx.RequestError as e:
            if self._settings.service_env != "prod":
                logger.warning(
                    "Cloud Run request failed in non-prod, falling back to local mock backend",
                    extra={"job_id": str(job_id), "service_env": self._settings.service_env},
                )
                if self._fallback_client is None:
                    from app.api.services.mock_camber_client import MockCamberClient
                    self._fallback_client = MockCamberClient(self._settings)
                return await self._fallback_client.submit_job(job_id=job_id, payload=payload)

            logger.error(
                "Cloud Run request failed",
                extra={"job_id": str(job_id), "error": str(e)},
            )
            raise CamberException(
                "Failed to connect to Cloud Run worker",
                details={"job_id": str(job_id)},
            )

    async def get_job_status(self, cloud_run_job_id: str) -> dict[str, Any]:
        """
        Get status of a Cloud Run job.
        
        Since Cloud Run blocks until completion, there are only two states:
        1. Completed (success=true with output)
        2. Failed (success=false with error)
        
        This returns the cached result from submit_job(). In a distributed system,
        you'd query a database instead.
        
        Args:
            cloud_run_job_id: Cloud Run job ID
            
        Returns:
            Status dict with format:
            {
                "success": bool,
                "job_id": str,
                "status": "completed" | "failed",
                "output": dict | None,
                "error": dict | None,
                "metrics": dict | None,
            }
            
        Raises:
            CamberException: Job not found or other error
        """
        # Check cache first
        if cloud_run_job_id in self._result_cache:
            cached_result = self._result_cache[cloud_run_job_id]
            
            # Normalize to match Camber status format
            return {
                "status": "completed" if cached_result.get("success") else "failed",
                "job_id": cached_result.get("job_id"),
                "success": cached_result.get("success"),
                "output": cached_result.get("output"),
                "error": cached_result.get("error"),
                "metrics": cached_result.get("metrics"),
            }
        
        # Not in cache - either job not submitted yet, or cache was cleared
        logger.warning(
            "Cloud Run job not found in cache",
            extra={"cloud_run_job_id": cloud_run_job_id},
        )
        raise CamberException(
            "Cloud Run job not found",
            details={"cloud_run_job_id": cloud_run_job_id},
        )

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
