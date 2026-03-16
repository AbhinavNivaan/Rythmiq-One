"""
Google Cloud Document AI OCR integration for Rythmiq worker.

Replaces PaddleOCR with Google's Document AI OCR processor:
- 200+ language support (Hindi, Tamil, mixed-script — critical for Indian docs)
- Higher accuracy on scanned/photographed documents
- Automatic orientation & skew detection
- Word-level and line-level confidence scores
- No local model loading (eliminates OOM risk on Cloud Run)

Environment Variables:
    GOOGLE_CLOUD_PROJECT       - GCP project ID (e.g., "rythmiq-one")
    DOCUMENT_AI_LOCATION       - Processor location (default: "asia-south1" to match Cloud Run region)
    DOCUMENT_AI_PROCESSOR_ID   - OCR processor ID from the Document AI console

Authentication:
    Uses Application Default Credentials (ADC).  On Cloud Run this is automatic
    via the service account.  Locally, run `gcloud auth application-default login`
    or set GOOGLE_APPLICATION_CREDENTIALS to a service-account JSON key path.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class DocumentAIBox:
    """Bounding box for a detected text segment."""
    x: int
    y: int
    width: int
    height: int
    text: str
    confidence: float


@dataclass
class DocumentAIResult:
    """Structured result from Document AI OCR processing."""
    text: str
    confidence: float
    boxes: List[DocumentAIBox] = field(default_factory=list)
    detected_languages: List[str] = field(default_factory=list)
    rotation_angle: float = 0.0   # detected page rotation in degrees
    page_width: int = 0
    page_height: int = 0


# ---------------------------------------------------------------------------
# Lazy-loaded client state
# ---------------------------------------------------------------------------

_client = None
_processor_name: Optional[str] = None
_init_error: Optional[str] = None


def _get_processor_name() -> str:
    """Build the full Document AI processor resource name from env vars."""
    global _processor_name

    if _processor_name is not None:
        return _processor_name

    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    location = os.environ.get("DOCUMENT_AI_LOCATION", "asia-south1")
    processor_id = os.environ.get("DOCUMENT_AI_PROCESSOR_ID")

    if not project:
        raise ValueError(
            "GOOGLE_CLOUD_PROJECT environment variable is required for Document AI"
        )
    if not processor_id:
        raise ValueError(
            "DOCUMENT_AI_PROCESSOR_ID environment variable is required for Document AI"
        )

    _processor_name = (
        f"projects/{project}/locations/{location}/processors/{processor_id}"
    )
    logger.info("Document AI processor: %s", _processor_name)
    return _processor_name


def _get_client():
    """Get or lazily create the Document AI client."""
    global _client, _init_error

    if _client is not None:
        return _client

    if _init_error is not None:
        raise RuntimeError(_init_error)

    try:
        from google.cloud import documentai_v1 as documentai  # noqa: F811

        location = os.environ.get("DOCUMENT_AI_LOCATION", "asia-south1")
        opts = {"api_endpoint": f"{location}-documentai.googleapis.com"}

        _client = documentai.DocumentProcessorServiceClient(
            client_options=opts,
        )
        return _client

    except ImportError:
        _init_error = (
            "google-cloud-documentai is not installed. "
            "Run: pip install google-cloud-documentai"
        )
        raise RuntimeError(_init_error)
    except Exception as e:
        _init_error = f"Failed to initialise Document AI client: {e}"
        raise RuntimeError(_init_error)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _detect_mime_type(data: bytes) -> str:
    """Detect MIME type from file magic bytes."""
    if len(data) >= 3 and data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if len(data) >= 4 and data[:4] == b"\x89PNG":
        return "image/png"
    if len(data) >= 4 and (data[:4] == b"II*\x00" or data[:4] == b"MM\x00*"):
        return "image/tiff"
    # Default to JPEG — most phone-camera uploads are JPEG
    return "image/jpeg"


def _extract_text_segment(full_text: str, text_anchor) -> str:
    """Extract a substring from the document text via a Document AI TextAnchor."""
    if not text_anchor or not text_anchor.text_segments:
        return ""

    parts: list[str] = []
    for segment in text_anchor.text_segments:
        start = int(segment.start_index) if segment.start_index else 0
        end = int(segment.end_index) if segment.end_index else 0
        if end > start:
            parts.append(full_text[start:end])

    return "".join(parts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def process_with_document_ai(
    image_data: bytes,
    mime_type: Optional[str] = None,
) -> DocumentAIResult:
    """
    Send an image to Google Cloud Document AI and return structured OCR results.

    Args:
        image_data: Raw image bytes (JPEG, PNG, or TIFF)
        mime_type:  MIME type override (auto-detected from magic bytes if omitted)

    Returns:
        DocumentAIResult with text, confidence, bounding boxes, and metadata

    Raises:
        RuntimeError: If the Document AI client cannot be initialised
        google.api_core.exceptions.*: On API-level errors (quota, auth, etc.)
    """
    from google.cloud import documentai_v1 as documentai

    if mime_type is None:
        mime_type = _detect_mime_type(image_data)

    client = _get_client()
    processor_name = _get_processor_name()

    request = documentai.ProcessRequest(
        name=processor_name,
        raw_document=documentai.RawDocument(
            content=image_data,
            mime_type=mime_type,
        ),
    )

    result = client.process_document(request=request)
    document = result.document

    # ----- Full extracted text ------------------------------------------------
    text = document.text or ""

    # ----- Page-level metadata ------------------------------------------------
    rotation_angle = 0.0
    page_width = 0
    page_height = 0
    detected_languages: List[str] = []

    if document.pages:
        page = document.pages[0]  # single-page image

        # Dimensions
        if page.dimension:
            page_width = int(page.dimension.width or 0)
            page_height = int(page.dimension.height or 0)

        # Detected rotation / transforms
        if page.transforms:
            for transform in page.transforms:
                # Document AI stores rotation in the 'rotation' field of
                # DocumentPageMatrix when type == ROTATION.
                rot = getattr(transform, "rotation", None)
                if rot is not None and rot != 0:
                    rotation_angle = float(rot)

        # Detected languages
        if page.detected_languages:
            for lang in page.detected_languages:
                if lang.language_code:
                    detected_languages.append(lang.language_code)

    # ----- Line-level boxes + confidence aggregation --------------------------
    boxes: List[DocumentAIBox] = []
    confidences: List[float] = []

    if document.pages:
        page = document.pages[0]

        for line in page.lines or []:
            line_text = _extract_text_segment(document.text, line.layout.text_anchor)
            line_conf = line.layout.confidence if line.layout else 0.0

            if not line_text.strip():
                continue

            confidences.append(line_conf)

            # Bounding poly → axis-aligned box
            if (
                line.layout
                and line.layout.bounding_poly
                and line.layout.bounding_poly.vertices
            ):
                verts = line.layout.bounding_poly.vertices
                xs = [v.x for v in verts if v.x is not None]
                ys = [v.y for v in verts if v.y is not None]

                if xs and ys:
                    x_min, x_max = int(min(xs)), int(max(xs))
                    y_min, y_max = int(min(ys)), int(max(ys))

                    boxes.append(DocumentAIBox(
                        x=x_min,
                        y=y_min,
                        width=max(1, x_max - x_min),
                        height=max(1, y_max - y_min),
                        text=line_text.strip(),
                        confidence=line_conf,
                    ))

    avg_confidence = (
        sum(confidences) / len(confidences) if confidences else 0.0
    )

    return DocumentAIResult(
        text=text.strip(),
        confidence=avg_confidence,
        boxes=boxes,
        detected_languages=detected_languages,
        rotation_angle=rotation_angle,
        page_width=page_width,
        page_height=page_height,
    )


def extract_text_safe(
    data: bytes,
    mime_type: Optional[str] = None,
) -> Tuple[Optional[DocumentAIResult], Optional[str]]:
    """
    Extract text via Document AI with graceful error handling.

    Drop-in replacement for ``processors.ocr.extract_text_safe`` — returns
    the same ``(result, warning)`` tuple shape so the caller (worker.py)
    does not need to change its result-handling logic.

    Args:
        data:      Raw image bytes
        mime_type: Optional MIME type override

    Returns:
        Tuple of (DocumentAIResult or None, warning string or None)
    """
    try:
        result = process_with_document_ai(data, mime_type)

        warning = None
        if not result.text.strip():
            warning = "Document AI returned no text"
        elif result.confidence < 0.5:
            warning = f"Low Document AI confidence: {result.confidence:.2f}"

        logger.info(
            "Document AI OCR complete: %d chars, confidence=%.3f, languages=%s",
            len(result.text),
            result.confidence,
            result.detected_languages or ["unknown"],
        )

        return result, warning

    except Exception as e:
        logger.warning("Document AI OCR failed: %s", e, exc_info=True)
        return None, f"Document AI OCR failed: {e}"


__all__ = [
    "DocumentAIBox",
    "DocumentAIResult",
    "extract_text_safe",
    "process_with_document_ai",
]
