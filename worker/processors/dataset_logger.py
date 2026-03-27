"""
Dataset logger — writes confirmed detection samples to GCS for model training.

Every call is fire-and-forget: exceptions are caught and logged but never
propagated. A GCS write failure must never affect job processing.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from google.cloud import storage

logger = logging.getLogger(__name__)

_DATASET_BUCKET = "rythmiq-one-dataset"
_PREFIX = "detection"


def log_detection_sample(
    image_bytes: bytes,
    quad: list[list[float]],
    document_type: str,
    job_id: str,
) -> None:
    """
    Write image + confirmed quad to GCS.

    Paths:
      gs://rythmiq-one-dataset/detection/{job_id}/image.jpg
      gs://rythmiq-one-dataset/detection/{job_id}/quad.json

    Errors are swallowed — never call this in a way that depends on success.
    """
    try:
        _write(image_bytes, quad, document_type, job_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[DATASET] Failed to log sample %s: %s", job_id, exc)


def _write(
    image_bytes: bytes,
    quad: list[list[float]],
    document_type: str,
    job_id: str,
) -> None:
    client = storage.Client()
    bucket = client.bucket(_DATASET_BUCKET)
    prefix = f"{_PREFIX}/{job_id}"

    bucket.blob(f"{prefix}/image.jpg").upload_from_string(
        image_bytes, content_type="image/jpeg"
    )

    meta = {
        "corners": quad,
        "document_type": document_type,
        "job_id": job_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    bucket.blob(f"{prefix}/quad.json").upload_from_string(
        json.dumps(meta, indent=2), content_type="application/json"
    )
    logger.info("[DATASET] Logged sample %s (%s)", job_id, document_type)
