"""
Storage service.
Owns: Signed URL generation and object operations for DigitalOcean Spaces.
"""

import logging
from datetime import datetime, timezone
from io import BytesIO
from typing import Iterator
from uuid import UUID

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.api.config import Settings, get_settings
from app.api.errors import StorageException

logger = logging.getLogger(__name__)

# Download URL expiry for output ZIPs (24 hours)
OUTPUT_DOWNLOAD_EXPIRY_SECONDS = 86400


class StorageService:
    def __init__(self, settings: Settings | None = None):
        self._settings = settings or get_settings()
        self._client = boto3.client(
            "s3",
            endpoint_url=self._settings.spaces_endpoint,
            region_name=self._settings.spaces_region,
            aws_access_key_id=self._settings.spaces_access_key,
            aws_secret_access_key=self._settings.spaces_secret_key,
            config=Config(signature_version="s3v4"),
        )

    def generate_upload_url(
        self,
        job_id: UUID,
        user_id: UUID,
        filename: str,
        mime_type: str,
    ) -> tuple[str, str, datetime]:
        """
        Generate a presigned URL for uploading a file.
        
        Returns:
            Tuple of (url, storage_path, expires_at)
        """
        storage_path = f"uploads/{user_id}/{job_id}/{filename}"
        expires_at = datetime.now(timezone.utc).timestamp() + self._settings.upload_url_expiry_seconds

        try:
            url = self._client.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": self._settings.spaces_bucket,
                    "Key": storage_path,
                    "ContentType": mime_type,
                },
                ExpiresIn=self._settings.upload_url_expiry_seconds,
            )
        except (BotoCoreError, ClientError) as e:
            logger.error("Failed to generate upload URL", extra={"error": str(e)})
            raise StorageException("Failed to generate upload URL")

        return url, storage_path, datetime.fromtimestamp(expires_at, tz=timezone.utc)

    def generate_download_url(
        self,
        storage_path: str,
        expiry_seconds: int | None = None,
        filename: str | None = None,
        content_type: str | None = None,
    ) -> tuple[str, datetime]:
        """
        Generate a presigned URL for downloading a file.

        Args:
            storage_path: S3 key
            expiry_seconds: Override default expiry
            filename: When provided, sets Content-Disposition: attachment so the
                      browser/client downloads with this filename instead of the
                      S3 key (e.g. "document.jpg" instead of "{job_id}.enc").
            content_type: When provided, overrides the stored Content-Type in the
                          response (e.g. "image/jpeg" for .enc files).

        Returns:
            Tuple of (url, expires_at)
        """
        expiry = expiry_seconds or self._settings.download_url_expiry_seconds
        expires_at = datetime.now(timezone.utc).timestamp() + expiry

        params: dict[str, str] = {
            "Bucket": self._settings.spaces_bucket,
            "Key": storage_path,
        }
        if filename:
            params["ResponseContentDisposition"] = f'attachment; filename="{filename}"'
        if content_type:
            params["ResponseContentType"] = content_type

        try:
            url = self._client.generate_presigned_url(
                "get_object",
                Params=params,
                ExpiresIn=expiry,
            )
        except (BotoCoreError, ClientError) as e:
            logger.error("Failed to generate download URL", extra={"error": str(e)})
            raise StorageException("Failed to generate download URL")

        return url, datetime.fromtimestamp(expires_at, tz=timezone.utc)

    def generate_output_download_url(
        self,
        user_id: UUID,
        job_id: UUID,
    ) -> tuple[str, datetime]:
        """
        Generate a presigned URL for downloading the output ZIP (24h expiry).
        """
        output_path = f"output/{user_id}/{job_id}.zip"
        return self.generate_download_url(output_path, expiry_seconds=OUTPUT_DOWNLOAD_EXPIRY_SECONDS)

    def fetch_object(self, storage_path: str) -> bytes:
        """
        Fetch an object's contents into memory.
        
        Args:
            storage_path: The S3 key
            
        Returns:
            Object contents as bytes
            
        Raises:
            StorageException: Object not found or fetch failed
        """
        try:
            response = self._client.get_object(
                Bucket=self._settings.spaces_bucket,
                Key=storage_path,
            )
            return response["Body"].read()
        except self._client.exceptions.NoSuchKey:
            logger.warning("Object not found", extra={"storage_path": storage_path})
            raise StorageException(
                "Object not found",
                details={"storage_path": storage_path},
            )
        except (BotoCoreError, ClientError) as e:
            logger.error("Failed to fetch object", extra={"storage_path": storage_path, "error": str(e)})
            raise StorageException("Failed to fetch object")

    def upload_object(
        self,
        storage_path: str,
        data: bytes | BytesIO,
        content_type: str = "application/octet-stream",
    ) -> None:
        """
        Upload an object to storage.
        
        Args:
            storage_path: The S3 key
            data: File contents (bytes or BytesIO)
            content_type: MIME type
            
        Raises:
            StorageException: Upload failed
        """
        # Convert BytesIO to bytes if needed
        if isinstance(data, BytesIO):
            data.seek(0)  # Reset to beginning
            body = data.read()
            logger.debug(
                "Converted BytesIO to bytes",
                extra={"storage_path": storage_path, "size_bytes": len(body)}
            )
        else:
            body = data
            logger.debug(
                "Using bytes directly",
                extra={"storage_path": storage_path, "size_bytes": len(body) if isinstance(body, bytes) else "unknown"}
            )
        
        try:
            logger.debug(
                "Starting S3 put_object",
                extra={
                    "storage_path": storage_path,
                    "bucket": self._settings.spaces_bucket,
                    "content_type": content_type,
                }
            )
            self._client.put_object(
                Bucket=self._settings.spaces_bucket,
                Key=storage_path,
                Body=body,
                ContentType=content_type,
            )
            logger.info(
                "Object uploaded successfully",
                extra={"storage_path": storage_path, "size_bytes": len(body) if isinstance(body, bytes) else "unknown"},
            )
        except (BotoCoreError, ClientError) as e:
            logger.error(
                "Failed to upload object to S3",
                extra={
                    "storage_path": storage_path,
                    "bucket": self._settings.spaces_bucket,
                    "error_type": type(e).__name__,
                    "error": str(e),
                    "error_code": getattr(e, 'response', {}).get('Error', {}).get('Code', 'unknown'),
                }
            )
            raise StorageException("Failed to upload object") from e

    def list_objects(self, prefix: str) -> Iterator[dict]:
        """
        List objects under a prefix.
        
        Args:
            prefix: S3 key prefix
            
        Yields:
            Object metadata dicts with 'Key', 'Size', etc.
        """
        try:
            paginator = self._client.get_paginator("list_objects_v2")
            for page in paginator.paginate(
                Bucket=self._settings.spaces_bucket,
                Prefix=prefix,
            ):
                for obj in page.get("Contents", []):
                    yield obj
        except (BotoCoreError, ClientError) as e:
            logger.error("Failed to list objects", extra={"prefix": prefix, "error": str(e)})
            raise StorageException("Failed to list objects")

    def object_exists(self, storage_path: str) -> bool:
        """Check if an object exists."""
        try:
            self._client.head_object(
                Bucket=self._settings.spaces_bucket,
                Key=storage_path,
            )
            return True
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "404":
                return False
            logger.error("Failed to check object existence", extra={"storage_path": storage_path, "error": str(e)})
            raise StorageException("Failed to check object existence")

    def delete_object(self, storage_path: str) -> None:
        """Delete a single object from storage."""
        try:
            self._client.delete_object(
                Bucket=self._settings.spaces_bucket,
                Key=storage_path,
            )
            logger.info("Object deleted", extra={"storage_path": storage_path})
        except (BotoCoreError, ClientError) as e:
            logger.error("Failed to delete object", extra={"storage_path": storage_path, "error": str(e)})
            raise StorageException("Failed to delete object")

    def delete_objects_by_prefix(self, prefix: str) -> None:
        """Delete all objects under a given prefix."""
        try:
            paginator = self._client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self._settings.spaces_bucket, Prefix=prefix):
                keys = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
                if keys:
                    self._client.delete_objects(
                        Bucket=self._settings.spaces_bucket,
                        Delete={"Objects": keys},
                    )
            logger.info("Objects deleted by prefix", extra={"prefix": prefix})
        except (BotoCoreError, ClientError) as e:
            logger.error("Failed to delete objects by prefix", extra={"prefix": prefix, "error": str(e)})
            raise StorageException("Failed to delete objects by prefix")


_storage_service: StorageService | None = None


def get_storage_service() -> StorageService:
    global _storage_service
    if _storage_service is None:
        _storage_service = StorageService()
    return _storage_service
