"""Unit tests for app/api/services/gemini.py."""

import json
from unittest.mock import MagicMock, patch


def test_categorize_returns_none_when_no_api_key():
    """Should return None immediately when api_key is not set."""
    from app.api.services.gemini import categorize_document

    result = categorize_document(b"fakejpeg", api_key="")

    assert result is None


def test_categorize_returns_none_when_image_payload_is_empty():
    """Should return None and skip Gemini calls when image payload is empty."""
    with patch("app.api.services.gemini.genai") as mock_genai:
        from app.api.services import gemini as gemini_module

        result = gemini_module.categorize_document(b"", api_key="test-key")

    assert result is None
    mock_genai.configure.assert_not_called()


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


def test_categorize_configures_gemini_and_calls_model_with_expected_contract():
    """Should configure Gemini and call model with expected generation/request options."""
    mock_response = MagicMock()
    mock_response.text = json.dumps(
        {
            "document_category": "identity",
            "document_subtype": "Aadhaar Card",
            "suggested_name": "Aadhaar",
            "suggested_owner": "Jane Doe",
            "confidence": 0.8,
        }
    )

    with patch("app.api.services.gemini.genai") as mock_genai:
        mock_model = MagicMock()
        mock_model.generate_content.return_value = mock_response
        mock_genai.GenerativeModel.return_value = mock_model

        from app.api.services import gemini as gemini_module

        result = gemini_module.categorize_document(b"fakejpeg", api_key="live-key")

    assert result is not None

    mock_genai.configure.assert_called_once_with(api_key="live-key")
    mock_genai.GenerativeModel.assert_called_once_with(
        model_name="gemini-2.0-flash",
        system_instruction=gemini_module._CATEGORIZE_SYSTEM,
    )

    generate_kwargs = mock_model.generate_content.call_args.kwargs
    assert generate_kwargs["request_options"] == {"timeout": 8}

    generation_config = generate_kwargs["generation_config"]
    mock_genai.GenerationConfig.assert_called_once_with(
        response_mime_type="application/json",
        response_schema=gemini_module._CATEGORIZE_SCHEMA,
    )
    assert generation_config is mock_genai.GenerationConfig.return_value

    payload = mock_model.generate_content.call_args.args[0]
    assert payload[1] == gemini_module._CATEGORIZE_USER
    assert payload[0]["mime_type"] == "image/jpeg"
    assert isinstance(payload[0]["data"], str)
    assert len(payload[0]["data"]) > 0


def test_categorize_returns_none_on_invalid_json():
    """Should return None when Gemini returns non-JSON text."""
    mock_response = MagicMock()
    mock_response.text = "I cannot determine the document type."

    with patch("app.api.services.gemini.genai") as mock_genai:
        mock_genai.GenerativeModel.return_value.generate_content.return_value = mock_response
        from app.api.services import gemini as gemini_module

        result = gemini_module.categorize_document(b"fakejpeg", api_key="test-key")

    assert result is None


def test_categorize_rejects_unknown_document_category():
    """Should return None when category is outside the allowed contract."""
    mock_response = MagicMock()
    mock_response.text = json.dumps(
        {
            "document_category": "passport",
            "document_subtype": "Passport",
            "suggested_name": "Passport",
            "suggested_owner": "John",
            "confidence": 0.9,
        }
    )

    with patch("app.api.services.gemini.genai") as mock_genai:
        mock_genai.GenerativeModel.return_value.generate_content.return_value = mock_response
        from app.api.services import gemini as gemini_module

        result = gemini_module.categorize_document(b"fakejpeg", api_key="test-key")

    assert result is None


def test_categorize_rejects_confidence_outside_range():
    """Should return None when confidence is outside 0.0-1.0."""
    mock_response = MagicMock()
    mock_response.text = json.dumps(
        {
            "document_category": "identity",
            "document_subtype": "PAN Card",
            "suggested_name": "PAN",
            "suggested_owner": None,
            "confidence": 1.2,
        }
    )

    with patch("app.api.services.gemini.genai") as mock_genai:
        mock_genai.GenerativeModel.return_value.generate_content.return_value = mock_response
        from app.api.services import gemini as gemini_module

        result = gemini_module.categorize_document(b"fakejpeg", api_key="test-key")

    assert result is None
