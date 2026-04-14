"""Tests for Stage 3c Gemini Flash Vision data extraction processor."""

import json
import os
import sys
import importlib
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../worker"))

extraction = importlib.import_module("processors.extraction")


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeModel:
    def __init__(self, response_text: str) -> None:
        self._response_text = response_text

    def generate_content(self, *_args: Any, **_kwargs: Any) -> _FakeResponse:
        return _FakeResponse(self._response_text)


class _FakeGenAI:
    class _GenerationConfig:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

    GenerationConfig = _GenerationConfig

    def __init__(self, response_text: str) -> None:
        self._response_text = response_text
        self.configured_api_key: str | None = None

    def configure(self, api_key: str) -> None:
        self.configured_api_key = api_key

    def GenerativeModel(self, **_kwargs: Any) -> _FakeModel:
        return _FakeModel(self._response_text)


def test_process_extraction_stage_skips_when_extract_data_false(monkeypatch) -> None:
    called = {"upsert": False}

    def _fake_upsert(*_args: Any, **_kwargs: Any) -> bool:
        called["upsert"] = True
        return True

    monkeypatch.setattr(extraction, "upsert_document_extraction", _fake_upsert)

    result = extraction.process_extraction_stage(
        image_bytes=b"image",
        job_id="job-1",
        user_id="user-1",
        document_type="document",
        extract_data=False,
        api_key="test-key",
        db_client=object(),
    )

    assert result["status"] == "skipped"
    assert result["fields"] == {}
    assert result["confidence"] == {}
    assert called["upsert"] is False


def test_process_extraction_stage_persists_completed_record(monkeypatch) -> None:
    payload = {
        "fields": {
            "pan_number": "ABCDE1234F",
            "name": "ABHINAV",
        },
        "confidence": {
            "pan_number": 0.99,
            "name": 0.93,
        },
    }

    fake_genai = _FakeGenAI(json.dumps(payload))
    monkeypatch.setattr(extraction, "genai", fake_genai)

    calls: list[dict[str, Any]] = []

    def _fake_upsert(db_client: Any, **kwargs: Any) -> bool:
        assert db_client is sentinel_db
        calls.append(kwargs)
        return True

    monkeypatch.setattr(extraction, "upsert_document_extraction", _fake_upsert)

    sentinel_db = object()
    result = extraction.process_extraction_stage(
        image_bytes=b"image-bytes",
        job_id="job-2",
        user_id="user-2",
        document_type="identity",
        extract_data=True,
        api_key="gemini-key",
        db_client=sentinel_db,
    )

    assert fake_genai.configured_api_key == "gemini-key"
    assert result["status"] == "completed"
    assert result["fields"] == payload["fields"]
    assert result["confidence"] == payload["confidence"]

    assert len(calls) == 1
    assert calls[0]["job_id"] == "job-2"
    assert calls[0]["user_id"] == "user-2"
    assert calls[0]["document_type"] == "identity"
    assert calls[0]["status"] == "completed"
    assert calls[0]["fields"] == payload["fields"]
    assert calls[0]["confidence"] == payload["confidence"]


def test_process_extraction_stage_persists_failed_record_for_invalid_response(monkeypatch) -> None:
    fake_genai = _FakeGenAI('{"fields": ["not-an-object"], "confidence": {"name": 0.9}}')
    monkeypatch.setattr(extraction, "genai", fake_genai)

    calls: list[dict[str, Any]] = []

    def _fake_upsert(_db_client: Any, **kwargs: Any) -> bool:
        calls.append(kwargs)
        return True

    monkeypatch.setattr(extraction, "upsert_document_extraction", _fake_upsert)

    result = extraction.process_extraction_stage(
        image_bytes=b"image-bytes",
        job_id="job-3",
        user_id="user-3",
        document_type="document",
        extract_data=True,
        api_key="gemini-key",
        db_client=object(),
    )

    assert result["status"] == "failed"
    assert result["fields"] == {}
    assert result["confidence"] == {}

    assert len(calls) == 1
    assert calls[0]["job_id"] == "job-3"
    assert calls[0]["status"] == "failed"
    assert calls[0]["fields"] == {}
    assert calls[0]["confidence"] == {}
