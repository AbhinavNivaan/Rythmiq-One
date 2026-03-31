"""Tests for POST /internal/cleanup/raw-uploads."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from app.api.main import app

VALID_SECRET = "test-secret-value"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def mock_settings():
    """Patch settings to inject the test secret."""
    mock = MagicMock()
    mock.internal_cleanup_secret = VALID_SECRET
    with patch("app.api.routes.internal.get_settings", return_value=mock):
        yield mock


class TestCleanupAuth:
    def test_missing_secret_returns_403(self, client):
        response = client.post("/internal/cleanup/raw-uploads")
        assert response.status_code == 403

    def test_wrong_secret_returns_403(self, client):
        response = client.post(
            "/internal/cleanup/raw-uploads",
            headers={"X-Internal-Secret": "wrong-secret"},
        )
        assert response.status_code == 403

    def test_correct_secret_accepted(self, client):
        with patch("app.api.routes.internal.get_storage_service") as mock_storage, \
             patch("app.api.routes.internal.get_service_db_client") as mock_db:
            mock_storage.return_value.list_objects.return_value = iter([])
            response = client.post(
                "/internal/cleanup/raw-uploads",
                headers={"X-Internal-Secret": VALID_SECRET},
            )
        assert response.status_code == 200

    def test_unconfigured_secret_returns_500(self, client, mock_settings):
        mock_settings.internal_cleanup_secret = ""
        response = client.post(
            "/internal/cleanup/raw-uploads",
            headers={"X-Internal-Secret": "anything"},
        )
        assert response.status_code == 500


class TestCleanupLogic:
    def _make_db_result(self, jobs):
        mock_result = MagicMock()
        mock_result.data = jobs
        return mock_result

    def test_empty_bucket_returns_zero_counts(self, client):
        with patch("app.api.routes.internal.get_storage_service") as mock_storage, \
             patch("app.api.routes.internal.get_service_db_client") as mock_db:
            mock_storage.return_value.list_objects.return_value = iter([])
            response = client.post(
                "/internal/cleanup/raw-uploads",
                headers={"X-Internal-Secret": VALID_SECRET},
            )
        data = response.json()
        assert data["scanned"] == 0
        assert data["deleted"] == 0
        assert data["errors"] == []

    def test_malformed_key_is_skipped(self, client):
        with patch("app.api.routes.internal.get_storage_service") as mock_storage, \
             patch("app.api.routes.internal.get_service_db_client") as mock_db:
            mock_storage.return_value.list_objects.return_value = iter([
                {"Key": "uploads/only-three-parts"},
                {"Key": "other-prefix/user/job/file.jpg"},
            ])
            mock_db.return_value.table.return_value.select.return_value \
                .in_.return_value.in_.return_value.lt.return_value \
                .execute.return_value = self._make_db_result([])
            response = client.post(
                "/internal/cleanup/raw-uploads",
                headers={"X-Internal-Secret": VALID_SECRET},
            )
        data = response.json()
        assert data["scanned"] == 2
        assert data["deleted"] == 0

    def test_exact_path_guard_prevents_wrong_delete(self, client):
        """File is not deleted if key != input_metadata.storage_path."""
        with patch("app.api.routes.internal.get_storage_service") as mock_storage, \
             patch("app.api.routes.internal.get_service_db_client") as mock_db:
            mock_storage.return_value.list_objects.return_value = iter([
                {"Key": "uploads/user-1/job-1/file.jpg"},
            ])
            mock_db.return_value.table.return_value.select.return_value \
                .in_.return_value.in_.return_value.lt.return_value \
                .execute.return_value = self._make_db_result([{
                    "id": "job-1",
                    "input_metadata": {"storage_path": "uploads/user-1/job-1/DIFFERENT.jpg"},
                }])
            response = client.post(
                "/internal/cleanup/raw-uploads",
                headers={"X-Internal-Secret": VALID_SECRET},
            )
        mock_storage.return_value.delete_object.assert_not_called()
        assert response.json()["deleted"] == 0

    def test_eligible_file_is_deleted(self, client):
        """File is deleted when key matches storage_path and job is terminal."""
        with patch("app.api.routes.internal.get_storage_service") as mock_storage, \
             patch("app.api.routes.internal.get_service_db_client") as mock_db:
            key = "uploads/user-1/job-1/file.jpg"
            mock_storage.return_value.list_objects.return_value = iter([{"Key": key}])
            mock_db.return_value.table.return_value.select.return_value \
                .in_.return_value.in_.return_value.lt.return_value \
                .execute.return_value = self._make_db_result([{
                    "id": "job-1",
                    "input_metadata": {"storage_path": key},
                }])
            response = client.post(
                "/internal/cleanup/raw-uploads",
                headers={"X-Internal-Secret": VALID_SECRET},
            )
        mock_storage.return_value.delete_object.assert_called_once_with(key)
        assert response.json()["deleted"] == 1

    def test_paginated_listing_traverses_all_pages(self, client):
        """All objects across multiple iterator pages are scanned."""
        with patch("app.api.routes.internal.get_storage_service") as mock_storage, \
             patch("app.api.routes.internal.get_service_db_client") as mock_db:
            objects = [
                {"Key": f"uploads/user-1/job-{i}/file.jpg"} for i in range(3)
            ]
            mock_storage.return_value.list_objects.return_value = iter(objects)
            mock_db.return_value.table.return_value.select.return_value \
                .in_.return_value.in_.return_value.lt.return_value \
                .execute.return_value = self._make_db_result([])
            response = client.post(
                "/internal/cleanup/raw-uploads",
                headers={"X-Internal-Secret": VALID_SECRET},
            )
        assert response.json()["scanned"] == 3

    def test_idempotent_second_run_deletes_zero(self, client):
        """If the file is already gone from Spaces, scanned=0 and deleted=0."""
        with patch("app.api.routes.internal.get_storage_service") as mock_storage, \
             patch("app.api.routes.internal.get_service_db_client"):
            mock_storage.return_value.list_objects.return_value = iter([])
            response = client.post(
                "/internal/cleanup/raw-uploads",
                headers={"X-Internal-Secret": VALID_SECRET},
            )
        data = response.json()
        assert data["scanned"] == 0
        assert data["deleted"] == 0

    def test_delete_failure_recorded_in_errors(self, client):
        """If a delete fails, it appears in errors and does not abort the run."""
        from app.api.errors import StorageException
        with patch("app.api.routes.internal.get_storage_service") as mock_storage, \
             patch("app.api.routes.internal.get_service_db_client") as mock_db:
            key = "uploads/user-1/job-1/file.jpg"
            mock_storage.return_value.list_objects.return_value = iter([{"Key": key}])
            mock_storage.return_value.delete_object.side_effect = StorageException("S3 error")
            mock_db.return_value.table.return_value.select.return_value \
                .in_.return_value.in_.return_value.lt.return_value \
                .execute.return_value = self._make_db_result([{
                    "id": "job-1",
                    "input_metadata": {"storage_path": key},
                }])
            response = client.post(
                "/internal/cleanup/raw-uploads",
                headers={"X-Internal-Secret": VALID_SECRET},
            )
        data = response.json()
        assert data["deleted"] == 0
        assert len(data["errors"]) == 1
        assert data["errors"][0]["key"] == key
