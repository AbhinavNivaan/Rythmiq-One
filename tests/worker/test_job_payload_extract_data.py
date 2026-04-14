"""Tests for extract_data parsing in worker JobPayload."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../worker"))

from models import JobPayload


def _base_payload() -> dict:
    return {
        "job_id": "550e8400-e29b-41d4-a716-446655440000",
        "user_id": "550e8400-e29b-41d4-a716-446655440001",
        "mode": "master",
        "document_type": "document",
        "input": {
            "raw_path": "uploads/test.jpg",
            "artifact_url": None,
            "mime_type": "image/jpeg",
            "original_filename": "test.jpg",
        },
        "storage": {
            "bucket": "test-bucket",
            "region": "sgp1",
            "endpoint": "https://example.com",
        },
    }


def test_jobpayload_extract_data_defaults_to_false() -> None:
    payload = JobPayload.from_dict(_base_payload())
    assert payload.extract_data is False


def test_jobpayload_parses_extract_data_true() -> None:
    data = _base_payload()
    data["extract_data"] = True

    payload = JobPayload.from_dict(data)
    assert payload.extract_data is True
