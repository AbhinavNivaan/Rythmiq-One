"""
DigitalOcean Spaces client for Camber CPU worker.

Worker-specific implementation that:
- Downloads raw artifacts from signed URLs OR direct paths (EXACTLY ONE)
- Uploads master and preview artifacts
- No retries, no async, no multipart, no caching

Environment Variables Required:
    SPACES_ENDPOINT  - e.g., "https://nyc3.digitaloceanspaces.com"
    SPACES_REGION    - e.g., "nyc3"
    SPACES_BUCKET    - e.g., "rythmiq-production"
    SPACES_KEY       - Worker access key (read raw, write master/output)
    SPACES_SECRET    - Worker secret key
"""

from __future__ import annotations

import io
import os
from dataclasses import dataclass
from typing import Literal, Optional
from urllib.parse import urlparse

import boto3
import requests
from botocore.config import Config
from botocore.exceptions import ClientError

from errors import (
    WorkerError,
    ErrorCode,
    ProcessingStage,
    fetch_failed,
    upload_failed,
)


# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class SpacesConfig:
    """Immutable configuration for Spaces client."""
    endpoint: str
    region: str
    bucket: str
    access_key: str
    secret_key: str
    
    @staticmethod
    def from_env() -> SpacesConfig:
        """Load configuration from environment variables."""
        required = {
            'SPACES_ENDPOINT': os.environ.get('SPACES_ENDPOINT'),
            'SPACES_REGION': os.environ.get('SPACES_REGION'),
            'SPACES_BUCKET': os.environ.get('SPACES_BUCKET'),
            'SPACES_KEY': os.environ.get('SPACES_KEY'),
            'SPACES_SECRET': os.environ.get('SPACES_SECRET'),
        }
        
        missing = [k for k, v in required.items() if not v]
        if missing:
            raise ValueError(f"Missing environment variables: {', '.join(missing)}")
        
        return SpacesConfig(
            endpoint=required['SPACES_ENDPOINT'],
            region=required['SPACES_REGION'],
            bucket=required['SPACES_BUCKET'],
            access_key=required['SPACES_KEY'],
            secret_key=required['SPACES_SECRET'],
        )
    
    @staticmethod
    def from_storage_spec(
        endpoint: str,
        region: str,
        bucket: str,
    ) -> SpacesConfig:
        """Create config from storage spec + env credentials."""
        access_key = os.environ.get('SPACES_KEY')
        secret_key = os.environ.get('SPACES_SECRET')
        
        if not access_key or not secret_key:
            raise ValueError("Missing SPACES_KEY or SPACES_SECRET environment variables")
        
        return SpacesConfig(
            endpoint=endpoint,
            region=region,
            bucket=bucket,
            access_key=access_key,
            secret_key=secret_key,
        )


# -----------------------------------------------------------------------------
# Artifact Source Validation
# -----------------------------------------------------------------------------

class ArtifactSourceError(ValueError):
    """Raised when artifact source specification is ambiguous."""
    pass


def validate_artifact_source(
    artifact_url: Optional[str],
    raw_path: Optional[str]
) -> Literal["url", "path"]:
    """
    Validate that exactly one artifact source is provided.
    
    This prevents the silent footgun of having ambiguous artifact sources.
    
    Args:
        artifact_url: Pre-signed URL for artifact download (optional)
        raw_path: Direct Spaces path for artifact download (optional)
        
    Returns:
        'url' if artifact_url provided, 'path' if raw_path provided
        
    Raises:
        ArtifactSourceError: If both or neither source is provided
    """
    has_url = artifact_url is not None and str(artifact_url).strip() != ''
    has_path = raw_path is not None and str(raw_path).strip() != ''
    
    if has_url and has_path:
        raise ArtifactSourceError(
            "Both artifact_url and raw_path provided. Specify exactly one."
        )
    
    if not has_url and not has_path:
        raise ArtifactSourceError(
            "Neither artifact_url nor raw_path provided. Specify exactly one."
        )
    
    return "url" if has_url else "path"


# -----------------------------------------------------------------------------
# Worker Spaces Client
# -----------------------------------------------------------------------------

