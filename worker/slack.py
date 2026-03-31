"""
Slack alert helper for the Rythmiq worker.

Fire-and-forget: posts security alerts to a Slack webhook.
Never raises — a Slack outage must not affect job processing.
"""

import logging
import os

import requests

logger = logging.getLogger(__name__)


def post_slack_alert(job_id: str, filename: str, error: str) -> None:
    """
    Post a security alert to Slack.

    Args:
        job_id: The job ID (safe to share — not PII).
        filename: Last path segment of the raw file (filename only, no user prefix).
        error: The exception message from the failed deletion.
    """
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL", "")
    if not webhook_url:
        logger.warning("SLACK_WEBHOOK_URL not set — Slack alert suppressed")
        return

    # Defensive: ensure only the filename is included, never a full path
    safe_filename = filename.split("/")[-1] if filename else "unknown"

    env = os.environ.get("SERVICE_ENV", "unknown")
    message = (
        f"\U0001f6a8 *Raw upload deletion failed*\n"
        f"\u2022 Job: `{job_id}`\n"
        f"\u2022 Env: {env}\n"
        f"\u2022 File: `{safe_filename}`\n"
        f"\u2022 Error: {str(error)[:200]}\n"
        f"\u2022 Action: Will be cleaned up on next scheduled run"
    )

    try:
        response = requests.post(
            webhook_url,
            json={"text": message},
            timeout=5,
        )
        response.raise_for_status()
    except Exception as exc:
        logger.warning("Failed to post Slack alert", extra={"error": str(exc)})
