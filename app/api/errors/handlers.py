"""
Exception handlers.
Owns: Mapping exceptions to HTTP responses.
"""

import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from .exceptions import AppException

logger = logging.getLogger(__name__)


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    correlation_id = getattr(request.state, "correlation_id", None)
    logger.error(
        "Application error",
        extra={
            "error_code": exc.error_code,
            "message": exc.message,
            "correlation_id": correlation_id,
        },
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict(),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    correlation_id = getattr(request.state, "correlation_id", None)
    logger.warning(
        "Validation error",
        extra={
            "errors": exc.errors(),
            "correlation_id": correlation_id,
        },
    )
    return JSONResponse(
        status_code=400,
        content={
            "error_code": "INVALID_INPUT",
            "message": "Request validation failed",
            "retryable": False,
            "errors": [
                {"field": ".".join(str(loc) for loc in e["loc"]), "message": e["msg"]}
                for e in exc.errors()
            ],
        },
    )


async def pydantic_exception_handler(
    request: Request, exc: ValidationError
) -> JSONResponse:
    correlation_id = getattr(request.state, "correlation_id", None)
    logger.warning(
        "Pydantic validation error",
        extra={
            "errors": exc.errors(),
            "correlation_id": correlation_id,
        },
    )
    return JSONResponse(
        status_code=400,
        content={
            "error_code": "INVALID_INPUT",
            "message": "Data validation failed",
            "retryable": False,
        },
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    correlation_id = getattr(request.state, "correlation_id", None)
    logger.exception(
        "Unhandled exception",
        extra={"correlation_id": correlation_id},
    )
    return JSONResponse(
        status_code=500,
        content={
            "error_code": "INTERNAL_ERROR",
            "message": "An unexpected error occurred",
            "retryable": True,
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(ValidationError, pydantic_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
