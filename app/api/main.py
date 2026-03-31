"""
FastAPI Application Entry Point.
Owns: App factory, router mounting, middleware setup.
"""

import logging
import sys

from fastapi import FastAPI

from app.api.config import get_settings
from app.api.errors import register_exception_handlers
from app.api.middleware import CorrelationMiddleware, LoggingMiddleware
from app.api.routes import (
    auth_router,
    form_schemas_router,
    health_router,
    internal_router,
    jobs_router,
    portals_router,
    webhooks_router,
)
from app.api.utils.logging import RedactingFormatter, setup_redacting_logger


def configure_logging() -> None:
    # ============================================
    # CRITICAL SECURITY: Enable log redaction
    # ============================================
    # Redact SEK, tokens, passwords from all logs
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        RedactingFormatter(
            fmt='{"timestamp": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": "%(message)s"}',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers = [handler]
    
    # Setup redacting logger (mirrors the formatter but also redacts extra fields)
    setup_redacting_logger(root_logger)
    
    root_logger.info("SECURITY: Log redaction enabled - sensitive data will be filtered from all logs")
    # ============================================

    # Suppress noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Rythmiq One API",
        version="2.0.0",
        docs_url="/docs" if settings.service_env != "prod" else None,
        redoc_url="/redoc" if settings.service_env != "prod" else None,
        openapi_url="/openapi.json" if settings.service_env != "prod" else None,
    )

    # Middleware (order matters: first added = outermost)
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(CorrelationMiddleware)

    # Exception handlers
    register_exception_handlers(app)

    # Routers
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(jobs_router)
    app.include_router(webhooks_router)
    app.include_router(form_schemas_router)
    app.include_router(portals_router)
    app.include_router(internal_router, prefix="/internal")

    return app


configure_logging()
app = create_app()
