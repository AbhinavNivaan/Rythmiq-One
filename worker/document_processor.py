"""
Document geometric pre-processor — Step 2 of the processing pipeline.

Responsibility:
    Take a raw photographed document image and return a geometrically
    corrected version: fine skew removed, cropped to the document's
    content boundaries. Colour, contrast, and sharpening are NOT touched
    here — that is the job of the downstream enhancement pipeline.

Designed for:
    Text-dense printed documents — mark sheets, certificates, printed
    agreements, contracts. NOT optimised for identity cards (PAN, Aadhaar)
    or hand-filled forms.

Pipeline (each step is an isolated function for easy replacement):
    1. _to_grayscale()        — convert BGR to single channel
    2. _adaptive_binarise()   — adaptive Gaussian threshold, handles uneven
                                lighting and shadows better than Otsu
    3. _detect_skew_angle()   — Hough line transform on the binary image to
                                find near-horizontal text lines, returns
                                median angle in degrees
    4. _deskew()              — apply affine rotation to the original colour
                                image; canvas expands so no content is lost
    5. _remove_background()   — use rembg ML model to remove the background,
                                compositing the result onto a white canvas

Public interface:
    process_document(image_path: str) -> str

    Returns the path of the corrected image.  On any failure it returns the
    ORIGINAL path unchanged so the rest of the pipeline can continue.
"""

from __future__ import annotations

import logging
import math
import os
import tempfile
from dataclasses import dataclass, field
from typing import Optional, Tuple

import cv2
import numpy as np
from numpy.typing import NDArray

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Minimum skew angle worth correcting — below this we skip rotation
# to avoid unnecessary resampling artefacts.
_SKEW_MIN_DEGREES: float = 0.4

# Maximum credible fine skew angle.  Larger angles are likely mis-detections
# caused by diagonal lines (table edges, ruled lines) rather than real skew.
# Large rotations (90°, 180°, 270°) are handled upstream by enhancement.py.
_SKEW_MAX_DEGREES: float = 20.0

# Minimum number of horizontal line detections needed to trust the skew angle.
_SKEW_MIN_LINE_COUNT: int = 4

# A line must span at least this fraction of the image width to count as a
# text line (rather than a short mark or border segment).
_SKEW_MIN_LINE_SPAN_FRACTION: float = 0.08

# Adaptive threshold parameters.
# blockSize controls how large a neighbourhood is used to compute the local
# threshold.  Larger values handle coarser lighting gradients.
# C is subtracted from the local mean — positive values pre-bias toward black.
_ADAPTIVE_BLOCK_SIZE: int = 51   # Must be odd
_ADAPTIVE_C: int = 10


# ---------------------------------------------------------------------------
# Result dataclass (returned internally for structured logging)
# ---------------------------------------------------------------------------

@dataclass
class _ProcessingResult:
    skew_angle_deg: float = 0.0
    skew_lines_found: int = 0
    skew_corrected: bool = False
    background_removed: bool = False
    fallback: bool = False
    fallback_reason: str = ""


# ---------------------------------------------------------------------------
# Step helpers — each is a pure-ish function so they can be replaced or
# monkey-patched independently in tests.
# ---------------------------------------------------------------------------

def _to_grayscale(img: NDArray[np.uint8]) -> NDArray[np.uint8]:
    """Convert a BGR colour image to an 8-bit single-channel grayscale image."""
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def _adaptive_binarise(gray: NDArray[np.uint8]) -> NDArray[np.uint8]:
    """
    Produce a clean binary image using adaptive Gaussian thresholding.

    Why adaptive rather than Otsu/global?
    Real-world phone photos of documents often have a lighting gradient
    across the page (bright centre, darker edges from shadow or shallow angle)
    or a dark background bleeding alongside the document.  A global threshold
    picks a single dividing value that fails on one side of such a gradient.
    Adaptive thresholding computes a local threshold per pixel using its
    neighbourhood, which handles these gradients robustly.

    The result is inverted so that text (originally dark) becomes WHITE on a
    BLACK background — the convention expected by Hough transforms and
    contour finders below.
    """
    # Gentle blur first to suppress JPEG compression artefacts and sensor noise,
    # which would otherwise register as tiny spurious text-like edges.
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    binary = cv2.adaptiveThreshold(
        blurred,
        maxValue=255,
        adaptiveMethod=cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        thresholdType=cv2.THRESH_BINARY_INV,   # invert: text = white
        blockSize=_ADAPTIVE_BLOCK_SIZE,
        C=_ADAPTIVE_C,
    )
    return binary


