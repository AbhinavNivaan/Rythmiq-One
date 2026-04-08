"""
Slack notification helper for the API service.

Fire-and-forget: never raises — a Slack outage must not affect request processing.
"""
from __future__ import annotations

import logging
import os

import requests

logger = logging.getLogger(__name__)


def post_feedback_report_alert(
    *,
    job_id: str,
    document_type: str | None,
    document_subtype: str | None,
    category: str,
    note: str | None,
    input_quality_score: float | None,
    output_quality_score: float | None,
    quad_source: str | None,
    tflite_confidence: float | None,
    raw_input_url: str | None,
    output_preview_url: str | None,
) -> None:
    """Post a bad-output feedback report notification to Slack."""
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL", "")
    if not webhook_url:
        logger.warning("SLACK_WEBHOOK_URL not set — feedback Slack alert suppressed")
        return

    doc_label = " / ".join(filter(None, [document_type, document_subtype])) or "Unknown"
    category_label = category.replace("_", " ").title()

    lines = [
        "🚨 *Bad Output Report*",
        f"• Job: `{job_id}`",
        f"• Type: {doc_label}",
        f"• Category: {category_label}",
    ]
    if note:
        lines.append(f"• Note: \"{note[:200]}\"")

    lines.append("")
    lines.append("*Pipeline:*")
    if input_quality_score is not None:
        lines.append(f"• Quality (before): {input_quality_score:.2f}")
    if output_quality_score is not None:
        lines.append(f"• Quality (after):  {output_quality_score:.2f}")
    if quad_source:
        lines.append(f"• Quad source: {quad_source}")
    if tflite_confidence is not None:
        lines.append(f"• TFLite confidence: {tflite_confidence:.3f}")

    lines.append("")
    raw_line = f"📥 Raw input: {raw_input_url}   _(expires 4h)_" if raw_input_url else "📥 Raw input: unavailable"
    output_line = f"📤 Output preview: {output_preview_url}   _(expires 4h)_" if output_preview_url else "📤 Output preview: unavailable"
    lines.append(raw_line)
    lines.append(output_line)

    try:
        response = requests.post(
            webhook_url,
            json={"text": "\n".join(lines), "unfurl_links": False, "unfurl_media": False},
            timeout=5,
        )
        response.raise_for_status()
    except Exception as exc:
        logger.warning("Failed to post feedback Slack alert", extra={"error": str(exc)})
