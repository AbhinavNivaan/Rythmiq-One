from types import SimpleNamespace
from unittest.mock import MagicMock


def test_categorize_feedback_uses_8s_timeout_and_returns_known_category(monkeypatch):
    from app.api.services.gemini import GeminiService

    fake_model = MagicMock()
    fake_model.generate_content.return_value = SimpleNamespace(text="wrong_crop")

    fake_genai = MagicMock()
    fake_genai.GenerativeModel.return_value = fake_model

    monkeypatch.setattr("app.api.services.gemini.genai", fake_genai)

    service = GeminiService(settings=SimpleNamespace(gemini_api_key="test-key"))

    category = service.categorize_feedback("The crop cut off the student photo")

    assert category == "wrong_crop"
    fake_model.generate_content.assert_called_once()
    _, kwargs = fake_model.generate_content.call_args
    assert kwargs["request_options"]["timeout"] == 8
