"""
DigitalOcean Spaces storage client for Rythmiq One API.

Production-ready, synchronous, no retries, no caching.
All files are encrypted client-side before upload.

Environment Variables Required:
    SPACES_ENDPOINT  - e.g., "https://nyc3.digitaloceanspaces.com"
    SPACES_REGION    - e.g., "nyc3"
    SPACES_BUCKET    - e.g., "rythmiq-production"
    SPACES_KEY       - Access key ID
    SPACES_SECRET    - Secret access key
"""

import os
from dataclasses import dataclass

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

# Import shared path validation (SINGLE SOURCE OF TRUTH)
from shared.path_validation import (
    PathValidationError,
    validate_storage_path,
    validate_uuid,
    sanitize_filename,
    build_raw_path,
    build_master_path,
    build_output_path,
)

# Re-export for convenience
__all__ = [
    'PathValidationError',
    'validate_storage_path',
    'validate_uuid',
    'sanitize_filename',
    'build_raw_path',
    'build_master_path',
    'build_output_path',
    'SpacesConfig',
    'SpacesStorageError',
    'SpacesClient',
    'create_spaces_client',
]


# -----------------------------------------------------------------------------
# Spaces Client
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class SpacesConfig:
    """Immutable configuration for DigitalOcean Spaces client."""
    endpoint: str
    region: str
    bucket: str
    access_key: str
    secret_key: str
    
    @staticmethod
    def from_env() -> "SpacesConfig":
        """
        Load configuration from environment variables.
        
        Raises:
            ValueError: If any required variable is missing
        """
        required_vars = {
            'SPACES_ENDPOINT': os.environ.get('SPACES_ENDPOINT'),
            'SPACES_REGION': os.environ.get('SPACES_REGION'),
            'SPACES_BUCKET': os.environ.get('SPACES_BUCKET'),
            'SPACES_KEY': os.environ.get('SPACES_KEY'),
            'SPACES_SECRET': os.environ.get('SPACES_SECRET'),
        }
        
        missing = [k for k, v in required_vars.items() if not v]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
        
        return SpacesConfig(
            endpoint=required_vars['SPACES_ENDPOINT'],
            region=required_vars['SPACES_REGION'],
            bucket=required_vars['SPACES_BUCKET'],
            access_key=required_vars['SPACES_KEY'],
            secret_key=required_vars['SPACES_SECRET'],
        )


class SpacesStorageError(Exception):
    """Raised when a Spaces operation fails."""
    def __init__(self, operation: str, path: str, reason: str):
        self.operation = operation
        self.path = path
        self.reason = reason
        super().__init__(f"{operation} failed for '{path}': {reason}")


