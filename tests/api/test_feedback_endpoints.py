"""
Tests for POST /jobs/{id}/dismiss and POST /jobs/{id}/feedback.
"""
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.api.auth import get_current_user
from app.api.services.storage import get_storage_service

JOB_ID = str(uuid4())
USER_ID = str(uuid4())


def _auth_headers():
    return {"Authorization": "Bearer test-token"}


# ── dismiss ─────────────────────────────────────────────────────────────────

def test_dismiss_deletes_raw_upload():
    mock_user = MagicMock()
    mock_user.id = USER_ID
    storage = MagicMock()

    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_storage_service] = lambda: storage
    try:
        client = TestClient(app)
        with patch("app.api.routes.jobs.get_db_client") as mock_db:
            db = MagicMock()
            db.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
                {"id": JOB_ID, "user_id": USER_ID, "status": "completed", "input_metadata": {"storage_path": f"uploads/{USER_ID}/{JOB_ID}/file.jpg"}}
            ]
            mock_db.return_value = db

            response = client.post(f"/jobs/{JOB_ID}/dismiss", headers=_auth_headers())
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    storage.delete_object.assert_called_once_with(f"uploads/{USER_ID}/{JOB_ID}/file.jpg")


def test_dismiss_idempotent_when_no_raw_path():
    mock_user = MagicMock()
    mock_user.id = USER_ID
    storage = MagicMock()

    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_storage_service] = lambda: storage
    try:
        client = TestClient(app)
        with patch("app.api.routes.jobs.get_db_client") as mock_db:
            db = MagicMock()
            db.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
                {"id": JOB_ID, "user_id": USER_ID, "status": "completed", "input_metadata": {}}
            ]
            mock_db.return_value = db

            response = client.post(f"/jobs/{JOB_ID}/dismiss", headers=_auth_headers())
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    storage.delete_object.assert_not_called()


# ── feedback ─────────────────────────────────────────────────────────────────

def test_feedback_full_report_returns_201():
    mock_user = MagicMock()
    mock_user.id = USER_ID
    storage = MagicMock()
    storage.fetch_object.return_value = b"fakejpegbytes"
    storage.generate_download_url.return_value = ("https://spaces.signed/preview.jpg", None)
    storage.object_exists.return_value = True

    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_storage_service] = lambda: storage
    try:
        client = TestClient(app)
        with patch("app.api.routes.jobs.get_db_client") as mock_db, \
             patch("app.api.routes.jobs.get_settings") as mock_settings, \
             patch("app.api.routes.jobs.feedback_gcs.archive_raw_upload", return_value="gs://bucket/job/raw.jpg"), \
             patch("app.api.routes.jobs.feedback_gcs.write_metadata"), \
             patch("app.api.routes.jobs.feedback_gcs.generate_signed_url", return_value="https://signed/raw.jpg"), \
             patch("app.api.routes.jobs.slack.post_feedback_report_alert"):

            db = MagicMock()
            db.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
                {
                    "id": JOB_ID, "user_id": USER_ID,
                    "status": "completed",
                    "master_path": f"master/{USER_ID}/{JOB_ID}/{JOB_ID}.enc",
                    "input_metadata": {
                        "storage_path": f"uploads/{USER_ID}/{JOB_ID}/file.jpg",
                        "document_type": "identity_card",
                        "document_subtype": "PAN Card",
                        "input_quality_score": 0.61,
                    }
                }
            ]
            db.table.return_value.insert.return_value.execute.return_value.data = [{"id": str(uuid4())}]
            mock_db.return_value = db
            settings = MagicMock()
            settings.gcs_feedback_bucket = "rythmiq-one-feedback"
            mock_settings.return_value = settings

            response = client.post(
                f"/jobs/{JOB_ID}/feedback",
                json={"report_type": "full", "category": "wrong_crop", "consent_granted": True},
                headers=_auth_headers(),
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert "feedback_id" in response.json()


def test_feedback_rejects_false_consent():
    mock_user = MagicMock()
    mock_user.id = USER_ID

    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_storage_service] = lambda: MagicMock()
    try:
        client = TestClient(app)
        with patch("app.api.routes.jobs.get_db_client") as mock_db, \
             patch("app.api.routes.jobs.get_settings") as mock_settings:

            db = MagicMock()
            db.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
                {"id": JOB_ID, "user_id": USER_ID, "input_metadata": {}}
            ]
            mock_db.return_value = db
            mock_settings.return_value = MagicMock()

            response = client.post(
                f"/jobs/{JOB_ID}/feedback",
                json={"category": "wrong_crop", "consent_granted": False},
                headers=_auth_headers(),
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code in (400, 422)


def test_feedback_returns_500_when_gcs_archive_fails():
    mock_user = MagicMock()
    mock_user.id = USER_ID
    storage = MagicMock()
    storage.fetch_object.return_value = b"bytes"

    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_storage_service] = lambda: storage
    try:
        client = TestClient(app, raise_server_exceptions=False)
        with patch("app.api.routes.jobs.get_db_client") as mock_db, \
             patch("app.api.routes.jobs.get_settings") as mock_settings, \
             patch("app.api.routes.jobs.feedback_gcs.archive_raw_upload", side_effect=Exception("GCS down")):

            db = MagicMock()
            db.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
                {"id": JOB_ID, "user_id": USER_ID, "status": "completed", "master_path": "master/x.enc",
                 "input_metadata": {"storage_path": "uploads/x.jpg"}}
            ]
            mock_db.return_value = db
            settings = MagicMock()
            settings.gcs_feedback_bucket = "rythmiq-one-feedback"
            mock_settings.return_value = settings

            response = client.post(
                f"/jobs/{JOB_ID}/feedback",
                json={"category": "wrong_crop", "consent_granted": True},
                headers=_auth_headers(),
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 500
    storage.delete_object.assert_not_called()