def _detect_skew_angle(
    binary: NDArray[np.uint8],
    img_width: int,
) -> Tuple[float, int]:
    """
    Detect document skew angle using Probabilistic Hough Line Transform.

    Strategy:
    1. Dilate horizontally to merge individual character blobs into text-line
       strokes.  This gives the Hough transform longer, more reliable segments
       to work with.
    2. Run HoughLinesP to find line segments.
    3. Keep only near-horizontal lines (angle within ±_SKEW_MAX_DEGREES of 0°)
       that span at least _SKEW_MIN_LINE_SPAN_FRACTION of the image width.
    4. Take the median angle (robust against outlier lines from ruled borders,
       table edges, etc.).

    Returns:
        (angle_degrees, n_lines_used)
        angle_degrees is the tilt to correct: positive = clockwise tilt,
        negative = anti-clockwise tilt.
        n_lines_used is the number of qualifying line detections.
    """
    # Dilate horizontally to connect adjacent characters into line strokes.
    # A narrow, wide kernel captures the horizontal structure of a text line.
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
    dilated = cv2.dilate(binary, kernel)

    min_line_length = max(30, int(img_width * _SKEW_MIN_LINE_SPAN_FRACTION))

    lines = cv2.HoughLinesP(
        dilated,
        rho=1,
        theta=np.pi / 180,
        threshold=60,
        minLineLength=min_line_length,
        maxLineGap=8,
    )

    if lines is None:
        return 0.0, 0

    angles: list[float] = []
    for line in lines:
        x1, y1, x2, y2 = line[0]
        dx = x2 - x1
        dy = y2 - y1

        # Skip vertical or near-vertical lines (dx too small risks division issues)
        if abs(dx) < 1:
            continue

        angle_deg = math.degrees(math.atan2(dy, dx))

        # Only keep near-horizontal lines — real text lines sit within ±_SKEW_MAX_DEGREES
        if abs(angle_deg) <= _SKEW_MAX_DEGREES:
            angles.append(angle_deg)

    if not angles:
        return 0.0, 0

    # Median is more robust than mean against the occasional diagonal element
    # (table border, document edge, underline at a different slant).
    median_angle = float(np.median(angles))
    return median_angle, len(angles)


def _deskew(
    img: NDArray[np.uint8],
    angle_deg: float,
) -> NDArray[np.uint8]:
    """
    Rotate the image by -angle_deg to correct for skew.

    The canvas is expanded to fit the full rotated content — no document
    corner is clipped.  Empty border areas are filled with white (255, 255, 255)
    to match typical document paper colour and to help the downstream crop
    step distinguish fill from real content.

    Why -angle_deg?
    The Hough transform returns the angle that text lines make with the
    horizontal axis.  A positive angle means the lines tilt clockwise, so
    we rotate the image anti-clockwise (negative angle) to flatten them.
    """
    h, w = img.shape[:2]
    center = (w / 2.0, h / 2.0)

    M = cv2.getRotationMatrix2D(center, -angle_deg, scale=1.0)

    # Compute the new bounding box required to contain all four corners of the
    # original image after rotation.
    cos_a = abs(M[0, 0])
    sin_a = abs(M[0, 1])
    new_w = int(h * sin_a + w * cos_a)
    new_h = int(h * cos_a + w * sin_a)

    # Shift the rotation centre so the whole image lands inside the new canvas.
    M[0, 2] += (new_w - w) / 2.0
    M[1, 2] += (new_h - h) / 2.0

    rotated = cv2.warpAffine(
        img,
        M,
        (new_w, new_h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),   # white fill
    )
    return rotated