class SpacesClient:
    """
    Synchronous DigitalOcean Spaces client.
    
    - No retries
    - No caching
    - No global state
    - Creates fresh boto3 client on each instantiation
    
    Usage:
        config = SpacesConfig.from_env()
        client = SpacesClient(config)
        url = client.generate_upload_url("raw/user/job/file.enc", expires_in=300)
    """
    
    def __init__(self, config: SpacesConfig):
        """
        Initialize Spaces client with configuration.
        
        Args:
            config: Immutable Spaces configuration
        """
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
            ),
        )
    
    @property
    def bucket(self) -> str:
        """Return the configured bucket name."""
        return self._config.bucket
    
    def generate_upload_url(
        self,
        path: str,
        expires_in: int = 300,
        content_type: str = "application/octet-stream"
    ) -> str:
        """
        Generate a pre-signed PUT URL for uploading.
        
        Args:
            path: Storage path (e.g., "raw/user_id/job_id/timestamp_file.enc")
            expires_in: URL validity in seconds (default 300 = 5 minutes)
            content_type: Expected content type (default application/octet-stream)
            
        Returns:
            Pre-signed PUT URL
            
        Raises:
            PathValidationError: If path is invalid
            SpacesStorageError: If URL generation fails
        """
        validate_storage_path(path)
        
        try:
            url = self._client.generate_presigned_url(
                ClientMethod='put_object',
                Params={
                    'Bucket': self._config.bucket,
                    'Key': path,
                    'ContentType': content_type,
                },
                ExpiresIn=expires_in,
            )
            return url
        except ClientError as e:
            raise SpacesStorageError(
                operation="generate_upload_url",
                path=path,
                reason=str(e),
            )
    
    def generate_download_url(self, path: str, expires_in: int = 900) -> str:
        """
        Generate a pre-signed GET URL for downloading.
        
        Args:
            path: Storage path (e.g., "output/user_id/job_id/timestamp_output.zip.enc")
            expires_in: URL validity in seconds (default 900 = 15 minutes)
            
        Returns:
            Pre-signed GET URL
            
        Raises:
            PathValidationError: If path is invalid
            SpacesStorageError: If URL generation fails
        """
        validate_storage_path(path)
        
        try:
            url = self._client.generate_presigned_url(
                ClientMethod='get_object',
                Params={
                    'Bucket': self._config.bucket,
                    'Key': path,
                },
                ExpiresIn=expires_in,
            )
            return url
        except ClientError as e:
            raise SpacesStorageError(
                operation="generate_download_url",
                path=path,
                reason=str(e),
            )
    
    def upload_bytes(
        self,
        data: bytes,
        path: str,
        content_type: str = "application/octet-stream"
    ) -> None:
        """
        Upload bytes directly to Spaces (server-side upload).
        
        Used by workers to upload processed artifacts.
        
        Args:
            data: Bytes to upload
            path: Storage path
            content_type: MIME type (default application/octet-stream)
            
        Raises:
            PathValidationError: If path is invalid
            SpacesStorageError: If upload fails
        """
        validate_storage_path(path)
        
        try:
            self._client.put_object(
                Bucket=self._config.bucket,
                Key=path,
                Body=data,
                ContentType=content_type,
            )
        except ClientError as e:
            raise SpacesStorageError(
                operation="upload_bytes",
                path=path,
                reason=str(e),
            )
    
    def download_bytes(self, path: str) -> bytes:
        """
        Download bytes directly from Spaces (server-side download).
        
        Used by workers to fetch raw artifacts.
        
        Args:
            path: Storage path
            
        Returns:
            Downloaded bytes
            
        Raises:
            PathValidationError: If path is invalid
            SpacesStorageError: If download fails or object not found
        """
        validate_storage_path(path)
        
        try:
            response = self._client.get_object(
                Bucket=self._config.bucket,
                Key=path,
            )
            return response['Body'].read()
        except self._client.exceptions.NoSuchKey:
            raise SpacesStorageError(
                operation="download_bytes",
                path=path,
                reason="Object not found",
            )
        except ClientError as e:
            raise SpacesStorageError(
                operation="download_bytes",
                path=path,
                reason=str(e),
            )
    
    def exists(self, path: str) -> bool:
        """
        Check if an object exists at the given path.
        
        Args:
            path: Storage path
            
        Returns:
            True if object exists, False otherwise
            
        Raises:
            PathValidationError: If path is invalid
            SpacesStorageError: If check fails (not including 404)
        """
        validate_storage_path(path)
        
        try:
            self._client.head_object(
                Bucket=self._config.bucket,
                Key=path,
            )
            return True
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            if error_code == '404':
                return False
            raise SpacesStorageError(
                operation="exists",
                path=path,
                reason=str(e),
            )


# -----------------------------------------------------------------------------
# Factory Function
# -----------------------------------------------------------------------------

def create_spaces_client() -> SpacesClient:
    """
    Create a new SpacesClient from environment variables.
    
    Returns:
        Configured SpacesClient instance
        
    Raises:
        ValueError: If required environment variables are missing
    """
    config = SpacesConfig.from_env()
    return SpacesClient(config)
