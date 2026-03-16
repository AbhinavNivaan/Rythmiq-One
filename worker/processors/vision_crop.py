"""
Vision API document boundary detector.

Uses Google Cloud Vision API objectLocalization to find the physical
paper/document object in a scene photo, returning 4 ordered corner
points ready for a warpPerspective call.

Strategy (in order, first success wins):
  1. objectLocalization — finds "Paper", "Document", "Book" etc. as
     physical objects and returns a tight bounding polygon.
  2. TEXT_DETECTION bounding union — union of all detected text block
     bounding boxes, expanded by a configurable margin fraction to
     include the paper edge beyond the text.

Fails gracefully (returns None) when:
  - Vision API is unreachable or credentials are missing
  - No paper-like object or text is detected
  - The returned polygon cannot be reduced to exactly 4 corners
"""

from __future__ import annotations

import logging
from typing import Optional

import cv2
import numpy as np
from numpy.typing import NDArray

logger = logging.getLogger(__name__)

# Object names (lowercase) that represent a document / paper in objectLocalization.
_PAPER_LABELS: frozenset[str] = frozenset({
    "paper", "document", "book", "letter", "envelope",
    "newspaper", "magazine", "form", "invoice", "receipt",
})

# Minimum objectLocalization score to accept.
_VISION_MIN_OBJ_SCORE = 0.40

# When falling back to text-union, expand the detected text bounding box
# by this fraction of each dimension to capture the paper margin.
_TEXT_MARGIN_FRACTION = 0.06  # 6 % padding on each side

# Lazy client singleton.
_vision_client = None


def _get_client():
    global _vision_client
    if _vision_client is None:
        from google.cloud import vision  # type: ignore[import]
        _vision_client = vision.ImageAnnotatorClient()
    return _vision_client


def _norm_verts_to_pixels(
    norm_verts: list,
    img_w: int,
    img_h: int,
) -> Optional[NDArray[np.float32]]:
    """
    Convert normalized (0–1) Vision API vertices to pixel coordinates.
    objectLocalization returns NormalizedVertex objects with .x / .y in [0, 1].
    """
    if not norm_verts:
        return None
    pts = np.array([[v.x * img_w, v.y * img_h] for v in norm_verts], dtype=np.float32)
    return pts if len(pts) >= 3 else None


def _poly_to_4_corners(
    pts: NDArray[np.float32],
) -> Optional[NDArray[np.float32]]:
    """
    Reduce an N-vertex numpy array to exactly 4 corners via convex-hull
    approximation.  Returns None if fewer than 3 vertices are provided.
    """
    if len(pts) == 4:
        return pts

    if len(pts) < 3:
        return None

    hull = cv2.convexHull(pts.reshape(-1, 1, 2).astype(np.int32))
    hull_peri = cv2.arcLength(hull, True)
    for eps in (0.02, 0.04, 0.06, 0.08, 0.10, 0.15):
        approx = cv2.approxPolyDP(hull, eps * hull_peri, True)
        if len(approx) == 4:
            return approx.reshape(4, 2).astype(np.float32)

    return None


def _image_dimensions(image_bytes: bytes) -> tuple[int, int]:
    """Return (width, height) from raw image bytes."""
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return 1, 1
    h, w = img.shape[:2]
    return w, h


def _try_object_localization(
    image_bytes: bytes,
    img_w: int,
    img_h: int,
) -> Optional[NDArray[np.float32]]:
    """
    Stage 1: objectLocalization.
    Finds physical paper/document objects and returns 4 pixel-space corners.
    """
    from google.cloud import vision  # type: ignore[import]
    client = _get_client()
    image = vision.Image(content=image_bytes)
    response = client.object_localization(image=image)

    if response.error.message:
        logger.warning("[VISION] objectLocalization error: %s", response.error.message)
        return None

    candidates = [
        obj for obj in response.localized_object_annotations
        if obj.name.lower() in _PAPER_LABELS and obj.score >= _VISION_MIN_OBJ_SCORE
    ]

    if not candidates:
        logger.info("[VISION] objectLocalization: no paper-like object found")
        return None

    # Pick the highest-confidence match.
    best = max(candidates, key=lambda o: o.score)
    logger.info(
        "[VISION] objectLocalization: '%s' (score=%.2f)", best.name, best.score
    )

    pts = _norm_verts_to_pixels(best.bounding_poly.normalized_vertices, img_w, img_h)
    if pts is None:
        return None

    return _poly_to_4_corners(pts)


def _try_text_union(
    image_bytes: bytes,
    img_w: int,
    img_h: int,
) -> Optional[NDArray[np.float32]]:
    """
    Stage 2: TEXT_DETECTION bounding-box union.
    Computes the axis-aligned union of all detected text word bounding boxes,
    then expands it by _TEXT_MARGIN_FRACTION on each side to reach the paper
    edge, and returns the 4 rectangle corners.
    """
    from google.cloud import vision  # type: ignore[import]
    client = _get_client()
    image = vision.Image(content=image_bytes)
    response = client.text_detection(image=image)

    if response.error.message:
        logger.warning("[VISION] text_detection error: %s", response.error.message)
        return None

    annotations = response.text_annotations
    if not annotations:
        logger.info("[VISION] text_detection: no text found")
        return None

    # text_annotations[0] is the full-image text block with a combined bounding poly.
    poly = annotations[0].bounding_poly.vertices
    if len(poly) < 4:
        return None

    xs = [v.x for v in poly]
    ys = [v.y for v in poly]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)

    # Expand by margin to include the paper edge beyond the text region.
    pad_x = int((x_max - x_min) * _TEXT_MARGIN_FRACTION)
    pad_y = int((y_max - y_min) * _TEXT_MARGIN_FRACTION)
    x_min = max(0, x_min - pad_x)
    y_min = max(0, y_min - pad_y)
    x_max = min(img_w, x_max + pad_x)
    y_max = min(img_h, y_max + pad_y)

    logger.info(
        "[VISION] text_detection union bbox: (%d,%d)→(%d,%d) + %dpx margin",
        x_min, y_min, x_max, y_max, max(pad_x, pad_y),
    )

    corners = np.array([
        [x_min, y_min],
        [x_max, y_min],
        [x_max, y_max],
        [x_min, y_max],
    ], dtype=np.float32)
    return corners


def get_crop_corners(
    image_bytes: bytes,
) -> Optional[NDArray[np.float32]]:
    """
    Locate the document boundary in a scene photo using Vision API.

    Tries objectLocalization first (physical paper object), then falls
    back to the text-annotation bounding union + margin expansion.

    The returned array is NOT yet ordered — pass it through
    `_order_corners` before calling `_perspective_crop`.

    Args:
        image_bytes: Raw JPEG or PNG image bytes.

    Returns:
        4×2 float32 array of corner points, or None if detection fails.
    """
    try:
        img_w, img_h = _image_dimensions(image_bytes)

        # Stage 1: Physical object detection (best for document on table).
        corners = _try_object_localization(image_bytes, img_w, img_h)
        if corners is not None:
            return corners

        # Stage 2: Text bounding union (catches documents with lots of text
        # even when object detection doesn't find a clear paper object).
        corners = _try_text_union(image_bytes, img_w, img_h)
        return corners

    except Exception as exc:
        logger.warning(
            "[VISION] detection unavailable, using OpenCV fallback: %s", exc
        )
        return None
