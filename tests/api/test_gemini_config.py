"""Tests that GEMINI_API_KEY is present in Settings."""
from unittest.mock import patch


def test_settings_has_gemini_api_key():
    with patch.dict("os.environ", {
        "SUPABASE_URL": "https://x.supabase.co",
        "SUPABASE_ANON_KEY": "anon",
        "SUPABASE_SERVICE_ROLE_KEY": "service",
        "SUPABASE_JWT_SECRET": "secret",
        "DO_SPACES_ENDPOINT": "https://sgp1.digitaloceanspaces.com",
        "DO_SPACES_REGION": "sgp1",
        "DO_SPACES_BUCKET": "bucket",
        "DO_SPACES_ACCESS_KEY": "key",
        "DO_SPACES_SECRET_KEY": "secret",
        "WEBHOOK_SECRET": "webhook",
        "GEMINI_API_KEY": "test-key",
    }):
        from app.api.config import Settings
        s = Settings()
        assert s.gemini_api_key == "test-key"