def _remove_background(img: NDArray[np.uint8]) -> NDArray[np.uint8]:
    """
    Remove the image background using the rembg ML model.

    Converts the result to a BGR image composited onto a white canvas so
    the output format matches what the rest of the pipeline expects (colour
    JPEG, no alpha channel).

    Strategy:
        1. Convert BGR numpy → RGB PIL Image (rembg expects PIL or bytes).
        2. Call rembg.remove() to get an RGBA PIL Image.  rembg uses the
           U²-Net or IS-Net model depending on the installed version.
        3. Composite the RGBA result over a white RGB canvas using the
           alpha channel as a mask.  Background areas become white rather
           than transparent, preserving compatibility with JPEG encoding.
        4. Convert the composited RGB PIL Image back to a BGR numpy array.

    Returns:
        Background-removed image as a BGR uint8 numpy array, same dimensions
        as the input.
    """
    from rembg import remove as _rembg_remove
    from PIL import Image as _PILImage

    # BGR (OpenCV) → RGB (PIL)
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    pil_img = _PILImage.fromarray(rgb)

    # Remove background — returns RGBA PIL Image
    rgba: _PILImage.Image = _rembg_remove(pil_img)

    # Composite onto white canvas
    white = _PILImage.new("RGB", rgba.size, (255, 255, 255))
    white.paste(rgba, mask=rgba.split()[3])  # alpha channel as mask

    # RGB PIL → BGR numpy
    return cv2.cvtColor(np.array(white), cv2.COLOR_RGB2BGR)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def process_document(image_path: str) -> str:
    """
    Apply geometric pre-processing to a raw photographed document image.

    Steps applied (in order):
        1. Load original image in full colour
        2. Grayscale conversion for analysis
        3. Adaptive binarisation for robust skew detection under uneven light
        4. Hough line transform to measure text-line angle
        5. Rotation correction applied to the colour image
        6. Background removal via rembg ML model

    The corrected image is saved as a JPEG alongside the source file
    (same directory, ``_proc`` suffix before the extension).

    Failure contract:
        On ANY error the function logs a warning and returns the ORIGINAL
        image_path unchanged.  The caller can always continue with the
        unprocessed file — step 2 degrading gracefully is far better than
        crashing the worker.

    Args:
        image_path: Absolute or relative path to the raw input image.

    Returns:
        Path to the processed image, or ``image_path`` if processing failed.
    """
    result = _ProcessingResult()

    try:
        # ----------------------------------------------------------------
        # 1. Load
        # ----------------------------------------------------------------
        img = cv2.imread(image_path, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError(f"cv2.imread returned None for path: {image_path!r}")

        original_h, original_w = img.shape[:2]
        logger.info(
            "document_processor: loaded image %s (%d×%d)",
            os.path.basename(image_path),
            original_w,
            original_h,
        )

        # ----------------------------------------------------------------
        # 2. Grayscale
        # ----------------------------------------------------------------
        gray = _to_grayscale(img)

        # ----------------------------------------------------------------
        # 3. Adaptive binarisation
        # ----------------------------------------------------------------
        binary = _adaptive_binarise(gray)

        # ----------------------------------------------------------------
        # 4. Detect skew angle
        # ----------------------------------------------------------------
        angle, n_lines = _detect_skew_angle(binary, original_w)
        result.skew_angle_deg = angle
        result.skew_lines_found = n_lines

        logger.info(
            "document_processor: skew detection — angle=%.2f° from %d lines",
            angle,
            n_lines,
        )

        # ----------------------------------------------------------------
        # 5. Deskew (apply to the original colour image)
        # ----------------------------------------------------------------
        working = img  # start with the colour image
        if n_lines >= _SKEW_MIN_LINE_COUNT and abs(angle) >= _SKEW_MIN_DEGREES:
            working = _deskew(img, angle)
            result.skew_corrected = True
            logger.info(
                "document_processor: deskewed by %.2f°  (%d→%d px wide)",
                angle,
                original_w,
                working.shape[1],
            )
        else:
            logger.info(
                "document_processor: skew correction skipped "
                "(angle=%.2f° < %.1f° threshold  or  only %d/%d lines)",
                angle,
                _SKEW_MIN_DEGREES,
                n_lines,
                _SKEW_MIN_LINE_COUNT,
            )

        # ----------------------------------------------------------------
        # 6. Remove background (disabled — uses too much memory on Cloud Run
        #    and is not needed for document scanning)
        # ----------------------------------------------------------------
        # working = _remove_background(working)
        # result.background_removed = True
        # logger.info("document_processor: background removed via rembg")

        # ----------------------------------------------------------------
        # 8. Save
        # ----------------------------------------------------------------
        stem, ext = os.path.splitext(image_path)
        output_path = f"{stem}_proc.jpg"

        encode_params = [cv2.IMWRITE_JPEG_QUALITY, 95]
        success = cv2.imwrite(output_path, working, encode_params)
        if not success:
            raise IOError(f"cv2.imwrite failed writing to {output_path!r}")

        logger.info(
            "document_processor: saved → %s  (%d×%d)  "
            "[skew_corrected=%s  background_removed=%s]",
            os.path.basename(output_path),
            working.shape[1],
            working.shape[0],
            result.skew_corrected,
            result.background_removed,
        )

        return output_path

    except Exception as exc:  # noqa: BLE001
        # Step 2 must never crash the worker.  Log the problem, return the
        # original path so the pipeline continues with the unprocessed image.
        logger.warning(
            "document_processor: processing failed — returning original path  "
            "[reason: %s: %s]",
            type(exc).__name__,
            exc,
            exc_info=True,
        )
        result.fallback = True
        result.fallback_reason = str(exc)
        return image_path
