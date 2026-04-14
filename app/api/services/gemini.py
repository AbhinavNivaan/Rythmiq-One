"""
Gemini categorization service.
Owns: Mapping free-text feedback notes into known feedback categories.
"""

import logging
import re
from typing import Any

from app.api.config import Settings, get_settings

try:
    import google.generativeai as genai
except ImportError:  # pragma: no cover - handled at runtime
    genai = None  # type: ignore


logger = logging.getLogger(__name__)

GEMINI_TIMEOUT_SECONDS = 8
GEMINI_MODEL = "gemini-1.5-flash"
_ALLOWED_CATEGORIES = {
    "wrong_crop",
    "poor_quality",
    "wrong_orientation",
    "wrong_document_type",
    "other",
}


class GeminiService:
    """Service wrapper for Gemini feedback-note categorization."""

    def __init__(self, settings: Settings | None = None):
        self._settings = settings or get_settings()

        if genai is not None and self._settings.gemini_api_key:
            genai.configure(api_key=self._settings.gemini_api_key)

    def categorize_feedback(self, note: str) -> str:
        """Categorize a free-text feedback note into a known category."""
        if not note.strip():
            return "other"

        if genai is None or not self._settings.gemini_api_key:
            return "other"

        prompt = (
            "Return only one category token for this user feedback note. "
            "Allowed categories: wrong_crop, poor_quality, wrong_orientation, "
            "wrong_document_type, other. "
            f"Note: {note}"
        )

        try:
            model = genai.GenerativeModel(GEMINI_MODEL)
            response: Any = model.generate_content(
                prompt,
                request_options={"timeout": GEMINI_TIMEOUT_SECONDS},
            )
            return _normalize_category(getattr(response, "text", ""))
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.warning("Gemini categorization failed", extra={"error": str(exc)})
            return "other"


def _normalize_category(text: str) -> str:
    if not text:
        return "other"

    normalized = text.strip().lower()
    if normalized in _ALLOWED_CATEGORIES:
        return normalized

    match = re.search(
        r"wrong_crop|poor_quality|wrong_orientation|wrong_document_type|other",
        normalized,
    )
    if match:
        return match.group(0)

    return "other"


_gemini_service: GeminiService | None = None


def get_gemini_service() -> GeminiService:
    """Get singleton Gemini service."""
    global _gemini_service
    if _gemini_service is None:
        _gemini_service = GeminiService()
    return _gemini_service
