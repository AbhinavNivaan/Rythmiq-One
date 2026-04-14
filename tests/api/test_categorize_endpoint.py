"""Tests for POST /jobs/categorize."""

import os
from io import BytesIO
from unittest.mock import MagicMock, patch
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

USER_ID = str(uuid4())


def _auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-token"}


def _fake_image_bytes() -> bytes:
    """1x1 JPEG for testing."""
    return (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t"
        b"\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a"
        b"\x1f\x1e\x1d\x1a\x1c\x1c $.\' \",#\x1c\x1c(7),01444\x1f\'9=82<.342\x1e\xff\xd9"
    )


def test_categorize_returns_200_with_result() -> None:
    mock_user = MagicMock()
    mock_user.id = USER_ID

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        client = TestClient(app)
        with patch("app.api.routes.jobs.categorize_document") as mock_cat, patch(
            "app.api.routes.jobs.get_settings"
        ) as mock_settings:
            mock_settings.return_value.gemini_api_key = "test-key"
            mock_cat.return_value = {
                "document_category": "identity",
                "document_subtype": "PAN Card",
                "suggested_name": "PAN Card",
                "suggested_owner": None,
                "confidence": 0.94,
            }
            response = client.post(
                "/jobs/categorize",
                files={"image": ("test.jpg", BytesIO(_fake_image_bytes()), "image/jpeg")},
                data={"image_width": "1080", "image_height": "1920"},
                headers=_auth_headers(),
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["document_category"] == "identity"
    assert body["document_subtype"] == "PAN Card"
    assert body["confidence"] == 0.94


def test_categorize_returns_200_with_nulls_on_gemini_failure() -> None:
    """On Gemini failure, endpoint returns 200 with all-null fields."""
    mock_user = MagicMock()
    mock_user.id = USER_ID

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        client = TestClient(app)
        with patch("app.api.routes.jobs.categorize_document") as mock_cat, patch(
            "app.api.routes.jobs.get_settings"
        ) as mock_settings:
            mock_settings.return_value.gemini_api_key = "test-key"
            mock_cat.return_value = None
            response = client.post(
                "/jobs/categorize",
                files={"image": ("test.jpg", BytesIO(_fake_image_bytes()), "image/jpeg")},
                data={"image_width": "800", "image_height": "600"},
                headers=_auth_headers(),
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["document_category"] is None
    assert body["confidence"] is None


def test_categorize_returns_200_with_nulls_when_gemini_key_missing() -> None:
    """When GEMINI_API_KEY is missing, endpoint should return all-null fallback."""
    mock_user = MagicMock()
    mock_user.id = USER_ID

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        client = TestClient(app)
        with patch("app.api.routes.jobs.categorize_document") as mock_cat, patch(
            "app.api.routes.jobs.get_settings"
        ) as mock_settings:
            mock_settings.return_value.gemini_api_key = None
            response = client.post(
                "/jobs/categorize",
                files={"image": ("test.jpg", BytesIO(_fake_image_bytes()), "image/jpeg")},
                data={"image_width": "800", "image_height": "600"},
                headers=_auth_headers(),
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["document_category"] is None
    assert body["document_subtype"] is None
    assert body["suggested_name"] is None
    assert body["suggested_owner"] is None
    assert body["confidence"] is None
    mock_cat.assert_not_called()


def test_categorize_requires_auth() -> None:
    client = TestClient(app)
    response = client.post(
        "/jobs/categorize",
        files={"image": ("test.jpg", BytesIO(_fake_image_bytes()), "image/jpeg")},
        data={"image_width": "800", "image_height": "600"},
    )
    assert response.status_code == 401


def test_categorize_openapi_uses_categorization_response_model() -> None:
    openapi = app.openapi()
    schema_ref = (
        openapi["paths"]["/jobs/categorize"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    )
    assert schema_ref.endswith("/CategorizationResponse")
