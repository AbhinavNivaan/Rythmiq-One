"""Tests for Settings.is_prod — see security audit S17."""

from __future__ import annotations

import pytest


@pytest.fixture
def settings_factory(monkeypatch):
    """Return a factory that builds a fresh Settings with the given SERVICE_ENV."""
    from app.api.config import Settings

    required_env = {
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_ANON_KEY": "anon",
        "SUPABASE_SERVICE_ROLE_KEY": "service",
        "SUPABASE_JWT_SECRET": "jwt",
        "DO_SPACES_ENDPOINT": "https://sgp1.digitaloceanspaces.com",
        "DO_SPACES_REGION": "sgp1",
        "DO_SPACES_BUCKET": "bucket",
        "DO_SPACES_ACCESS_KEY": "access",
        "DO_SPACES_SECRET_KEY": "secret",
        "WEBHOOK_SECRET": "webhook",
    }
    for key, value in required_env.items():
        monkeypatch.setenv(key, value)

    def _build(service_env: str | None) -> Settings:
        if service_env is None:
            monkeypatch.delenv("SERVICE_ENV", raising=False)
        else:
            monkeypatch.setenv("SERVICE_ENV", service_env)
        return Settings()

    return _build


def test_is_prod_recognizes_literal_prod(settings_factory):
    assert settings_factory("prod").is_prod is True


def test_is_prod_recognizes_production(settings_factory):
    # This is the S17 bug: Cloud Build binds SERVICE_ENV=production, but the
    # historical callsites compared to the literal "prod".
    assert settings_factory("production").is_prod is True


def test_is_prod_is_case_insensitive(settings_factory):
    assert settings_factory("PROD").is_prod is True
    assert settings_factory("Production").is_prod is True


def test_is_prod_strips_whitespace(settings_factory):
    assert settings_factory(" production ").is_prod is True


def test_is_prod_false_for_dev_and_staging(settings_factory):
    assert settings_factory("dev").is_prod is False
    assert settings_factory("staging").is_prod is False
    assert settings_factory("").is_prod is False


def test_is_prod_default_is_dev(settings_factory):
    # Default SERVICE_ENV is "dev"; is_prod must be False.
    assert settings_factory(None).is_prod is False
