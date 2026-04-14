"""Tests for GET /jobs/{job_id}/extraction."""

import os
from unittest.mock import MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient

os.environ.setdefault("SUPABASE_URL", "http://localhost:54321")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("DO_SPACES_ENDPOINT", "https://example.digitaloceanspaces.com")
os.environ.setdefault("DO_SPACES_REGION", "blr1")
os.environ.setdefault("DO_SPACES_BUCKET", "test-bucket")
os.environ.setdefault("DO_SPACES_ACCESS_KEY", "test-access-key")
os.environ.setdefault("DO_SPACES_SECRET_KEY", "test-secret-key")
os.environ.setdefault("WEBHOOK_SECRET", "test-webhook-secret")

from app.api.auth import get_current_user
from app.api.main import app


def _auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-token"}


class _FakeQuery:
    def __init__(self, data: list[dict]):
        self._data = data
        self._filters: list[tuple[str, str]] = []
        self._limit: int | None = None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, field: str, value: str):
        self._filters.append((field, value))
        return self

    def limit(self, count: int):
        self._limit = count
        return self

    def execute(self):
        filtered = self._data
        for field, value in self._filters:
            filtered = [row for row in filtered if str(row.get(field)) == str(value)]
        if self._limit is not None:
            filtered = filtered[: self._limit]
        return MagicMock(data=filtered)


class _FakeDb:
    def __init__(self, tables: dict[str, list[dict]]):
        self._tables = tables

    def table(self, table_name: str):
        return _FakeQuery(self._tables.get(table_name, []))


def test_extraction_returns_completed_job_extraction() -> None:
    user_id = str(uuid4())
    other_user_id = str(uuid4())
    job_id = str(uuid4())
    mock_user = MagicMock()
    mock_user.id = user_id

    fake_db = _FakeDb(
        {
            "document_extractions": [
                {
                    "job_id": job_id,
                    "user_id": other_user_id,
                    "document_type": "document",
                    "status": "completed",
                    "extracted_at": None,
                    "fields": {"pan_number": "WRONGUSER123"},
                    "confidence": {"pan_number": 0.1},
                },
                {
                    "job_id": job_id,
                    "user_id": user_id,
                    "document_type": "document",
                    "status": "completed",
                    "extracted_at": "2026-04-14T12:34:56Z",
                    "fields": {"pan_number": "ABCDE1234F", "name": "ABHINAV"},
                    "confidence": {"pan_number": 0.99, "name": 0.93},
                }
            ],
        }
    )

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        client = TestClient(app)
        from app.api.routes import jobs as jobs_routes

        original_get_db_client = jobs_routes.get_db_client
        jobs_routes.get_db_client = lambda: fake_db
        try:
            response = client.get(f"/jobs/{job_id}/extraction", headers=_auth_headers())
        finally:
            jobs_routes.get_db_client = original_get_db_client
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] == job_id
    assert body["document_type"] == "document"
    assert body["status"] == "completed"
    assert body["fields"] == {"pan_number": "ABCDE1234F", "name": "ABHINAV"}
    assert body["confidence"] == {"pan_number": 0.99, "name": 0.93}
    assert body["extracted_at"].startswith("2026-04-14T12:34:56")


def test_extraction_returns_404_when_extraction_missing() -> None:
    user_id = str(uuid4())
    job_id = str(uuid4())
    mock_user = MagicMock()
    mock_user.id = user_id

    fake_db = _FakeDb({"document_extractions": []})

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        client = TestClient(app)
        from app.api.routes import jobs as jobs_routes

        original_get_db_client = jobs_routes.get_db_client
        jobs_routes.get_db_client = lambda: fake_db
        try:
            response = client.get(f"/jobs/{job_id}/extraction", headers=_auth_headers())
        finally:
            jobs_routes.get_db_client = original_get_db_client
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


def test_extraction_requires_auth() -> None:
    job_id = str(uuid4())

    client = TestClient(app)
    response = client.get(f"/jobs/{job_id}/extraction")

    assert response.status_code == 401
