"""Tests for extract_data consent flag plumbing in API routes."""

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

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
from app.api.routes.jobs import _submit_job_to_processing
from app.api.services.camber import get_camber_service
from app.api.services.storage import get_storage_service


class _FakeExecResult:
    def __init__(self, data):
        self.data = data


class _FakeJobsTable:
    def __init__(self):
        self.inserted_rows: list[dict] = []
        self.updated_rows: list[dict] = []
        self._last_op: str | None = None

    def insert(self, data: dict):
        self._last_op = "insert"
        self.inserted_rows.append(data)
        return self

    def update(self, data: dict):
        self._last_op = "update"
        self.updated_rows.append(data)
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def execute(self):
        if self._last_op == "insert":
            return _FakeExecResult([{"id": str(uuid4())}])
        return _FakeExecResult([])


class _FakeDb:
    def __init__(self):
        self.jobs = _FakeJobsTable()

    def table(self, table_name: str):
        if table_name != "jobs":
            raise AssertionError(f"Unexpected table requested: {table_name}")
        return self.jobs


def _auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-token"}


def test_create_job_persists_extract_data_in_input_metadata() -> None:
    fake_db = _FakeDb()
    mock_user = MagicMock()
    mock_user.id = uuid4()

    mock_storage = MagicMock()
    mock_storage.generate_upload_url.return_value = (
        "https://example.com/upload",
        "uploads/user/job/file.jpg",
        None,
    )

    mock_camber = MagicMock()

    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_storage_service] = lambda: mock_storage
    app.dependency_overrides[get_camber_service] = lambda: mock_camber

    try:
        client = TestClient(app)
        from app.api.routes import jobs as jobs_routes

        with patch.object(jobs_routes, "get_db_client", return_value=fake_db):
            response = client.post(
                "/jobs",
                json={
                    "job_type": "master",
                    "document_type": "document",
                    "filename": "input.jpg",
                    "mime_type": "image/jpeg",
                    "file_size_bytes": 1024,
                    "defer_processing": True,
                    "extract_data": True,
                },
                headers=_auth_headers(),
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert fake_db.jobs.inserted_rows, "Expected insert into jobs table"
    inserted_meta = fake_db.jobs.inserted_rows[0]["input_metadata"]
    assert inserted_meta["extract_data"] is True


def test_submit_job_to_processing_passes_extract_data_to_worker_payload() -> None:
    camber = MagicMock()
    camber.submit_job = AsyncMock(return_value="worker-job-1")
    camber.get_job_status = AsyncMock(return_value={"status": "failed", "success": False, "error": {}})

    with patch("app.api.routes.jobs.get_settings") as mock_settings, patch(
        "app.api.routes.jobs.transition_job_state"
    ):
        mock_settings.return_value = SimpleNamespace(
            execution_backend="cloudrun",
            spaces_bucket="bucket",
            spaces_region="region",
            spaces_endpoint="https://endpoint",
        )

        import asyncio

        asyncio.run(
            _submit_job_to_processing(
                job_id=UUID("550e8400-e29b-41d4-a716-446655440000"),
                user_id=UUID("550e8400-e29b-41d4-a716-446655440001"),
                job_type="master",
                document_type="document",
                document_category="identity",
                document_subtype="pan_card",
                portal_schema_id=None,
                portal_schema_name=None,
                portal_schema_version=None,
                portal_schema_definition=None,
                storage_path="uploads/user/job/file.jpg",
                input_metadata={
                    "mime_type": "image/jpeg",
                    "original_filename": "input.jpg",
                    "extract_data": True,
                },
                correlation_id="corr-1",
                camber=camber,
                extract_data=True,
            )
        )

    submitted_payload = camber.submit_job.await_args.kwargs["payload"]
    assert submitted_payload["extract_data"] is True
