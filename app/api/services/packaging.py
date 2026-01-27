"""
Packaging service.
Owns: In-memory ZIP creation for job outputs.
"""

import logging
import zipfile
from io import BytesIO
from typing import Any
from uuid import UUID

from app.api.errors import PackagingException
from app.api.services.storage import StorageService, get_storage_service

logger = logging.getLogger(__name__)


class PackagingService:
    """
    Handles packaging of worker output artifacts into downloadable ZIPs.
    
    CRITICAL: All ZIP operations are in-memory. Never write to disk.
    """

    def __init__(self, storage: StorageService | None = None):
        self._storage = storage or get_storage_service()

    def package_job_output(
        self,
        job_id: UUID,
        user_id: UUID,
        worker_result: dict[str, Any],
    ) -> str:
        """
        Package worker output artifacts into a ZIP and upload to output storage.
        
        This method is idempotent: if the ZIP already exists, it skips creation.
        
        Args:
            job_id: The job UUID
            user_id: The user UUID (for storage path)
            worker_result: The parsed worker stdout result containing artifact paths
            
        Returns:
            Storage path of the created ZIP
            
        Raises:
            PackagingException: Packaging or upload failed
        """
        output_path = f"output/{user_id}/{job_id}.zip"

        # Idempotency: check if ZIP already exists
        if self._storage.object_exists(output_path):
            logger.info(
                "Output ZIP already exists, skipping packaging",
                extra={"job_id": str(job_id), "output_path": output_path},
            )
            return output_path

        # Extract artifact paths from worker result
        artifact_paths = self._extract_artifact_paths(worker_result)

        if not artifact_paths:
            logger.warning(
                "No artifacts to package",
                extra={"job_id": str(job_id)},
            )
            # Create empty ZIP with metadata
            artifact_paths = []

        # Create ZIP in memory
        try:
            zip_buffer = self._create_zip(job_id, artifact_paths, worker_result)
        except Exception as e:
            logger.error(
                "Failed to create ZIP",
                extra={"job_id": str(job_id), "error": str(e)},
            )
            raise PackagingException(
                "Failed to create output package",
                details={"job_id": str(job_id)},
            )

        # Upload ZIP
        try:
            self._storage.upload_object(
                storage_path=output_path,
                data=zip_buffer,
                content_type="application/zip",
            )
        except Exception as e:
            logger.error(
                "Failed to upload ZIP",
                extra={"job_id": str(job_id), "output_path": output_path, "error": str(e)},
            )
            raise PackagingException(
                "Failed to upload output package",
                details={"job_id": str(job_id)},
            )

        logger.info(
            "Job output packaged successfully",
            extra={
                "job_id": str(job_id),
                "output_path": output_path,
                "artifact_count": len(artifact_paths),
            },
        )

        return output_path

    def _extract_artifact_paths(self, worker_result: dict[str, Any]) -> list[str]:
        """
        Extract storage paths of artifacts from worker result.
        
        Worker result shape (from Prompt 1.4 contract):
        {
            "status": "success",
            "output": {
                "artifacts": [
                    {"path": "...", "type": "...", "size": ...},
                    ...
                ],
                "portal_output": {...},
                "canonical_output": {...}
            }
        }
        """
        paths = []

        output = worker_result.get("output", {})
        artifacts = output.get("artifacts", [])

        for artifact in artifacts:
            if isinstance(artifact, dict) and "path" in artifact:
                paths.append(artifact["path"])
            elif isinstance(artifact, str):
                # Handle simple path strings
                paths.append(artifact)

        return paths

    def _create_zip(
        self,
        job_id: UUID,
        artifact_paths: list[str],
        worker_result: dict[str, Any],
    ) -> BytesIO:
        """
        Create an in-memory ZIP containing all artifacts.
        
        ZIP structure:
            /artifacts/
                - original files
            /metadata/
                - result.json (worker result)
        """
        import json

        zip_buffer = BytesIO()

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            # Add each artifact
            for path in artifact_paths:
                try:
                    content = self._storage.fetch_object(path)
                    # Use filename only in ZIP
                    filename = path.split("/")[-1]
                    zf.writestr(f"artifacts/{filename}", content)
                except Exception as e:
                    logger.warning(
                        "Failed to fetch artifact for packaging",
                        extra={"job_id": str(job_id), "path": path, "error": str(e)},
                    )
                    # Continue with other artifacts

            # Add metadata
            metadata = {
                "job_id": str(job_id),
                "worker_result": worker_result,
            }
            zf.writestr("metadata/result.json", json.dumps(metadata, indent=2))

        zip_buffer.seek(0)
        return zip_buffer

    def get_output_download_url(
        self,
        job_id: UUID,
        user_id: UUID,
    ) -> tuple[str, str] | None:
        """
        Get download URL for job output if it exists.
        
        Returns:
            Tuple of (download_url, expires_at_iso) or None if not ready
        """
        output_path = f"output/{user_id}/{job_id}.zip"

        if not self._storage.object_exists(output_path):
            return None

        url, expires_at = self._storage.generate_output_download_url(user_id, job_id)
        return url, expires_at.isoformat()


_packaging_service: PackagingService | None = None


def get_packaging_service() -> PackagingService:
    """Get singleton PackagingService instance."""
    global _packaging_service
    if _packaging_service is None:
        _packaging_service = PackagingService()
    return _packaging_service
