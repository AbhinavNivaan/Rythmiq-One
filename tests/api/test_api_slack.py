# tests/api/test_api_slack.py
from unittest.mock import MagicMock, patch

from app.api.slack import post_feedback_report_alert


def test_posts_to_webhook_when_url_set():
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()

    with patch("app.api.slack.requests.post", return_value=mock_response) as mock_post, \
         patch.dict("os.environ", {"SLACK_WEBHOOK_URL": "https://hooks.slack.com/test"}):
        post_feedback_report_alert(
            job_id="abc-123",
            document_type="document",
            document_subtype="PAN Card",
            category="wrong_crop",
            note="Card edge cut off",
            quality_score=0.61,
            quad_source="model",
            tflite_confidence=0.43,
            raw_input_url="https://gcs.signed/raw.jpg",
            output_preview_url="https://spaces.signed/preview.jpg",
        )

    mock_post.assert_called_once()
    payload = mock_post.call_args[1]["json"]["text"]
    assert "abc-123" in payload
    assert "Wrong Crop" in payload
    assert "PAN Card" in payload
    assert "https://gcs.signed/raw.jpg" in payload


def test_suppressed_when_no_webhook_url():
    with patch("app.api.slack.requests.post") as mock_post, \
         patch.dict("os.environ", {}, clear=True):
        post_feedback_report_alert(
            job_id="abc-123",
            document_type=None,
            document_subtype=None,
            category="other",
            note=None,
            quality_score=None,
            quad_source=None,
            tflite_confidence=None,
            raw_input_url=None,
            output_preview_url=None,
        )
    mock_post.assert_not_called()


def test_never_raises_on_network_error():
    with patch("app.api.slack.requests.post", side_effect=Exception("network down")), \
         patch.dict("os.environ", {"SLACK_WEBHOOK_URL": "https://hooks.slack.com/test"}):
        # Must not raise
        post_feedback_report_alert(
            job_id="abc-123",
            document_type=None,
            document_subtype=None,
            category="poor_quality",
            note=None,
            quality_score=None,
            quad_source=None,
            tflite_confidence=None,
            raw_input_url=None,
            output_preview_url=None,
        )
