"""Gemini Flash Vision service for document categorization."""

from __future__ import annotations

import base64
import json
import logging
from typing import Any

try:
    import google.generativeai as genai
except ImportError:  # pragma: no cover - handled at runtime
    genai = None  # type: ignore[assignment]


logger = logging.getLogger(__name__)

_CATEGORIZE_SYSTEM = (
    "You are a document classifier. Given a document image, identify the document type "
    "and suggest metadata. Return only what you can confidently determine. "
    "If uncertain, return null."
)

_CATEGORIZE_USER = (
    "Classify this document. Return: document_category (one of: identity, academic, "
    "address, financial, photograph, signature, certificate, other), "
    "document_subtype (specific name e.g. 'PAN Card', 'Aadhaar Card', "
    "'Class 10 Marksheet'), suggested_name (short user-facing label), "
    "suggested_owner (person's name if visible on document, otherwise null), "
    "confidence (0.0-1.0)."
)

_CATEGORIZE_SCHEMA = {
    "type": "object",
    "properties": {
        "document_category": {"type": "string"},
        "document_subtype": {"type": "string", "nullable": True},
        "suggested_name": {"type": "string", "nullable": True},
        "suggested_owner": {"type": "string", "nullable": True},
        "confidence": {"type": "number"},
    },
    "required": ["document_category", "confidence"],
}


def categorize_document(image_bytes: bytes, api_key: str) -> dict[str, Any] | None:
    """Classify a document image via Gemini and return parsed JSON or None."""
    if not api_key:
        return None

    if genai is None:
        return None

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            model_name="gemini-2.0-flash",
            system_instruction=_CATEGORIZE_SYSTEM,
        )

        image_part = {
            "mime_type": "image/jpeg",
            "data": base64.b64encode(image_bytes).decode("utf-8"),
        }

        response = model.generate_content(
            [image_part, _CATEGORIZE_USER],
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                response_schema=_CATEGORIZE_SCHEMA,
            ),
            request_options={"timeout": 8},
        )

        return json.loads(response.text)
    except json.JSONDecodeError:
        logger.warning("Gemini categorization returned non-JSON response")
        return None
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.warning("Gemini categorization failed: %s", type(exc).__name__)
        return None
