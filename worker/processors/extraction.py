"""Stage 3c data extraction processor using Gemini Flash Vision."""

from __future__ import annotations

import base64
import json
import logging
from typing import Any

from db import get_worker_db_client, upsert_document_extraction

try:
    import google.generativeai as genai
except ImportError:  # pragma: no cover - handled at runtime
    genai = None  # type: ignore[assignment]


logger = logging.getLogger(__name__)

_EXTRACTION_SYSTEM = (
    "You are a document field extraction assistant. Read the document image and "
    "return only structured JSON. Do not include markdown or explanations."
)

_EXTRACTION_USER = (
    "Extract key fields from this document image. Return JSON with exactly two "
    "top-level keys: fields (object) and confidence (object). "
    "For confidence, include one key per extracted field with a score from 0.0 to 1.0."
)

_EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "fields": {"type": "object"},
        "confidence": {
            "type": "object",
            "additionalProperties": {"type": "number"},
        },
    },
    "required": ["fields", "confidence"],
}


def _validate_extraction_payload(payload: Any) -> tuple[dict[str, Any], dict[str, float]] | None:
    if not isinstance(payload, dict):
        return None

    fields = payload.get("fields")
    confidence = payload.get("confidence")

    if not isinstance(fields, dict) or not isinstance(confidence, dict):
        return None

    normalized_fields: dict[str, Any] = {}
    for key, value in fields.items():
        if not isinstance(key, str):
            return None
        normalized_fields[key] = value

    normalized_confidence: dict[str, float] = {}
    for key, value in confidence.items():
        if not isinstance(key, str):
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        value_f = float(value)
        if value_f < 0.0 or value_f > 1.0:
            return None
        normalized_confidence[key] = value_f

    return normalized_fields, normalized_confidence


def process_extraction_stage(
    *,
    image_bytes: bytes,
    job_id: str,
    user_id: str,
    document_type: str,
    extract_data: bool,
    api_key: str | None,
    db_client: Any | None = None,
) -> dict[str, Any]:
    """
    Run optional Stage 3c extraction and persist output to document_extractions.

    This stage is fail-open: it never raises and does not block job completion.
    """
    empty_result = {"status": "skipped", "fields": {}, "confidence": {}}
    if not extract_data:
        return empty_result

    fields: dict[str, Any] = {}
    confidence: dict[str, float] = {}
    status = "failed"

    try:
        if not image_bytes:
            raise ValueError("image bytes missing")
        if not api_key:
            raise ValueError("GEMINI_API_KEY missing")
        if genai is None:
            raise RuntimeError("google-generativeai package unavailable")

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            model_name="gemini-2.0-flash",
            system_instruction=_EXTRACTION_SYSTEM,
        )

        image_part = {
            "mime_type": "image/jpeg",
            "data": base64.b64encode(image_bytes).decode("utf-8"),
        }

        response = model.generate_content(
            [image_part, _EXTRACTION_USER],
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                response_schema=_EXTRACTION_SCHEMA,
            ),
            request_options={"timeout": 10},
        )

        parsed = json.loads(response.text)
        validated = _validate_extraction_payload(parsed)
        if validated is None:
            raise ValueError("invalid extraction contract from Gemini")

        fields, confidence = validated
        status = "completed"
    except Exception as exc:
        logger.warning("Stage 3c extraction failed for job %s: %s", job_id, type(exc).__name__)

    client = db_client if db_client is not None else get_worker_db_client()
    if client is not None:
        upsert_document_extraction(
            client,
            job_id=job_id,
            user_id=user_id,
            document_type=document_type,
            status=status,
            fields=fields,
            confidence=confidence,
        )

    return {
        "status": status,
        "fields": fields,
        "confidence": confidence,
    }
