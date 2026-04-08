"""
GCS feedback store — archives reported raw uploads and pipeline metadata.

Raises on failure — callers (the feedback endpoint) decide to return 500
so the raw upload is NOT deleted and the user can retry.
"""
from __future__ import annotations

import json
import logging
from datetime import timedelta

import google.auth
import google.auth.transport.requests
from google.cloud import storage

logger = logging.getLogger(__name__)

_SIGNED_URL_EXPIRY_HOURS = 4

_gcs_client: storage.Client | None = None


def _get_client() -> storage.Client:
    global _gcs_client
    if _gcs_client is None:
        _gcs_client = storage.Client()
    return _gcs_client


def archive_raw_upload(raw_bytes: bytes, job_id: str, bucket_name: str) -> str:
    """
    Upload raw upload bytes to the feedback GCS bucket.

    Returns the GCS URI of the uploaded object.
    Raises on failure — do not catch here.
    """
    client = _get_client()
    bucket = client.bucket(bucket_name)
    path = f"{job_id}/raw.jpg"
    bucket.blob(path).upload_from_string(raw_bytes, content_type="image/jpeg")
    logger.info("[FEEDBACK] Archived raw upload for job %s", job_id)
    return f"gs://{bucket_name}/{path}"


def write_metadata(job_id: str, metadata: dict, bucket_name: str) -> None:
    """Write pipeline metadata snapshot JSON to GCS. Best-effort — does not raise."""
    try:
        client = _get_client()
        client.bucket(bucket_name).blob(f"{job_id}/metadata.json").upload_from_string(
            json.dumps(metadata), content_type="application/json"
        )
    except Exception as exc:
        logger.warning("[FEEDBACK] Failed to write metadata for job %s: %s", job_id, exc)


def generate_signed_url(gcs_uri: str, bucket_name: str) -> str:
    """
    Generate a v4 signed URL for a GCS object. Valid for 4 hours.

    On Cloud Run, Compute Engine credentials carry only a token — no private key —
    so blob.generate_signed_url() raises AttributeError if called without explicit
    credentials. We pass service_account_email + access_token so the library uses
    the IAM signBlob API instead of local key signing.

    Args:
        gcs_uri: Full GCS URI (gs://bucket/path) or just the object path.
        bucket_name: The GCS bucket name.
    """
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    auth_request = google.auth.transport.requests.Request()
    credentials.refresh(auth_request)

    client = _get_client()
    blob_name = gcs_uri.removeprefix(f"gs://{bucket_name}/")
    blob = client.bucket(bucket_name).blob(blob_name)
    return blob.generate_signed_url(
        expiration=timedelta(hours=_SIGNED_URL_EXPIRY_HOURS),
        method="GET",
        version="v4",
        service_account_email=credentials.service_account_email,
        access_token=credentials.token,
    )
