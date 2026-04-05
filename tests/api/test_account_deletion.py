# tests/api/test_account_deletion.py
"""Tests for DELETE /account."""
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.api.auth import get_current_user
from app.api.db import get_service_db_client
from app.api.services.storage import get_storage_service
from app.api.errors import StorageException

USER_ID = str(uuid4())


def _auth():
    return {"Authorization": "Bearer test-token"}


def _mock_user():
    u = MagicMock()
    u.id = USER_ID
    return u


def _no_inflight_db():
    """DB mock: no in-flight jobs, all delete calls succeed."""
    db = MagicMock()
    # In-flight check returns nothing
    db.table.return_value.select.return_value.eq.return_value.in_.return_value.limit.return_value.execute.return_value.data = []
    # Job IDs query for documents deletion
    db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
    return db


class TestAccountDeletionGuard:
    def test_returns_409_when_jobs_in_flight(self):
        storage = MagicMock()
        storage.delete_objects_by_prefix.return_value = (0, 0)

        app.dependency_overrides[get_current_user] = _mock_user
        app.dependency_overrides[get_storage_service] = lambda: storage
        try:
            client = TestClient(app)
            db = MagicMock()
            db.table.return_value.select.return_value.eq.return_value.in_.return_value.limit.return_value.execute.return_value.data = [
                {"id": str(uuid4())}
            ]
            app.dependency_overrides[get_service_db_client] = lambda: db
            response = client.delete("/account", headers=_auth())
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 409
        assert response.json()["detail"]["error_code"] == "JOBS_IN_PROGRESS"
        storage.delete_objects_by_prefix.assert_not_called()

    def test_returns_401_without_token(self):
        client = TestClient(app)
        response = client.delete("/account")
        assert response.status_code == 401


class TestAccountDeletionHappyPath:
    def test_returns_204_on_success(self):
        storage = MagicMock()
        storage.delete_objects_by_prefix.return_value = (3, 0)

        app.dependency_overrides[get_current_user] = _mock_user
        app.dependency_overrides[get_storage_service] = lambda: storage
        try:
            client = TestClient(app)
            db = _no_inflight_db()
            app.dependency_overrides[get_service_db_client] = lambda: db
            response = client.delete("/account", headers=_auth())
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 204
        # Both prefixes deleted
        calls = storage.delete_objects_by_prefix.call_args_list
        prefixes = [c[0][0] for c in calls]
        assert any(f"uploads/{USER_ID}/" in p for p in prefixes)
        assert any(f"output/{USER_ID}/" in p for p in prefixes)
        # Auth user deleted
        db.auth.admin.delete_user.assert_called_once_with(USER_ID)

    def test_returns_204_with_no_jobs(self):
        """User has zero jobs — storage and DB steps are no-ops."""
        storage = MagicMock()
        storage.delete_objects_by_prefix.return_value = (0, 0)

        app.dependency_overrides[get_current_user] = _mock_user
        app.dependency_overrides[get_storage_service] = lambda: storage
        try:
            client = TestClient(app)
            db = _no_inflight_db()
            app.dependency_overrides[get_service_db_client] = lambda: db
            response = client.delete("/account", headers=_auth())
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 204
        db.auth.admin.delete_user.assert_called_once_with(USER_ID)

    def test_deletes_documents_before_jobs_when_jobs_exist(self):
        """When user has jobs, documents rows are deleted before jobs rows."""
        storage = MagicMock()
        storage.delete_objects_by_prefix.return_value = (2, 0)
        job_id_1 = str(uuid4())
        job_id_2 = str(uuid4())

        app.dependency_overrides[get_current_user] = _mock_user
        app.dependency_overrides[get_storage_service] = lambda: storage
        try:
            client = TestClient(app)
            db = MagicMock()
            # In-flight guard: no pending/processing jobs
            in_flight_mock = MagicMock()
            in_flight_mock.data = []
            # Job IDs query: returns 2 jobs
            job_ids_mock = MagicMock()
            job_ids_mock.data = [{"id": job_id_1}, {"id": job_id_2}]

            # Track call order
            call_order = []

            def documents_delete_side_effect(*args, **kwargs):
                call_order.append("documents")
                return MagicMock()

            def jobs_delete_side_effect(*args, **kwargs):
                call_order.append("jobs")
                return MagicMock()

            # Wire up the mock — we need different behaviour per table name
            def table_side_effect(name):
                t = MagicMock()
                if name == "jobs":
                    select_mock = MagicMock()
                    eq_mock = MagicMock()
                    in_mock = MagicMock()
                    limit_mock = MagicMock()
                    limit_mock.execute.return_value = in_flight_mock
                    in_mock.limit.return_value = limit_mock
                    eq_mock.in_.return_value = in_mock
                    eq_mock.execute.return_value = job_ids_mock
                    select_mock.eq.return_value = eq_mock
                    t.select.return_value = select_mock
                    delete_mock = MagicMock()
                    eq_delete_mock = MagicMock()
                    eq_delete_mock.execute.side_effect = jobs_delete_side_effect
                    delete_mock.eq.return_value = eq_delete_mock
                    t.delete.return_value = delete_mock
                elif name == "documents":
                    delete_mock = MagicMock()
                    in_delete_mock = MagicMock()
                    in_delete_mock.execute.side_effect = documents_delete_side_effect
                    delete_mock.in_.return_value = in_delete_mock
                    t.delete.return_value = delete_mock
                elif name == "feedback_reports":
                    delete_mock = MagicMock()
                    eq_delete_mock = MagicMock()
                    eq_delete_mock.execute.return_value = MagicMock()
                    delete_mock.eq.return_value = eq_delete_mock
                    t.delete.return_value = delete_mock
                return t

            db.table.side_effect = table_side_effect
            app.dependency_overrides[get_service_db_client] = lambda: db
            response = client.delete("/account", headers=_auth())
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 204
        assert call_order == ["documents", "jobs"], f"Expected documents before jobs, got: {call_order}"
        db.auth.admin.delete_user.assert_called_once_with(USER_ID)


