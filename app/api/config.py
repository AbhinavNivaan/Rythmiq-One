"""
Configuration module.
Owns: Environment variables, settings validation.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# Project root (…/Rythmiq One)
BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # ======================
    # Supabase
    # ======================
    supabase_url: str = Field(..., alias="SUPABASE_URL")
    supabase_anon_key: str = Field(..., alias="SUPABASE_ANON_KEY")
    supabase_service_role_key: str = Field(..., alias="SUPABASE_SERVICE_ROLE_KEY")
    supabase_jwt_secret: str = Field(..., alias="SUPABASE_JWT_SECRET")

    # ======================
    # DigitalOcean Spaces
    # ======================
    spaces_endpoint: str = Field(..., alias="DO_SPACES_ENDPOINT")
    spaces_region: str = Field(..., alias="DO_SPACES_REGION")
    spaces_bucket: str = Field(..., alias="DO_SPACES_BUCKET")
    spaces_access_key: str = Field(..., alias="DO_SPACES_ACCESS_KEY")
    spaces_secret_key: str = Field(..., alias="DO_SPACES_SECRET_KEY")

    # ======================
    # Camber / Execution Backend
    # ======================
    camber_api_url: str = Field(
        default="", alias="CAMBER_API_URL",
        description="Camber API URL. Only required when EXECUTION_BACKEND=camber.",
    )
    camber_api_key: str = Field(
        default="", alias="CAMBER_API_KEY",
        description="Camber API key. Only required when EXECUTION_BACKEND=camber.",
    )
    camber_app_name: str = Field(
        default="rythmiq-worker-python-v2",
        alias="CAMBER_APP_NAME",
    )
    execution_backend: str = Field(
        default="cloudrun",
        alias="EXECUTION_BACKEND",
        description="Execution backend: 'local' (mock), 'cloudrun' (Cloud Run worker), or 'camber' (Camber API)",
    )
    cloud_run_worker_url: str = Field(
        default="",
        alias="CLOUD_RUN_WORKER_URL",
        description="Cloud Run worker service URL. Required when EXECUTION_BACKEND=cloudrun.",
    )

    # ======================
    # Service
    # ======================
    service_env: str = Field(default="dev", alias="SERVICE_ENV")
    webhook_secret: str = Field(..., alias="WEBHOOK_SECRET")
    webhook_base_url: str = Field(
        default="",
        alias="WEBHOOK_BASE_URL",
        description="Base URL for webhook callbacks (e.g., https://api.rythmiq.app). "
                    "If empty, Camber must be configured with the correct callback URL.",
    )
    api_port: int = Field(
        default=8000,
        alias="API_PORT",
        description="API server port (for webhook callback URL)",
    )

    # ======================
    # URLs
    # ======================
    upload_url_expiry_seconds: int = Field(
        default=3600, alias="UPLOAD_URL_EXPIRY_SECONDS"
    )
    download_url_expiry_seconds: int = Field(
        default=3600, alias="DOWNLOAD_URL_EXPIRY_SECONDS"
    )

    # ✅ Pydantic v2 configuration
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        populate_by_name=True,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()