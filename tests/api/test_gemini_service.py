"""Unit tests for app/api/services/gemini.py."""

import json
from unittest.mock import MagicMock, patch


def test_categorize_returns_none_when_no_api_key():
    """Should return None immediately when api_key is not set."""
    from app.api.services.gemini import categorize_document

    result = categorize_document(b"fakejpeg", api_key="")

    assert result is None


def test_categorize_returns_none_on_exception():
    """Should swallow exceptions and return None."""
    with patch("app.api.services.gemini.genai") as mock_genai:
        mock_genai.GenerativeModel.return_value.generate_content.side_effect = Exception("boom")
        from app.api.services import gemini as gemini_module

        result = gemini_module.categorize_document(b"fakejpeg", api_key="test-key")

    assert result is None


def test_categorize_returns_structured_result():
    """Should parse Gemini JSON response into a dict."""
    mock_response = MagicMock()
    mock_response.text = json.dumps(
        {
            "document_category": "identity",
            "document_subtype": "PAN Card",
            "suggested_name": "PAN Card",
            "suggested_owner": None,
            "confidence": 0.94,
        }
    )

    with patch("app.api.services.gemini.genai") as mock_genai:
        mock_genai.GenerativeModel.return_value.generate_content.return_value = mock_response
        from app.api.services import gemini as gemini_module

        result = gemini_module.categorize_document(b"fakejpeg", api_key="test-key")

    assert result is not None
    assert result["document_category"] == "identity"
    assert result["document_subtype"] == "PAN Card"
    assert result["confidence"] == 0.94


def test_categorize_returns_none_on_invalid_json():
    """Should return None when Gemini returns non-JSON text."""
    mock_response = MagicMock()
    mock_response.text = "I cannot determine the document type."

    with patch("app.api.services.gemini.genai") as mock_genai:
        mock_genai.GenerativeModel.return_value.generate_content.return_value = mock_response
        from app.api.services import gemini as gemini_module

        result = gemini_module.categorize_document(b"fakejpeg", api_key="test-key")

    assert result is None