class TestAccountDeletionFailures:
    def test_returns_500_when_storage_enumeration_fails(self):
        storage = MagicMock()
        storage.delete_objects_by_prefix.side_effect = StorageException("list failed")

        app.dependency_overrides[get_current_user] = _mock_user
        app.dependency_overrides[get_storage_service] = lambda: storage
        try:
            client = TestClient(app, raise_server_exceptions=False)
            db = _no_inflight_db()
            app.dependency_overrides[get_service_db_client] = lambda: db
            response = client.delete("/account", headers=_auth())
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 500
        assert response.json()["detail"]["error_code"] == "STORAGE_CLEANUP_FAILED"
        db.auth.admin.delete_user.assert_not_called()

    def test_returns_500_when_jobs_db_deletion_fails(self):
        storage = MagicMock()
        storage.delete_objects_by_prefix.return_value = (0, 0)

        app.dependency_overrides[get_current_user] = _mock_user
        app.dependency_overrides[get_storage_service] = lambda: storage
        try:
            client = TestClient(app, raise_server_exceptions=False)
            db = MagicMock()

            def table_side_effect(name):
                t = MagicMock()
                if name == "jobs":
                    select_mock = MagicMock()
                    eq_mock = MagicMock()
                    in_mock = MagicMock()
                    limit_mock = MagicMock()
                    limit_mock.execute.return_value.data = []
                    in_mock.limit.return_value = limit_mock
                    eq_mock.in_.return_value = in_mock
                    eq_mock.execute.return_value.data = []
                    select_mock.eq.return_value = eq_mock
                    t.select.return_value = select_mock
                    delete_mock = MagicMock()
                    eq_delete_mock = MagicMock()
                    eq_delete_mock.execute.side_effect = Exception("DB error")
                    delete_mock.eq.return_value = eq_delete_mock
                    t.delete.return_value = delete_mock
                else:
                    # documents and feedback_reports succeed
                    delete_mock = MagicMock()
                    delete_mock.eq.return_value.execute.return_value = MagicMock()
                    delete_mock.in_.return_value.execute.return_value = MagicMock()
                    t.delete.return_value = delete_mock
                return t

            db.table.side_effect = table_side_effect
            app.dependency_overrides[get_service_db_client] = lambda: db
            response = client.delete("/account", headers=_auth())
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 500
        assert response.json()["detail"]["error_code"] == "DB_DELETION_FAILED"
        db.auth.admin.delete_user.assert_not_called()

    def test_returns_500_when_auth_deletion_fails_after_data_purge(self):
        storage = MagicMock()
        storage.delete_objects_by_prefix.return_value = (0, 0)

        app.dependency_overrides[get_current_user] = _mock_user
        app.dependency_overrides[get_storage_service] = lambda: storage
        try:
            client = TestClient(app, raise_server_exceptions=False)
            db = _no_inflight_db()
            db.auth.admin.delete_user.side_effect = Exception("Supabase error")
            app.dependency_overrides[get_service_db_client] = lambda: db
            response = client.delete("/account", headers=_auth())
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 500
        assert response.json()["detail"]["error_code"] == "AUTH_DELETION_FAILED"