class WorkerSpacesClient:
    """
    Synchronous Spaces client for Camber CPU worker.
    
    Capabilities:
    - Download from URL (signed) or path (direct)
    - Upload to master/
    - Upload to output/
    
    No retries. No async. No caching. No threads.
    """
    
    def __init__(self, config: SpacesConfig):
        self._config = config
        self._client = boto3.client(
            's3',
            endpoint_url=config.endpoint,
            region_name=config.region,
            aws_access_key_id=config.access_key,
            aws_secret_access_key=config.secret_key,
            config=Config(
                signature_version='s3v4',
                s3={'addressing_style': 'path'},
                connect_timeout=30,
                read_timeout=60,
            ),
        )
    
    def download_from_url(self, url: str, timeout: int = 60) -> bytes:
        """
        Download artifact from a signed URL.
        
        Args:
            url: Pre-signed URL for artifact download
            timeout: Request timeout in seconds
            
        Returns:
            Raw bytes of artifact
            
        Raises:
            WorkerError: If download fails
        """
        try:
            response = requests.get(url, timeout=timeout, stream=True)
            response.raise_for_status()
            
            # Read into memory
            data = io.BytesIO()
            for chunk in response.iter_content(chunk_size=8192):
                data.write(chunk)
            
            return data.getvalue()
            
        except requests.Timeout:
            raise WorkerError(
                code=ErrorCode.FETCH_TIMEOUT,
                stage=ProcessingStage.FETCH,
                message=f"Timeout downloading from URL: {timeout}s exceeded",
            )
        except requests.RequestException as e:
            raise fetch_failed(f"HTTP error: {str(e)}")
    
    def download_from_path(self, path: str) -> bytes:
        """
        Download artifact by direct Spaces path.
        
        Args:
            path: Storage path (e.g., raw/{user_id}/{job_id}/file.jpg)
            
        Returns:
            Raw bytes of artifact
            
        Raises:
            WorkerError: If download fails
        """
        try:
            response = self._client.get_object(
                Bucket=self._config.bucket,
                Key=path,
            )
            return response['Body'].read()
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            
            if error_code == 'NoSuchKey':
                raise WorkerError(
                    code=ErrorCode.ARTIFACT_NOT_FOUND,
                    stage=ProcessingStage.FETCH,
                    message=f"Artifact not found: {path}",
                )
            elif error_code == 'AccessDenied':
                raise WorkerError(
                    code=ErrorCode.ARTIFACT_ACCESS_DENIED,
                    stage=ProcessingStage.FETCH,
                    message=f"Access denied to artifact: {path}",
                )
            else:
                raise fetch_failed(f"S3 error ({error_code}): {str(e)}")
        except Exception as e:
            raise fetch_failed(f"Unexpected error: {str(e)}")
    
    def download(
        self,
        source: Literal["url", "path"],
        artifact_url: Optional[str],
        raw_path: Optional[str],
    ) -> bytes:
        """
        Download artifact from the appropriate source.
        
        Args:
            source: 'url' or 'path' indicating which source to use
            artifact_url: Pre-signed URL (used if source='url')
            raw_path: Direct path (used if source='path')
            
        Returns:
            Raw bytes of artifact
        """
        if source == "url":
            if not artifact_url:
                raise fetch_failed("artifact_url is required when source='url'")
            return self.download_from_url(artifact_url)
        else:
            if not raw_path:
                raise fetch_failed("raw_path is required when source='path'")
            return self.download_from_path(raw_path)
    
    def upload_master(
        self,
        data: bytes,
        user_id: str,
        job_id: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        """
        Upload master document to Spaces.
        
        Args:
            data: Master document bytes (encrypted)
            user_id: User UUID
            job_id: Job UUID
            content_type: MIME type of the content
            
        Returns:
            Storage path: master/{user_id}/{job_id}/{job_id}.enc
            
        Raises:
            WorkerError: If upload fails
        """
        path = f"master/{user_id}/{job_id}/{job_id}.enc"
        
        try:
            self._client.put_object(
                Bucket=self._config.bucket,
                Key=path,
                Body=data,
                ContentType=content_type,
            )
            return path
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            raise upload_failed(f"Failed to upload master ({error_code}): {str(e)}")
        except Exception as e:
            raise upload_failed(f"Unexpected error uploading master: {str(e)}")
    
    def upload_preview(
        self,
        data: bytes,
        user_id: str,
        job_id: str,
        content_type: str = "image/jpeg",
    ) -> str:
        """
        Upload preview image to Spaces.
        
        Args:
            data: Preview image bytes
            user_id: User UUID
            job_id: Job UUID
            content_type: MIME type of the content
            
        Returns:
            Storage path: output/{user_id}/{job_id}/preview.jpg
            
        Raises:
            WorkerError: If upload fails
        """
        path = f"output/{user_id}/{job_id}/preview.jpg"
        
        try:
            self._client.put_object(
                Bucket=self._config.bucket,
                Key=path,
                Body=data,
                ContentType=content_type,
            )
            return path
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            raise upload_failed(f"Failed to upload preview ({error_code}): {str(e)}")
        except Exception as e:
            raise upload_failed(f"Unexpected error uploading preview: {str(e)}")


def create_client_from_env() -> WorkerSpacesClient:
    """Create WorkerSpacesClient from environment variables."""
    config = SpacesConfig.from_env()
    return WorkerSpacesClient(config)


def create_client_from_spec(
    endpoint: str,
    region: str,
    bucket: str,
) -> WorkerSpacesClient:
    """Create WorkerSpacesClient from storage spec + env credentials."""
    config = SpacesConfig.from_storage_spec(endpoint, region, bucket)
    return WorkerSpacesClient(config)


# Re-export for worker usage
__all__ = [
    'WorkerSpacesClient',
    'SpacesConfig',
    'create_client_from_env',
    'create_client_from_spec',
    'validate_artifact_source',
    'ArtifactSourceError',
]
