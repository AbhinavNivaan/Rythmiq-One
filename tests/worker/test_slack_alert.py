# tests/worker/test_slack_alert.py
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../worker"))

from unittest.mock import MagicMock, patch


def test_post_slack_alert_posts_correct_payload():
    """Posts to the configured webhook URL with job_id and filename in text."""
    with patch("slack.requests.post") as mock_post:
        mock_post.return_value.raise_for_status = MagicMock()
        import slack
        with patch.dict(os.environ, {"SLACK_WEBHOOK_URL": "https://hooks.slack.com/test"}):
            slack.post_slack_alert("job-abc", "document.jpg", "Connection reset")
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert call_kwargs[0][0] == "https://hooks.slack.com/test"
        payload_text = call_kwargs[1]["json"]["text"]
        assert "job-abc" in payload_text
        assert "document.jpg" in payload_text
        assert "Connection reset" in payload_text


def test_post_slack_alert_excludes_user_id_and_full_path():
    """user_id and full storage path must not appear in the Slack message."""
    with patch("slack.requests.post") as mock_post:
        mock_post.return_value.raise_for_status = MagicMock()
        import slack
        with patch.dict(os.environ, {"SLACK_WEBHOOK_URL": "https://hooks.slack.com/test"}):
            slack.post_slack_alert("job-abc", "document.jpg", "err")
        text = mock_post.call_args[1]["json"]["text"]
        assert "uploads/" not in text
        assert "user-uuid-here" not in text


def test_post_slack_alert_no_webhook_url_does_not_raise():
    """When SLACK_WEBHOOK_URL is unset, must return silently without raising."""
    import importlib
    import slack
    importlib.reload(slack)
    env = {k: v for k, v in os.environ.items() if k != "SLACK_WEBHOOK_URL"}
    with patch.dict(os.environ, env, clear=True):
        slack.post_slack_alert("job-abc", "document.jpg", "err")  # must not raise


def test_post_slack_alert_http_error_does_not_raise():
    """Slack outage (HTTP error) must not propagate to the caller."""
    with patch("slack.requests.post", side_effect=Exception("timeout")):
        import slack
        with patch.dict(os.environ, {"SLACK_WEBHOOK_URL": "https://hooks.slack.com/test"}):
            slack.post_slack_alert("job-abc", "document.jpg", "err")  # must not raise


def test_post_slack_alert_raise_for_status_failure_does_not_raise():
    """HTTP 4xx/5xx from Slack must not propagate to the caller."""
    with patch("slack.requests.post") as mock_post:
        mock_post.return_value.raise_for_status = MagicMock(side_effect=Exception("403"))
        import slack
        with patch.dict(os.environ, {"SLACK_WEBHOOK_URL": "https://hooks.slack.com/test"}):
            slack.post_slack_alert("job-abc", "document.jpg", "err")  # must not raise
