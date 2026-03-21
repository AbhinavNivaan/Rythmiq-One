"""
CPU-only image enhancement for Camber worker.

Implements:
- Orientation correction (auto-rotate based on EXIF or content analysis)
- Large rotation detection (90°/180° via aspect ratio and text orientation)
- Light denoising (non-local means or bilateral filter)
- Color normalization (white balance, contrast adjustment)

All operations are:
- Modular (can be applied independently)
- Testable (pure functions where possible)
- CPU-only (no GPU acceleration)

Guardrails:
- GUARD-001: Skip denoise+CLAHE for readable images (quality>0.75)
- GUARD-003: Detect and correct 90°/180° rotations
"""

from __future__ import annotations

import io
import logging
import math
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple, Literal

import cv2
import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageOps

from models import EnhancementResult, QualityBreakdown
from errors import WorkerError, ErrorCode, ProcessingStage


logger = logging.getLogger(__name__)

# Guardrail thresholds
READABLE_QUALITY_THRESHOLD = 0.75  # GUARD-001: Skip enhancement above this


@dataclass
class EnhancementOptions:
    """Configuration for enhancement operations."""
    correct_orientation: bool = True
    denoise: bool = True
    normalize_color: bool = True
    denoise_strength: int = 7  # h parameter for fastNlMeansDenoising
    clahe_clip_limit: float = 2.0
    clahe_grid_size: Tuple[int, int] = (8, 8)
    # GUARD-001: Skip enhancement for readable images
    quality_score: Optional[float] = None
    is_readable: bool = False
    # Document type: "photo", "signature", or "document"
    document_type: str = "document"
    # Rich vault taxonomy — category and subtype chosen by the user in the app.
    # e.g. category="photograph", subtype="Passport Photo"
    #      category="identity",   subtype="PAN Card"
    # Used to override enhancement routing and behaviour beyond the coarse 3-value
    # document_type enum.
    document_category: Optional[str] = None
    document_subtype: Optional[str] = None
    # Full quality breakdown — used by photo/signature branches for per-metric decisions
    quality_breakdown: Optional[QualityBreakdown] = None
    # WP-7: Pre-binarise in enhancement so Sauvola operates on the full-resolution
    # CLAHE-normalised image rather than on a post-resize downsampled copy.
    # Only active when GUARD-001 does NOT skip enhancement (i.e. skip_enhancement=False).
    # For readable/high-quality images the Stage 5 convert_colour_mode path handles it.
    binarise_output: bool = False


def _apply_exif_transpose(data: bytes) -> bytes:
    """
    Apply Pillow's exif_transpose to upright the image using its EXIF
    orientation tag before any OpenCV processing.

    - Returns the original bytes unchanged when no rotation is needed
      (avoids a JPEG re-encode cycle in the common case).
    - Resets the orientation tag to 1 in the output so downstream
      correct_orientation_exif calls are a guaranteed no-op.
    - Any error returns original bytes silently.
    """
    try:
        pil = Image.open(io.BytesIO(data))
        transposed = ImageOps.exif_transpose(pil)
        if transposed is pil:
            return data  # already upright — skip re-encode
        buf = io.BytesIO()
        # Save as lossless PNG so the pipeline works on uncompressed pixels.
        # The final JPEG encode happens once at the end of enhance_image.
        transposed.save(buf, format="PNG")
        logger.info("[ENHANCEMENT] EXIF transpose applied (phone camera rotation corrected)")
        return buf.getvalue()
    except Exception:
        return data


def decode_image(data: bytes) -> NDArray[np.uint8]:
    """
    Decode image bytes to OpenCV BGR array.
    
    Args:
        data: Raw image bytes
        
    Returns:
        BGR image array
        
    Raises:
        WorkerError: If image cannot be decoded
    """
    nparr = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if img is None:
        raise WorkerError(
            code=ErrorCode.DECODE_FAILED,
            stage=ProcessingStage.ENHANCE,
            message="Failed to decode image for enhancement",
        )
    
    return img


def encode_image(
    img: NDArray[np.uint8],
    format: str = "jpeg",
    quality: int = 95,
) -> bytes:
    """
    Encode image array to bytes.
    
    Args:
        img: BGR image array
        format: Output format (jpeg, png)
        quality: JPEG quality (1-100)
        
    Returns:
        Encoded image bytes
    """
    if format.lower() in ("jpeg", "jpg"):
        params = [cv2.IMWRITE_JPEG_QUALITY, quality]
        ext = ".jpg"
    elif format.lower() == "png":
        params = [cv2.IMWRITE_PNG_COMPRESSION, 6]
        ext = ".png"
    else:
        params = [cv2.IMWRITE_JPEG_QUALITY, quality]
        ext = ".jpg"
    
    success, encoded = cv2.imencode(ext, img, params)
    
    if not success:
        raise WorkerError(
            code=ErrorCode.ENHANCE_FAILED,
            stage=ProcessingStage.ENHANCE,
            message=f"Failed to encode image as {format}",
        )
    
    return encoded.tobytes()


def detect_large_rotation(img: NDArray[np.uint8]) -> Optional[Literal[90, 180, 270]]:
    """
    GUARD-003: Detect 90°/180°/270° rotation using text line orientation.
    
    Uses Hough line detection to determine if text runs horizontally
    or vertically, and checks for upside-down orientation.
    
    Args:
        img: BGR image array
        
    Returns:
        Rotation angle (90, 180, 270) or None if no large rotation detected
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]
    
    # Detect edges
    edges = cv2.Canny(gray, 50, 150)
    
    # Use Hough transform to detect lines
    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180,
        threshold=80,
        minLineLength=30,
        maxLineGap=10,
    )
    
    if lines is None or len(lines) < 10:
        return None
    
    # Count horizontal vs vertical lines
    horizontal_count = 0
    vertical_count = 0
    
    for line in lines:
        x1, y1, x2, y2 = line[0]
        dx = abs(x2 - x1)
        dy = abs(y2 - y1)
        
        if dx > dy * 3:  # Mostly horizontal
            horizontal_count += 1
        elif dy > dx * 3:  # Mostly vertical
            vertical_count += 1
    
    # If portrait image has mostly vertical lines -> likely 90° rotated
    # If landscape image has mostly vertical lines -> likely 90° rotated
    aspect_ratio = w / h
    
    # Check for 90°/270° rotation: text lines should be horizontal in a properly oriented doc
    if vertical_count > horizontal_count * 2:
        # Text appears vertical - image is rotated 90° or 270°
        # Use aspect ratio to guess direction
        if aspect_ratio < 1:  # Portrait mode
            return 90
        else:
            return 270
    
    # Check for 180° rotation using text region analysis
    # Documents typically have more content in the upper portion
    # Split image into top and bottom halves
    top_half = edges[:h//2, :]
    bottom_half = edges[h//2:, :]
    
    top_density = np.sum(top_half > 0)
    bottom_density = np.sum(bottom_half > 0)
    
    # If bottom half has significantly more content, image might be upside down
    # This is a heuristic - most documents have headers/titles at top
    if bottom_density > top_density * 1.8 and top_density > 0:
        return 180
    
    return None


def apply_large_rotation(
    img: NDArray[np.uint8],
    angle: Literal[90, 180, 270],
) -> NDArray[np.uint8]:
    """
    Apply exact 90°/180°/270° rotation.
    
    Args:
        img: BGR image array
        angle: Rotation angle (90, 180, or 270 degrees)
        
    Returns:
        Rotated image
    """
    if angle == 90:
        return cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    elif angle == 180:
        return cv2.rotate(img, cv2.ROTATE_180)
    elif angle == 270:
        return cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return img


def correct_orientation(img: NDArray[np.uint8]) -> Tuple[NDArray[np.uint8], bool]:
    """
    Correct image orientation using text line detection.
    
    For documents, we detect text orientation by analyzing
    horizontal vs vertical line density.
    
    Now includes GUARD-003: large rotation detection (90°/180°/270°)
    before skew correction.
    
    Uses robust median-angle estimation (resistant to outlier lines)
    instead of histogram peak, and applies Hough lines on multiple
    preprocessed edge maps for better detection on low-contrast images.
    
    Args:
        img: BGR image array
        
    Returns:
        Tuple of (corrected image, was_corrected)
    """
    # GUARD-003: Check for large rotations first
    large_rotation = detect_large_rotation(img)
    if large_rotation is not None:
        logger.info(f"[ENHANCEMENT] large rotation corrected: {large_rotation}°")
        img = apply_large_rotation(img, large_rotation)
        # Continue with skew correction on the rotated image
    
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = img.shape[:2]
    min_line_len = max(30, w // 8)

    # Try multiple edge detection approaches to find lines
    edge_candidates = []

    # Standard Canny
    edges1 = cv2.Canny(gray, 50, 150)
    edge_candidates.append(edges1)

    # Bilateral + Canny (better for textured backgrounds)
    bilateral = cv2.bilateralFilter(gray, d=9, sigmaColor=75, sigmaSpace=75)
    edges2 = cv2.Canny(bilateral, 30, 100)
    edge_candidates.append(edges2)

    # Blurred + lower thresholds (for low contrast)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges3 = cv2.Canny(blurred, 20, 80)
    edge_candidates.append(edges3)

    # Collect angles from all edge maps
    all_angles: list[float] = []
    for edges in edge_candidates:
        lines = cv2.HoughLinesP(
            edges,
            rho=1,
            theta=np.pi / 180,
            threshold=60,
            minLineLength=min_line_len,
            maxLineGap=10,
        )
        if lines is None:
            continue
        for line in lines:
            x1, y1, x2, y2 = line[0]
            dx = x2 - x1
            dy = y2 - y1
            if abs(dx) < 1:
                continue
            angle_deg = math.degrees(math.atan2(dy, dx))
            # Only consider near-horizontal lines (within ±45°)
            if abs(angle_deg) <= 45:
                all_angles.append(angle_deg)

    if len(all_angles) < 3:
        return img, False

    # Robust angle: use median (resistant to outlier lines)
    dominant_angle = float(np.median(all_angles))
    
    # Only correct if angle is significant (> 0.5 degree)
    if abs(dominant_angle) < 0.5:
        return img, False

    logger.info(
        f"[ENHANCEMENT] Hough skew correction: {dominant_angle:.2f}° "
        f"(from {len(all_angles)} lines)"
    )
    
    # Rotate image
    center = (w / 2.0, h / 2.0)
    rotation_matrix = cv2.getRotationMatrix2D(center, dominant_angle, 1.0)
    
    cos_a = abs(rotation_matrix[0, 0])
    sin_a = abs(rotation_matrix[0, 1])
    new_w = int(h * sin_a + w * cos_a)
    new_h = int(h * cos_a + w * sin_a)
    
    rotation_matrix[0, 2] += (new_w - w) / 2
    rotation_matrix[1, 2] += (new_h - h) / 2
    
    # Apply rotation — use BORDER_CONSTANT (white) to avoid streak artifacts
    rotated = cv2.warpAffine(
        img,
        rotation_matrix,
        (new_w, new_h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )
    
    return rotated, True


def denoise(
    img: NDArray[np.uint8],
    strength: int = 7,
) -> Tuple[NDArray[np.uint8], bool]:
    """
    Apply light denoising using fast non-local means.
    
    Args:
        img: BGR image array
        strength: Denoising strength (h parameter)
        
    Returns:
        Tuple of (denoised image, was_applied)
    """
    try:
        # Use fastNlMeansDenoisingColored for color images
        denoised = cv2.fastNlMeansDenoisingColored(
            img,
            None,
            h=strength,
            hForColorComponents=strength,
            templateWindowSize=7,
            searchWindowSize=21,
        )
        return denoised, True
    except cv2.error:
        # If denoising fails, return original
        return img, False


def normalize_color(
    img: NDArray[np.uint8],
    clip_limit: float = 2.0,
    grid_size: Tuple[int, int] = (8, 8),
) -> Tuple[NDArray[np.uint8], bool]:
    """
    Normalize colors using CLAHE (Contrast Limited Adaptive Histogram Equalization).
    
    This improves contrast while preventing over-amplification of noise.
    Applied to the L channel of LAB color space.
    
    Args:
        img: BGR image array
        clip_limit: CLAHE clip limit
        grid_size: CLAHE tile grid size
        
    Returns:
        Tuple of (normalized image, was_applied)
    """
    try:
        # Convert to LAB color space
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        
        # Split channels
        l_channel, a_channel, b_channel = cv2.split(lab)
        
        # Apply CLAHE to L channel
        clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=grid_size)
        l_enhanced = clahe.apply(l_channel)
        
        # Merge channels back
        lab_enhanced = cv2.merge([l_enhanced, a_channel, b_channel])
        
        # Convert back to BGR
        result = cv2.cvtColor(lab_enhanced, cv2.COLOR_LAB2BGR)
        
        return result, True
    except cv2.error:
        # If normalization fails, return original
        return img, False


def auto_white_balance(img: NDArray[np.uint8]) -> Tuple[NDArray[np.uint8], bool]:
    """
    Apply simple white balance correction using gray world assumption.
    
    Args:
        img: BGR image array
        
    Returns:
        Tuple of (white-balanced image, was_applied)
    """
    try:
        # Calculate mean of each channel
        b_mean = np.mean(img[:, :, 0])
        g_mean = np.mean(img[:, :, 1])
        r_mean = np.mean(img[:, :, 2])
        
        # Calculate gray world average
        gray_mean = (b_mean + g_mean + r_mean) / 3
        
        # Calculate scale factors
        b_scale = gray_mean / b_mean if b_mean > 0 else 1.0
        g_scale = gray_mean / g_mean if g_mean > 0 else 1.0
        r_scale = gray_mean / r_mean if r_mean > 0 else 1.0
        
        # Clamp scale factors to prevent extreme corrections
        b_scale = np.clip(b_scale, 0.5, 2.0)
        g_scale = np.clip(g_scale, 0.5, 2.0)
        r_scale = np.clip(r_scale, 0.5, 2.0)
        
        # Apply scaling
        result = img.astype(np.float32)
        result[:, :, 0] = np.clip(result[:, :, 0] * b_scale, 0, 255)
        result[:, :, 1] = np.clip(result[:, :, 1] * g_scale, 0, 255)
        result[:, :, 2] = np.clip(result[:, :, 2] * r_scale, 0, 255)
        
        return result.astype(np.uint8), True
    except Exception:
        return img, False


# ---------------------------------------------------------------------------
# EXIF orientation
# ---------------------------------------------------------------------------

# Maps EXIF orientation tag value → clockwise degrees needed to correct.
# Flip/mirror values (2, 4, 5, 7) are ignored (treated as 0).
_EXIF_ORIENTATION_TAG = 0x0112  # 274
_EXIF_TO_CW_DEGREES: Dict[int, int] = {
    1: 0,
    3: 180,
    6: 270,  # Shot rotated 90° CW  → rotate 90° CCW (= 270° CW) to fix
    8: 90,   # Shot rotated 90° CCW → rotate 90° CW to fix
}


def get_exif_rotation_angle(data: bytes) -> int:
    """
    Read the EXIF orientation tag and return the clockwise rotation needed.

    Returns 0 when orientation is normal or EXIF is unavailable.
    """
    try:
        pil_img = Image.open(io.BytesIO(data))
        exif = pil_img.getexif()
        orientation = exif.get(_EXIF_ORIENTATION_TAG, 1)
        return _EXIF_TO_CW_DEGREES.get(int(orientation), 0)
    except Exception:
        return 0


def correct_orientation_exif(
    img: NDArray[np.uint8],
    data: bytes,
) -> Tuple[NDArray[np.uint8], bool]:
    """
    Rotate image to correct EXIF orientation.

    Safe for photos: no Hough detection, no warpAffine artifacts.

    Returns:
        Tuple of (corrected image, was_rotated)
    """
    angle = get_exif_rotation_angle(data)
    if angle == 0:
        return img, False
    rotated = apply_large_rotation(img, angle)  # type: ignore[arg-type]
    logger.info(f"[ENHANCEMENT] EXIF rotation applied: {angle}°")
    return rotated, True


# ---------------------------------------------------------------------------
# Gamma correction (photos — exposure fix)
# ---------------------------------------------------------------------------

# Sharpness threshold: normalized Laplacian variance < 0.2 (≈ raw var < 100)
_PHOTO_SHARPNESS_THRESHOLD = 0.20
# Exposure thresholds for photos
_PHOTO_BRIGHTNESS_MIN = 80.0
_PHOTO_BRIGHTNESS_MAX = 200.0


def _compute_gamma_for_brightness(mean_brightness: float, target: float = 140.0) -> float:
    """
    Compute the gamma that maps *mean_brightness* → *target*.

    output = (input/255)^gamma * 255
    At mean pixel value m:  target/255 = (m/255)^gamma
    ⟹ gamma = log(target/255) / log(m/255)
    """
    m = max(mean_brightness, 1.0)
    gamma = math.log(target / 255.0) / math.log(m / 255.0)
    return float(max(0.3, min(4.0, gamma)))


def gamma_correct(img: NDArray[np.uint8], gamma: float) -> NDArray[np.uint8]:
    """Apply gamma correction via a lookup table (fast, exact)."""
    table = np.array(
        [((i / 255.0) ** gamma) * 255 for i in range(256)],
        dtype=np.uint8,
    )
    return cv2.LUT(img, table)


# ---------------------------------------------------------------------------
# Unsharp mask (photos & signatures — sharpening)
# ---------------------------------------------------------------------------

def apply_unsharp_mask(
    img: NDArray[np.uint8],
    sigma: float = 1.0,
    strength: float = 1.5,
) -> NDArray[np.uint8]:
    """
    Sharpen image via unsharp masking.

    output = original + strength * (original - blurred)

    Args:
        sigma: Gaussian blur sigma
        strength: Sharpening amount
    """
    blurred = cv2.GaussianBlur(img, (0, 0), sigma)
    return cv2.addWeighted(img, 1.0 + strength, blurred, -strength, 0)


# ---------------------------------------------------------------------------
# Bilateral denoising (signatures — edge-preserving)
# ---------------------------------------------------------------------------

def bilateral_denoise(
    img: NDArray[np.uint8],
) -> Tuple[NDArray[np.uint8], bool]:
    """
    Apply bilateral filter.

    Preserves sharp ink edges better than NLM denoising,
    making it suitable for signature images.
    """
    try:
        result = cv2.bilateralFilter(img, d=9, sigmaColor=75, sigmaSpace=75)
        return result, True
    except cv2.error:
        return img, False


# ---------------------------------------------------------------------------
# Otsu binarization (signatures — clean scan output)
# ---------------------------------------------------------------------------

def otsu_binarize(
    img: NDArray[np.uint8],
) -> Tuple[NDArray[np.uint8], bool]:
    """
    Apply Otsu thresholding to produce a clean black-on-white signature.

    Converts to grayscale, applies OTSU threshold, then converts
    back to 3-channel so downstream stages stay consistent.
    """
    try:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        result = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
        return result, True
    except cv2.error:
        return img, False


# ---------------------------------------------------------------------------
# Border crop (scanner black-border removal)
# ---------------------------------------------------------------------------

# Only crop if the detected border is thicker than this fraction of the image
_MIN_BORDER_FRACTION = 0.02   # 2 % of the shorter dimension
# Don't crop if result would be less than this fraction of original area
_MIN_CROP_AREA_FRACTION = 0.50
# Pixels to add back as padding around the tight content bounding rect
_CROP_PADDING = 4


def crop_borders(
    img: NDArray[np.uint8],
    black_threshold: int = 15,
) -> Tuple[NDArray[np.uint8], bool]:
    """
    Remove uniform dark (scanner) borders detected by brightness thresholding.

    Algorithm:
      1. Threshold the grayscale image: pixels > black_threshold are "content".
      2. Find the bounding rect of all content pixels.
      3. Only crop if the detected border on any side exceeds 2 % of that
         dimension — this avoids spurious crops on naturally dark-edged images.
      4. A safety check rejects the crop if the result would be < 50 % of the
         original area (guards against threshold mis-fires on very dark images).

    Args:
        img: BGR image array
        black_threshold: Pixels at or below this value are treated as border.

    Returns:
        Tuple of (cropped image, was_cropped)
    """
    try:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape

        _, mask = cv2.threshold(gray, black_threshold, 255, cv2.THRESH_BINARY)
        coords = cv2.findNonZero(mask)
        if coords is None:
            return img, False

        x, y, cw, ch = cv2.boundingRect(coords)

        top    = y
        bottom = h - (y + ch)
        left   = x
        right  = w - (x + cw)

        min_h = _MIN_BORDER_FRACTION * h
        min_w = _MIN_BORDER_FRACTION * w

        if top <= min_h and bottom <= min_h and left <= min_w and right <= min_w:
            return img, False  # no significant border detected

        # Add padding, clamped to image bounds
        x1 = max(0, x - _CROP_PADDING)
        y1 = max(0, y - _CROP_PADDING)
        x2 = min(w, x + cw + _CROP_PADDING)
        y2 = min(h, y + ch + _CROP_PADDING)

        # Safety: reject if result is too small relative to original
        if (x2 - x1) * (y2 - y1) < _MIN_CROP_AREA_FRACTION * w * h:
            return img, False

        cropped = img[y1:y2, x1:x2]
        logger.info(
            f"[ENHANCEMENT] border crop: {w}x{h} → {x2-x1}x{y2-y1} "
            f"(borders t={top} b={bottom} l={left} r={right})"
        )
        return cropped, True

    except Exception:
        return img, False


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Face-aware orientation correction
# ---------------------------------------------------------------------------
# Uses OpenCV's built-in Haar cascade to detect faces.  Tries all 4
# rotations (0°, 90° CW, 90° CCW, 180°) and picks the one where the
# face detector fires with the largest bounding box — indicating the
# face is upright and fully visible.  This replaces the blind "rotate
# 90° clockwise" heuristic which has a 50/50 chance of being wrong
# when the physical photo is tilted on the surface.

_FACE_CASCADE: Optional[cv2.CascadeClassifier] = None


def _get_face_cascade() -> cv2.CascadeClassifier:
    """Lazy-load the Haar frontal-face cascade (singleton)."""
    global _FACE_CASCADE
    if _FACE_CASCADE is None:
        _FACE_CASCADE = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
    return _FACE_CASCADE


def _orient_by_face_detection(
    img: NDArray[np.uint8],
) -> Tuple[NDArray[np.uint8], Optional[bool]]:
    """
    Try all 4 rotations and pick the one where face detection returns
    the largest face bounding box.

    Returns:
        (oriented_image, result) where result is:
          True  — rotated to correct orientation
          False — already upright (face found at 0°, no rotation needed)
          None  — no face detected in any rotation (caller should fallback)
    """
    cascade = _get_face_cascade()

    # Use higher resolution for detection — passport photos have small faces
    # relative to the full cropped image (face may be ~15-20% of frame).
    max_dim = max(img.shape[:2])
    scale = min(1.0, 1024.0 / max_dim)

    rotations: list[Tuple[Optional[int], str]] = [
        (None, "0°"),
        (cv2.ROTATE_90_CLOCKWISE, "90° CW"),
        (cv2.ROTATE_90_COUNTERCLOCKWISE, "90° CCW"),
        (cv2.ROTATE_180, "180°"),
    ]

    best_rot_code: Optional[int] = None
    best_rot_label: str = "0°"
    best_face_area: float = 0.0
    all_detections: list[Tuple[str, float]] = []

    for rot_code, label in rotations:
        rotated = cv2.rotate(img, rot_code) if rot_code is not None else img
        if scale < 1.0:
            small = cv2.resize(rotated, None, fx=scale, fy=scale)
        else:
            small = rotated
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

        # Use stricter minNeighbors to reduce false positives on textured
        # areas (shirt collars, tie knots, wood grain).
        faces = cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=8, minSize=(50, 50),
        )
        if len(faces) > 0:
            largest = max(faces, key=lambda f: int(f[2]) * int(f[3]))
            area = float(largest[2]) * float(largest[3])
            # Minimum face-to-image ratio: a real face in a passport photo
            # should be at least 3% of the image area.  Smaller detections
            # are likely false positives (buttons, patterns, etc.).
            img_area = float(small.shape[0]) * float(small.shape[1])
            face_ratio = area / max(img_area, 1.0)
            all_detections.append((label, face_ratio))
            if face_ratio >= 0.03 and area > best_face_area:
                best_face_area = area
                best_rot_code = rot_code
                best_rot_label = label

    logger.info(
        "[ENHANCEMENT] face detection results: %s",
        ", ".join(f"{lbl}={ratio:.3f}" for lbl, ratio in all_detections)
        if all_detections else "none",
    )

    if best_face_area > 0 and best_rot_code is not None:
        logger.info(
            "[ENHANCEMENT] face-aware orientation: best rotation = %s "
            "(face_area=%.0f px²)",
            best_rot_label, best_face_area / (scale * scale),
        )
        return cv2.rotate(img, best_rot_code), True

    if best_face_area > 0:
        # Face found at 0° — already correct
        logger.info("[ENHANCEMENT] face-aware orientation: already upright")
        return img, False

    logger.info("[ENHANCEMENT] face-aware orientation: no face detected in any rotation")
    return img, None


# ---------------------------------------------------------------------------
# Face-based crop for portrait photos
# ---------------------------------------------------------------------------
# When contour detection fails to find the passport photo border on a
# surface (low contrast white-on-wood), use face detection to locate the
# subject and derive crop boundaries from standard passport photo
# proportions.
#
# Standard passport photo: 35mm × 45mm (aspect ratio 7:9).
# - Face width ≈ 60-70% of photo width
# - Face is roughly centred horizontally
# - Face top is at ≈ 20-30% from photo top

# How much wider the photo is than the face (each side gets half the excess)
_PORTRAIT_FACE_WIDTH_RATIO = 0.65   # face_width / photo_width
# Vertical padding above face bounding box (fraction of face height)
_PORTRAIT_TOP_PAD_RATIO = 0.45
# Standard passport aspect ratio (width / height)
_PORTRAIT_ASPECT = 35.0 / 45.0  # ≈ 0.778

# Maximum HSV-Value std across the 4 card-corner patches that is still
# considered "uniform background".
# Real card (passport blue / white / grey studio): std ≈ 10–35.
# Cluttered-desk false-positive (corners land on wood, cables, pens): std ≈ 60–130.
# Set conservatively at 45.0: wide margin above worst real-card (35) and
# below best false-positive (60).  Analogous to _FRAME_BORDER_UNIFORMITY_THRESH.
_CARD_BG_UNIFORMITY_THRESHOLD = 45.0

# Size of each corner sampling patch as a fraction of estimated card size.
# 8% of a 140×180 card ≈ 11×14 px patch (~154 px) — enough for stable std
# while staying well clear of the face/hair region.
_CARD_CORNER_PATCH_FRACTION = 0.08

# Minimum face-to-SCENE area ratio inside _find_portrait_card().
# A 4%-of-scene card with 65%-of-card-width face → face ≈ 1.3% of scene.
# 0.5% leaves 2.6× headroom while rejecting sub-pixel noise.
# (Different from _orient_by_face_detection's 3% guard, which operates on
#  an already-isolated crop where the face is large.)
_PORTRAIT_SCENE_MIN_FACE_RATIO = 0.005


def _score_card_background(
    img: NDArray[np.uint8],
    fx: int,
    fy: int,
    fw: int,
    fh: int,
) -> float:
    """
    Measure how much the region around a face candidate looks like a printed
    passport-photo card with a uniform solid-colour backdrop.

    Uses the same passport-proportion constants as _find_portrait_card to
    estimate the card boundary, then samples a small patch at each of the
    4 card corners (which are always inside the backdrop area, never inside
    the face).  Returns the HSV-Value std across all corner patch pixels —
    lower is more uniform (more card-like).

    Returns 999.0 when any corner falls outside the image (the estimated
    card does not fit, so this cannot be an in-scene card).

    Args:
        img:  Full-scene BGR image (full-scale coordinates).
        fx, fy, fw, fh:  Face bounding box in full-scale pixel coordinates.
    """
    h, w = img.shape[:2]

    photo_w = int(fw / _PORTRAIT_FACE_WIDTH_RATIO)
    photo_h = int(photo_w / _PORTRAIT_ASPECT)

    face_cx = fx + fw // 2
    x1 = face_cx - photo_w // 2
    y1 = fy - int(fh * _PORTRAIT_TOP_PAD_RATIO)
    x2 = x1 + photo_w
    y2 = y1 + photo_h

    pw = max(4, int(photo_w * _CARD_CORNER_PATCH_FRACTION))
    ph = max(4, int(photo_h * _CARD_CORNER_PATCH_FRACTION))

    corners = [
        (x1,      y1),
        (x2 - pw, y1),
        (x1,      y2 - ph),
        (x2 - pw, y2 - ph),
    ]

    patches: list[NDArray[np.uint8]] = []
    for cx, cy in corners:
        if cx < 0 or cy < 0 or cx + pw > w or cy + ph > h:
            return 999.0
        patch = img[cy: cy + ph, cx: cx + pw]
        hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
        patches.append(hsv[:, :, 2].ravel())  # Value channel only

    all_v = np.concatenate(patches)
    return float(np.std(all_v))


def _find_portrait_card(
    img: NDArray[np.uint8],
) -> Tuple[NDArray[np.uint8], bool]:
    """
    Locate a printed passport-photo card in a scene image and crop to it.

    Replaces the old "pick largest face" approach with a principled two-gate
    selection:

      Gate 1 — minimum face-to-scene area ratio (0.5%)
        Rejects sub-pixel noise.  Calibrated for faces that are ~1–2% of the
        full scene (a 35×45mm card at ~4% of a typical phone photo).

      Gate 2 — card background uniformity (_score_card_background)
        Estimates where the card boundary would be from passport proportions,
        samples the 4 card corners, and checks that they form a uniform solid
        colour.  A real card has a consistent backdrop colour at every corner;
        a charger, earbuds, or power bank does not.

    The candidate with the LOWEST background std that also beats
    _CARD_BG_UNIFORMITY_THRESHOLD wins.

    Returns:
        (cropped_image, success)  — same signature as original
    """
    h, w = img.shape[:2]
    cascade = _get_face_cascade()

    max_dim = max(h, w)
    scale = min(1.0, 1024.0 / max_dim)

    small = cv2.resize(img, None, fx=scale, fy=scale) if scale < 1.0 else img
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

    # Slightly permissive detection: the background scorer is the real gate.
    # minNeighbors=5 / minSize=(30,30) ensures a small-in-scene face (which
    # generates fewer cascade hits) survives candidate proposal.
    faces = cascade.detectMultiScale(
        gray, scaleFactor=1.05, minNeighbors=5, minSize=(30, 30),
    )

    if len(faces) == 0:
        logger.info("[ENHANCEMENT] face-crop: no face candidates")
        return img, False

    img_area = float(w * h)
    best_score = float("inf")
    best_face: Optional[Tuple[int, int, int, int]] = None

    for (fx_s, fy_s, fw_s, fh_s) in faces:
        fx = int(fx_s / scale)
        fy = int(fy_s / scale)
        fw = int(fw_s / scale)
        fh = int(fh_s / scale)

        # Gate 1: reject sub-pixel noise
        if float(fw * fh) / img_area < _PORTRAIT_SCENE_MIN_FACE_RATIO:
            continue

        # Gate 2: card background uniformity
        score = _score_card_background(img, fx, fy, fw, fh)
        logger.debug(
            "[ENHANCEMENT] face-crop: candidate (%d,%d %dx%d) bg_std=%.1f",
            fx, fy, fw, fh, score,
        )
        if score < best_score:
            best_score = score
            best_face = (fx, fy, fw, fh)

    if best_face is None:
        logger.info("[ENHANCEMENT] face-crop: all candidates below area threshold")
        return img, False

    if best_score >= _CARD_BG_UNIFORMITY_THRESHOLD:
        logger.info(
            "[ENHANCEMENT] face-crop: best bg_std=%.1f >= %.1f — "
            "no card-like background found",
            best_score, _CARD_BG_UNIFORMITY_THRESHOLD,
        )
        return img, False

    fx, fy, fw, fh = best_face
    photo_w = int(fw / _PORTRAIT_FACE_WIDTH_RATIO)
    photo_h = int(photo_w / _PORTRAIT_ASPECT)

    face_cx = fx + fw // 2
    x1 = max(0, face_cx - photo_w // 2)
    y1 = max(0, fy - int(fh * _PORTRAIT_TOP_PAD_RATIO))
    x2 = min(w, x1 + photo_w)
    y2 = min(h, y1 + photo_h)

    crop_w, crop_h = x2 - x1, y2 - y1
    if crop_w < 100 or crop_h < 100:
        logger.info("[ENHANCEMENT] face-crop: crop too small (%dx%d)", crop_w, crop_h)
        return img, False

    if float(crop_w * crop_h) > 0.8 * img_area:
        logger.info("[ENHANCEMENT] face-crop: crop too large (>80%% of image)")
        return img, False

    logger.info(
        "[ENHANCEMENT] face-crop: accepted bg_std=%.1f — %dx%d -> %dx%d "
        "(face at %d,%d %dx%d)",
        best_score, w, h, crop_w, crop_h, fx, fy, fw, fh,
    )
    return img[y1:y2, x1:x2], True


# Backward-compatibility alias
_crop_portrait_by_face = _find_portrait_card


# Already-framed photo detection (skip document-crop guard)
# ---------------------------------------------------------------------------

# Border sampling strip: fraction of each dimension used to sample the edges.
_FRAME_BORDER_STRIP = 0.06  # 6 % on each side

# If the mean standard-deviation across the 4 border strips (in grayscale)
# is below this, the border is "uniform" (solid-colour backdrop / plain BG).
_FRAME_BORDER_UNIFORMITY_THRESH = 28.0

# Minimum ratio of centre-region std-dev to border std-dev.
# A high ratio means "busy centre, quiet border" → already framed.
_FRAME_CENTRE_CONTRAST_RATIO = 1.8

# Maximum Laplacian variance (texture energy) in border strips.
# Smooth studio backdrops have very low texture (~5–80).
# Natural surfaces (wood grain, fabric, marble) have visible texture (~100–500+)
# even when their grayscale intensity std is relatively low.
# This prevents surfaces like wood from being misclassified as "uniform backdrop".
_FRAME_BORDER_MAX_TEXTURE = 90.0

# If ALL three checks pass (uniform intensity + busy centre + smooth border),
# the image looks like a studio/passport photo or a pre-cropped product shot.


def _photo_already_framed(img: NDArray[np.uint8]) -> bool:
    """
    Heuristic: detect whether a photo is already cleanly framed (studio
    portrait, product shot, pre-cropped image) rather than a document
    photographed on a surface.

    Checks:
      1. Border uniformity — the 4 edge strips have low intensity variance,
         indicating a solid-colour or near-uniform background with no
         table/surface clutter.
      2. Centre-vs-border contrast — the centre of the image has
         significantly higher variance than the borders, indicating a
         subject filling the frame.
      3. Border smoothness — the border strips have low texture energy
         (Laplacian variance).  Natural surfaces like wood, fabric, and
         marble can fool check 1 (low grayscale std) but have visible
         grain/texture that produces high Laplacian variance.

    Returns True when ALL THREE conditions hold, meaning
    ``detect_and_crop_document`` should be skipped.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    h, w = gray.shape[:2]

    bh = max(1, int(h * _FRAME_BORDER_STRIP))
    bw = max(1, int(w * _FRAME_BORDER_STRIP))

    # 4 border strips
    top    = gray[:bh, :]
    bottom = gray[h - bh:, :]
    left   = gray[:, :bw]
    right  = gray[:, w - bw:]

    border_stds = [float(np.std(s)) for s in (top, bottom, left, right)]
    mean_border_std = float(np.mean(border_stds))

    # Texture energy: Laplacian variance measures high-frequency detail.
    # Smooth backdrops → low variance; wood grain / fabric → high variance.
    border_textures = [
        float(cv2.Laplacian(s, cv2.CV_64F).var())
        for s in (top, bottom, left, right)
    ]
    mean_border_texture = float(np.mean(border_textures))

    # Centre region (middle 50 %)
    cy0, cy1 = h // 4, 3 * h // 4
    cx0, cx1 = w // 4, 3 * w // 4
    centre = gray[cy0:cy1, cx0:cx1]
    centre_std = float(np.std(centre))

    # Guard: avoid division by zero
    ratio = centre_std / max(mean_border_std, 1.0)

    uniform_border = mean_border_std < _FRAME_BORDER_UNIFORMITY_THRESH
    busy_centre    = ratio > _FRAME_CENTRE_CONTRAST_RATIO
    smooth_border  = mean_border_texture < _FRAME_BORDER_MAX_TEXTURE

    logger.info(
        "[ENHANCEMENT] already-framed check: border_std=%.1f, texture=%.1f, "
        "centre_std=%.1f, ratio=%.2f → uniform=%s, smooth=%s, busy_centre=%s",
        mean_border_std, mean_border_texture, centre_std, ratio,
        uniform_border, smooth_border, busy_centre,
    )

    if uniform_border and busy_centre and smooth_border:
        logger.info(
            "[ENHANCEMENT] photo appears already framed (border_std=%.1f, "
            "texture=%.1f, ratio=%.2f) — skipping document crop",
            mean_border_std, mean_border_texture, ratio,
        )
        return True

    return False


# ---------------------------------------------------------------------------
# Document boundary detection + straighten/crop
# ---------------------------------------------------------------------------

# Document must cover at least this fraction of image area to be detected.
_DOC_DETECT_MIN_AREA_FRACTION = 0.10
# Allow near-full-frame cards so already-cropped tilted docs can be straightened.
_DOC_DETECT_MAX_AREA_FRACTION = 0.999
# Aspect ratio of detected document: longest side / shortest side must be in range.
_DOC_DETECT_MIN_ASPECT_RATIO = 1.12
_DOC_DETECT_MAX_ASPECT_RATIO = 5.0
# Contour must fill at least this fraction of its rotated bounding rect
_DOC_DETECT_MIN_SOLIDITY = 0.60
# Epsilon multiplier for polygon approximation (fraction of arc length)
_POLY_APPROX_EPSILON = 0.02

# ---------------------------------------------------------------------------
# Document taxonomy — drives routing and orientation decisions.
# These mirror the vault categories/subtypes the user selects in the app.
# ---------------------------------------------------------------------------

# Identity card subtypes that are LANDSCAPE (wider than tall).
# Never rotate these to portrait after a successful perspective crop.
_LANDSCAPE_IDENTITY_SUBTYPES: frozenset[str] = frozenset({
    "PAN Card", "Aadhaar Card", "Voter ID", "Driving Licence", "Ration Card",
})

# Photograph subtypes that must come out PORTRAIT (taller than wide).
# Only these trigger a 90° rotate-to-portrait correction after crop.
_PORTRAIT_PHOTO_SUBTYPES: frozenset[str] = frozenset({
    "Passport Photo", "ID Photo", "Profile Photo",
})

# Photograph subtypes that are expected to be LANDSCAPE (wider than tall).
_LANDSCAPE_PHOTO_SUBTYPES: frozenset[str] = frozenset({
    "Postcard Photo",
})

# document_category values that should always use the full document pipeline
# (perspective crop + optional denoising/CLAHE) regardless of document_type.
_DOCUMENT_PIPELINE_CATEGORIES: frozenset[str] = frozenset({
    "identity", "academic", "certificate", "financial", "address", "other",
})


def _order_corners(pts: NDArray[np.float32]) -> NDArray[np.float32]:
    """
    Order 4 corner points as: top-left, top-right, bottom-right, bottom-left.

    This is essential for a correct perspective transform — wrong ordering
    produces hourglass/butterfly warps.

    Algorithm:
      1. Sum (x + y): smallest = top-left, largest = bottom-right
      2. Diff (y - x): smallest = top-right, largest = bottom-left
    """
    rect = np.zeros((4, 2), dtype=np.float32)
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).squeeze()

    rect[0] = pts[np.argmin(s)]   # top-left
    rect[2] = pts[np.argmax(s)]   # bottom-right
    rect[1] = pts[np.argmin(d)]   # top-right
    rect[3] = pts[np.argmax(d)]   # bottom-left

    return rect


def _perspective_crop(
    img: NDArray[np.uint8],
    corners: NDArray[np.float32],
) -> Optional[NDArray[np.uint8]]:
    """
    Apply a 4-corner perspective transform to produce a top-down view.

    Args:
        img: Source BGR image
        corners: Ordered 4 corner points (TL, TR, BR, BL)

    Returns:
        Warped image or None if the result would be degenerate.
    """
    tl, tr, br, bl = corners

    # Compute output dimensions from the max of each edge pair
    width_top = np.linalg.norm(tr - tl)
    width_bot = np.linalg.norm(br - bl)
    out_w = int(max(width_top, width_bot))

    height_left = np.linalg.norm(bl - tl)
    height_right = np.linalg.norm(br - tr)
    out_h = int(max(height_left, height_right))

    if out_w < 50 or out_h < 50:
        return None

    dst = np.array([
        [0, 0],
        [out_w - 1, 0],
        [out_w - 1, out_h - 1],
        [0, out_h - 1],
    ], dtype=np.float32)

    M = cv2.getPerspectiveTransform(corners, dst)
    warped = cv2.warpPerspective(
        img, M, (out_w, out_h),
        flags=cv2.INTER_LANCZOS4,  # higher quality than INTER_LINEAR — preserves sharpness
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )
    return warped


def _find_quad_contour(
    edges: NDArray[np.uint8],
    min_area: float,
    max_area: float,
) -> Optional[Tuple[NDArray[np.float32], float]]:
    """
    Find the best (largest) 4-sided polygon contour in an edge image.

    Walks the largest contours and tries polygon approximation.
    Returns (ordered_4_corner_points, contour_area) or None.
    """
    contours, _ = cv2.findContours(
        edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE,
    )
    contours = sorted(contours, key=cv2.contourArea, reverse=True)

    for cnt in contours[:20]:
        area = cv2.contourArea(cnt)
        if area < min_area or area > max_area:
            continue

        peri = cv2.arcLength(cnt, True)

        # Inner helper: validate and return a 4-corner approximation.
        def _validate_quad(pts4: NDArray[np.float32], quad_area: float):
            ordered = _order_corners(pts4)
            if not cv2.isContourConvex(ordered.astype(np.int32).reshape(-1, 1, 2)):
                return None
            angles_ok = True
            for i in range(4):
                p1 = ordered[i]
                p2 = ordered[(i + 1) % 4]
                p3 = ordered[(i + 2) % 4]
                v1 = p1 - p2
                v2 = p3 - p2
                cos_angle = np.dot(v1, v2) / (
                    np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-6
                )
                angle_deg = np.degrees(np.arccos(np.clip(cos_angle, -1, 1)))
                if angle_deg < 50 or angle_deg > 130:
                    angles_ok = False
                    break
            if not angles_ok:
                return None
            width_top = np.linalg.norm(ordered[1] - ordered[0])
            width_bot = np.linalg.norm(ordered[2] - ordered[3])
            height_left = np.linalg.norm(ordered[3] - ordered[0])
            height_right = np.linalg.norm(ordered[2] - ordered[1])
            est_w = max(width_top, width_bot)
            est_h = max(height_left, height_right)
            short_side = min(est_w, est_h)
            long_side = max(est_w, est_h)
            if short_side < 1:
                return None
            aspect = long_side / short_side
            if aspect < _DOC_DETECT_MIN_ASPECT_RATIO or aspect > _DOC_DETECT_MAX_ASPECT_RATIO:
                return None
            return ordered, quad_area

        # Try multiple epsilon values on the raw contour — tighter first, then looser
        for eps_mult in [0.015, 0.02, 0.03, 0.04, 0.05]:
            approx = cv2.approxPolyDP(cnt, eps_mult * peri, True)
            if len(approx) == 4:
                result = _validate_quad(approx.reshape(4, 2).astype(np.float32), area)
                if result is not None:
                    return result

        # Rounded-corner fallback: approximate the CONVEX HULL instead.
        # For cards like PAN / Aadhaar whose rounded corners mean
        # approxPolyDP on the raw contour never yields exactly 4 corners,
        # the convex hull (already corner-free) approximates cleanly to 4 pts.
        hull = cv2.convexHull(cnt)
        hull_peri = cv2.arcLength(hull, True)
        for eps_mult in [0.01, 0.015, 0.02, 0.03, 0.04, 0.05]:
            approx = cv2.approxPolyDP(hull, eps_mult * hull_peri, True)
            if len(approx) == 4:
                result = _validate_quad(approx.reshape(4, 2).astype(np.float32), area)
                if result is not None:
                    return result

    return None


def _fallback_perspective_crop(
    img: NDArray[np.uint8],
    min_area: float,
    max_area: float,
    edges: NDArray[np.uint8],
) -> Tuple[NDArray[np.uint8], bool]:
    """
    Fallback: use minAreaRect corners + perspective transform when
    4-corner polygon detection (approxPolyDP) fails.

    Instead of rotating the whole image by the minAreaRect angle (which has
    confusing sign conventions that vary across OpenCV versions), extract the
    4 corner points via boxPoints() and apply a perspective warp — identical
    to the Stage-1 path.  This guarantees a perfectly axis-aligned output.
    """
    h, w = img.shape[:2]

    contours, _ = cv2.findContours(
        edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE,
    )
    contours = sorted(contours, key=cv2.contourArea, reverse=True)

    for cnt in contours[:15]:
        area = cv2.contourArea(cnt)
        if area < min_area or area > max_area:
            continue

        rect = cv2.minAreaRect(cnt)
        (_cx, _cy), (rw, rh), _angle = rect

        rect_area = rw * rh
        if rect_area <= 0 or area / rect_area < _DOC_DETECT_MIN_SOLIDITY:
            continue

        long_side = max(rw, rh)
        short_side = min(rw, rh)
        if short_side < 1:
            continue
        aspect = long_side / short_side
        if aspect < _DOC_DETECT_MIN_ASPECT_RATIO or aspect > _DOC_DETECT_MAX_ASPECT_RATIO:
            continue

        # Get the 4 corners of the minimum area rectangle and use
        # perspective transform — no angle sign headaches.
        box = cv2.boxPoints(rect).astype(np.float32)
        corners = _order_corners(box)

        warped = _perspective_crop(img, corners)
        if warped is None or warped.size == 0:
            continue

        out_h, out_w = warped.shape[:2]
        logger.info(
            "[ENHANCEMENT] document fallback perspective crop: "
            f"{w}x{h} -> {out_w}x{out_h}"
        )
        return warped, True

    return img, False


def _find_filled_document_blob(
    img: NDArray[np.uint8],
    min_area: float,
    max_area: float,
) -> Tuple[NDArray[np.uint8], bool]:
    """
    Detect a document card using binary brightness threshold → filled blob.

    Unlike edge-based detection, this approach is robust to:
    - Rounded corners (no edge connectivity required — the card is a solid blob)
    - Holographic / textured card surfaces creating spurious internal edges
    - Cards whose boundary approxPolyDP never yields exactly 4 corners

    Works best when the card luminance clearly differs from the background.
    Three threshold strategies are tried in order:
      A) Bright-value mask       — HIGH Value channel (V>180): captures bright
                                   white paper which has very high brightness.
                                   Most reliable for letter/A4 on any background.
      B) Otsu on blurred gray    — adapts to any contrast level
      C) Inverted Otsu           — handles dark card on light background
      D) Fixed thresholds        — dark-background and mid-tone scenes
      E) Saturation strategies   — colorful cards + white paper on wood

    Returns (warped_img, True) on success, (img, False) on failure.
    """
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (9, 9), 0)

    # Strategy A: High-brightness mask — white paper (V > 180) on any background.
    # This is the most reliable candidate for letter/A4 documents because white
    # paper has Value close to 255 while wood / fabric are noticeably darker.
    # Placed FIRST so it is evaluated before all Otsu/fixed-threshold variants.
    hsv_a = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    val = hsv_a[:, :, 2]
    _, bright_mask = cv2.threshold(val, 180, 255, cv2.THRESH_BINARY)
    bright_blur = cv2.GaussianBlur(bright_mask, (9, 9), 0)
    _, bright_clean = cv2.threshold(bright_blur, 127, 255, cv2.THRESH_BINARY)

    _, otsu_thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    _, inv_thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    # Multiple fixed thresholds to cover dark-background, mid-tone, and light-background scenes.
    binary_candidates = [bright_clean, otsu_thresh, inv_thresh]
    for _tval in [40, 60, 90, 120, 150, 180]:
        _, _t = cv2.threshold(blur, _tval, 255, cv2.THRESH_BINARY)
        binary_candidates.append(_t)

    # HSV saturation strategies:
    # (A) High-saturation foreground: colorful cards (PAN, Aadhaar, Voter ID) are far
    #     more saturated than most table surfaces — pixels with HIGH saturation are the card.
    # (B) Low-saturation foreground: white/grey documents (letters, certificates) have
    #     VERY LOW saturation compared to a wooden/fabric table background — inverse Otsu
    #     finds the desaturated (white paper) blob.
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1]
    sat_blur = cv2.GaussianBlur(sat, (9, 9), 0)
    _, sat_otsu = cv2.threshold(sat_blur, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    binary_candidates.append(sat_otsu)  # (A) colorful card on neutral background
    _, sat_inv_otsu = cv2.threshold(sat_blur, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    binary_candidates.append(sat_inv_otsu)  # (B) white/grey paper on coloured background

    # Adaptive kernel: scale the fill kernel relative to image size so it can
    # bridge the face-photo hole (~10-15 % of card width) on PAN cards.
    fill_size = max(15, min(w, h) // 20)  # ~5 % of the shorter dimension
    fill_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (fill_size, fill_size))
    open_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))

    best_warped: Optional[NDArray[np.uint8]] = None
    best_size: int = 0

    for binary in binary_candidates:
        # Fill internal holes (text, QR code cutouts) and denoise small blobs
        closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, fill_kernel)
        cleaned = cv2.morphologyEx(closed, cv2.MORPH_OPEN, open_kernel)

        # RETR_EXTERNAL: only outermost blobs — avoids internal card elements
        contours, _ = cv2.findContours(
            cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE,
        )
        contours = sorted(contours, key=cv2.contourArea, reverse=True)

        for cnt in contours[:5]:
            raw_area = cv2.contourArea(cnt)
            if raw_area < min_area * 0.5:  # pre-filter: hull will be larger
                continue

            # Use the CONVEX HULL to bridge internal holes (face photo, holo strip).
            # For a PAN card the raw contour can have significant holes that reduce
            # solidity; the hull gives a clean outer boundary.
            hull = cv2.convexHull(cnt)
            area = cv2.contourArea(hull)
            if area < min_area or area > max_area:
                continue

            rect = cv2.minAreaRect(hull)
            (_cx, _cy), (rw, rh), _angle = rect

            rect_area = rw * rh
            if rect_area <= 0:
                continue
            # Solidity check on hull vs bounding rect (hull is already convex so
            # the threshold can be a bit lower than for raw contours).
            if area / rect_area < 0.50:
                continue

            long_side = max(rw, rh)
            short_side = min(rw, rh)
            if short_side < 1:
                continue
            aspect = long_side / short_side
            if aspect < _DOC_DETECT_MIN_ASPECT_RATIO or aspect > _DOC_DETECT_MAX_ASPECT_RATIO:
                continue

            box = cv2.boxPoints(rect).astype(np.float32)
            corners = _order_corners(box)
            warped = _perspective_crop(img, corners)
            if warped is None or warped.size == 0:
                continue

            size = warped.shape[0] * warped.shape[1]
            if size > best_size:
                best_warped = warped
                best_size = size

    if best_warped is not None:
        out_h, out_w = best_warped.shape[:2]
        logger.info(
            f"[ENHANCEMENT] document filled-blob perspective crop: "
            f"{w}x{h} → {out_w}x{out_h}"
        )
        return best_warped, True

    return img, False


def _preprocess_for_edges(
    gray: NDArray[np.uint8],
    bgr: Optional[NDArray[np.uint8]] = None,
) -> list[NDArray[np.uint8]]:
    """
    Generate multiple edge maps using different preprocessing strategies
    to handle varied backgrounds (wood, fabric, table, white surface, etc.).

    When `bgr` is provided, also generates color-aware edge maps (saturation,
    LAB) which are crucial for detecting colored documents (PAN cards, voter
    IDs, mark sheets) on white/light backgrounds where grayscale contrast
    is near zero.

    Returns a list of edge images to try in order.
    """
    edge_maps: list[NDArray[np.uint8]] = []
    close_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))

    # ---- Strategy 1: Bilateral filter (edge-preserving) + Canny ----------
    bilateral = cv2.bilateralFilter(gray, d=11, sigmaColor=80, sigmaSpace=80)
    for lo, hi in [(30, 100), (50, 150), (20, 80)]:
        e = cv2.Canny(bilateral, lo, hi)
        e = cv2.morphologyEx(e, cv2.MORPH_CLOSE, close_kernel)
        edge_maps.append(e)

    # ---- Strategy 2: Adaptive threshold → edges -------------------------
    adaptive = cv2.adaptiveThreshold(
        bilateral, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        blockSize=15,
        C=5,
    )
    adaptive = cv2.morphologyEx(adaptive, cv2.MORPH_CLOSE, close_kernel)
    dilate_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    adaptive = cv2.dilate(adaptive, dilate_kernel, iterations=2)
    adaptive = cv2.erode(adaptive, dilate_kernel, iterations=1)
    edge_maps.append(adaptive)

    # ---- Strategy 3: Heavy Gaussian + wider Canny thresholds -------------
    heavy_blur = cv2.GaussianBlur(gray, (15, 15), 0)
    for lo, hi in [(25, 90), (40, 120)]:
        e = cv2.Canny(heavy_blur, lo, hi)
        e = cv2.morphologyEx(e, cv2.MORPH_CLOSE, close_kernel)
        edge_maps.append(e)

    # ---- Strategy 4: Color-aware (saturation channel) --------------------
    # PAN cards, voter IDs, etc. are colorful documents.  On a white/grey
    # background the grayscale contrast is near zero, but the SATURATION
    # channel cleanly separates the colored card from the desaturated bg.
    if bgr is not None:
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        sat = hsv[:, :, 1]  # saturation channel

        # 4a: Otsu threshold on saturation — card = saturated, bg = not
        sat_blur = cv2.GaussianBlur(sat, (7, 7), 0)
        _, sat_thresh = cv2.threshold(sat_blur, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        # Heavy morphological close to fill internal gaps and get outer hull
        big_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 25))
        sat_thresh = cv2.morphologyEx(sat_thresh, cv2.MORPH_CLOSE, big_kernel)
        sat_thresh = cv2.morphologyEx(sat_thresh, cv2.MORPH_OPEN, close_kernel)
        edge_maps.append(sat_thresh)

        # 4b: Canny on saturation — useful when Otsu doesn't separate cleanly
        sat_bilateral = cv2.bilateralFilter(sat, d=9, sigmaColor=75, sigmaSpace=75)
        for lo, hi in [(20, 80), (30, 100)]:
            e = cv2.Canny(sat_bilateral, lo, hi)
            e = cv2.morphologyEx(e, cv2.MORPH_CLOSE, close_kernel)
            edge_maps.append(e)

        # ---- Strategy 5: LAB color space (a-channel) ---------------------
        # The 'a' channel in LAB separates green-red axis — many ID cards
        # have pink/red tones that stand out here.
        lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
        a_ch = lab[:, :, 1]
        a_blur = cv2.GaussianBlur(a_ch, (7, 7), 0)
        for lo, hi in [(15, 60), (25, 80)]:
            e = cv2.Canny(a_blur, lo, hi)
            e = cv2.morphologyEx(e, cv2.MORPH_CLOSE, close_kernel)
            edge_maps.append(e)

        # ---- Strategy 6: Morphological gradient on blurred gray ----------
        # Catches subtle edges missed by Canny — good for low-contrast scenes
        morph_blur = cv2.GaussianBlur(gray, (11, 11), 0)
        grad_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        gradient = cv2.morphologyEx(morph_blur, cv2.MORPH_GRADIENT, grad_kernel)
        _, grad_thresh = cv2.threshold(gradient, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        grad_thresh = cv2.morphologyEx(grad_thresh, cv2.MORPH_CLOSE, close_kernel)
        edge_maps.append(grad_thresh)

    return edge_maps


def _hough_fine_tune_rotation(
    img: NDArray[np.uint8],
    max_correction: float = 15.0,
) -> NDArray[np.uint8]:
    """
    Fine-tune the rotation of an already-cropped document using Hough lines.

    After perspective or affine cropping, there may be a small residual tilt
    (1-15 degrees) from imprecise contour detection.  This function detects
    the dominant near-horizontal line angle via HoughLinesP and corrects it.

    Only corrects angles in (-max_correction, +max_correction).  Larger angles
    likely indicate a badly cropped image and should not be "fixed" here.

    Args:
        img:  Already-cropped BGR image.
        max_correction:  Maximum angle (degrees) to correct.

    Returns:
        Rotation-corrected image (or the original if no correction needed).
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = img.shape[:2]

    # Use Canny on a lightly blurred image to pick up text baselines / edges
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)

    # Hough transform — look for long, near-horizontal lines
    min_line_len = max(30, w // 8)
    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180,
        threshold=80,
        minLineLength=min_line_len,
        maxLineGap=10,
    )

    if lines is None or len(lines) < 3:
        return img

    # Collect angles of lines that are roughly horizontal (within ±max_correction)
    angles: list[float] = []
    for line in lines:
        x1, y1, x2, y2 = line[0]
        dx = x2 - x1
        dy = y2 - y1
        if abs(dx) < 1:
            continue  # skip vertical lines
        angle_deg = math.degrees(math.atan2(dy, dx))
        if abs(angle_deg) <= max_correction:
            angles.append(angle_deg)

    if len(angles) < 3:
        return img

    # Robust angle estimation: use the median (resistant to outliers)
    median_angle = float(np.median(angles))

    # Skip if the correction is negligible (< 0.3 degree)
    if abs(median_angle) < 0.3:
        return img

    logger.info(
        f"[ENHANCEMENT] Hough fine-tune rotation: {median_angle:.2f}° "
        f"(from {len(angles)} lines)"
    )

    center = (w / 2.0, h / 2.0)
    M = cv2.getRotationMatrix2D(center, median_angle, 1.0)
    cos_a = abs(M[0, 0])
    sin_a = abs(M[0, 1])
    new_w = int(round(h * sin_a + w * cos_a))
    new_h = int(round(h * cos_a + w * sin_a))
    M[0, 2] += (new_w - w) / 2.0
    M[1, 2] += (new_h - h) / 2.0

    rotated = cv2.warpAffine(
        img, M, (new_w, new_h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )

    # Tight-crop: remove the white border added by the rotation
    rotated = _trim_white_border(rotated)

    return rotated


def _trim_white_border(img: NDArray[np.uint8], threshold: int = 245) -> NDArray[np.uint8]:
    """
    Remove nearly-white borders from an image. Useful after rotation
    introduces white fill around the document.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # Pixels darker than threshold are "content"
    mask = gray < threshold
    coords = np.argwhere(mask)
    if coords.size == 0:
        return img
    y0, x0 = coords.min(axis=0)
    y1, x1 = coords.max(axis=0) + 1
    cropped = img[y0:y1, x0:x1]
    if cropped.size == 0:
        return img
    return cropped


def detect_and_crop_document(
    img: NDArray[np.uint8],
    raw_data: Optional[bytes] = None,
) -> Tuple[NDArray[np.uint8], bool]:
    """
    Detect the largest valid document rectangle in a scene photo, correct
    perspective, and crop to produce a clean top-down view.

    Three-stage approach:
      Stage 1 — 4-corner perspective transform (preferred):
        Polygon approximation → corner ordering → perspective warp.

      Stage 2 — minAreaRect perspective fallback:
        Uses minAreaRect → boxPoints → perspective warp.  Always produces
        axis-aligned output without angle-sign confusion.

      Stage 3 — Hough fine-tune:
        After any successful crop, detect dominant near-horizontal text
        baselines via HoughLinesP and correct residual tilt (±15°).

    Returns:
        (result_image, was_processed)
    """
    h, w = img.shape[:2]
    min_area = _DOC_DETECT_MIN_AREA_FRACTION * w * h
    max_area = _DOC_DETECT_MAX_AREA_FRACTION * w * h

    cropped: Optional[NDArray[np.uint8]] = None

    # ── Stage 0: Vision API crop hints (ML-based, preferred) ──────────────
    # Sends the EXIF-corrected image to Vision API, which uses a trained
    # model to locate the primary subject (the document).  If it returns a
    # confident 4-corner polygon we use it directly and skip the OpenCV
    # cascade below.
    if raw_data is not None:
        try:
            from processors.vision_crop import get_crop_corners
            vision_corners = get_crop_corners(raw_data)
            if vision_corners is not None:
                ordered = _order_corners(vision_corners)
                warped = _perspective_crop(img, ordered)
                if warped is not None and warped.size > 0:
                    out_h, out_w = warped.shape[:2]
                    warped_area = out_h * out_w
                    original_area = h * w
                    area_ratio = warped_area / max(original_area, 1)
                    if area_ratio < _DOC_DETECT_MIN_AREA_FRACTION:
                        logger.warning(
                            "[ENHANCEMENT] Vision API crop too small "
                            "(%.1f%% of original, min %.0f%%) — rejecting, "
                            "falling through to OpenCV",
                            area_ratio * 100,
                            _DOC_DETECT_MIN_AREA_FRACTION * 100,
                        )
                    else:
                        logger.info(
                            "[ENHANCEMENT] Vision API perspective crop: %dx%d -> %dx%d",
                            w, h, out_w, out_h,
                        )
                        return _hough_fine_tune_rotation(warped), True
        except Exception as _ve:
            logger.warning(
                "[ENHANCEMENT] Vision Stage 0 failed, continuing to OpenCV: %s", _ve
            )

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edge_maps = _preprocess_for_edges(gray, bgr=img)

    # ── Stage 1: 4-corner perspective transform ───────────────────────────
    # Scan ALL edge maps and pick the LARGEST valid quad.  This prevents
    # internal card elements (QR codes, photos) from being mistakenly
    # selected when the first edge map happens to detect them.
    best_corners: Optional[NDArray[np.float32]] = None
    best_quad_area: float = 0.0

    for edge_img in edge_maps:
        result = _find_quad_contour(edge_img, min_area, max_area)
        if result is not None:
            corners, quad_area = result
            if quad_area > best_quad_area:
                best_corners = corners
                best_quad_area = quad_area

    if best_corners is not None:
        warped = _perspective_crop(img, best_corners)
        if warped is not None and warped.size > 0:
            out_h, out_w = warped.shape[:2]
            logger.info(
                "[ENHANCEMENT] document perspective-corrected: "
                f"{w}x{h} -> {out_w}x{out_h} "
                f"(quad_area={best_quad_area:.0f}/{w*h}={best_quad_area/(w*h):.1%})"
            )
            cropped = warped

    # ── Stage 2: Filled-blob detection (primary fallback) ─────────────────
    # Treats the document as a bright filled region rather than an edge ring.
    # This is robust to rounded corners (PAN cards, Aadhaar) and holographic
    # surfaces that produce noisy internal edges which break Stage 1's polygon
    # approximation.  Three binary-threshold strategies are tried in order.
    if cropped is None:
        cropped_blob, blob_found = _find_filled_document_blob(img, min_area, max_area)
        if blob_found:
            cropped = cropped_blob

    # ── Stage 3: minAreaRect on edge contours (secondary fallback) ─────────
    # Legacy fallback kept for documents on light/complex backgrounds where
    # brightness thresholding cannot isolate the document cleanly.
    if cropped is None:
        best_fallback: Optional[NDArray[np.uint8]] = None
        best_fb_size: int = 0

        all_edges = edge_maps if edge_maps else [
            cv2.Canny(cv2.GaussianBlur(gray, (9, 9), 0), 30, 100)
        ]
        for edge_img in all_edges:
            result, found = _fallback_perspective_crop(
                img, min_area, max_area, edge_img,
            )
            if found:
                fb_size = result.shape[0] * result.shape[1]
                if fb_size > best_fb_size:
                    best_fallback = result
                    best_fb_size = fb_size

        if best_fallback is not None:
            cropped = best_fallback

    if cropped is None:
        return img, False

    # ── Stage 3: Hough fine-tune rotation ─────────────────────────────────
    cropped = _hough_fine_tune_rotation(cropped)

    return cropped, True


# ---------------------------------------------------------------------------
# Type-specific enhancement branches
# ---------------------------------------------------------------------------

def _enhance_photo(
    img: NDArray[np.uint8],
    raw_data: bytes,
    breakdown: Optional[QualityBreakdown],
    options: Optional["EnhancementOptions"] = None,
) -> Tuple[NDArray[np.uint8], bool, bool, bool, bool]:
    """
    Photo enhancement pipeline.

    Operations (each conditional on measured need):
      1. EXIF rotation     — always attempted
      2. Border crop       — dark scanner borders removed if detected
      3. Gamma correction  — if mean brightness outside 80–200
      4. Unsharp mask      — if normalized sharpness < 0.20

    NO NLM denoising. NO CLAHE. NO Hough skew detection.

    Returns:
        (img, orientation_corrected, exposure_corrected, sharpened, border_cropped)
    """
    orientation_corrected = False
    exposure_corrected = False
    sharpened = False
    border_cropped = False

    # 1. EXIF rotation (handles most phone camera photos)
    img, orientation_corrected = correct_orientation_exif(img, raw_data)

    # 2. Crop: extract the photo from the background.
    #
    #    Portrait subtypes (Passport Photo, ID Photo, etc.):
    #       Always use face-based crop — the face is the most reliable anchor
    #       regardless of whether the photo is on a surface or already framed.
    #       Re-cropping an already-correct passport photo to passport proportions
    #       is a near-no-op (the face is already centred at those proportions).
    #       This avoids the framing-guard threshold game entirely.
    #
    #    Non-portrait photo types:
    #       Use framing guard → document-boundary detection (contour-based).
    _subtype = options.document_subtype if options else None
    _expects_portrait = (
        _subtype in _PORTRAIT_PHOTO_SUBTYPES
        if _subtype is not None
        else True   # default: assume portrait for untagged photo uploads
    )

    crop_done = False

    if _expects_portrait:
        # Face-based crop: works for both photo-on-surface and already-framed
        img_face, face_found = _crop_portrait_by_face(img)
        if face_found:
            img = img_face
            border_cropped = True
            crop_done = True
            # Orientation check for edge cases
            img, face_result = _orient_by_face_detection(img)
            if face_result is True:
                orientation_corrected = True

    if not crop_done:
        # Non-portrait path: framing guard + contour-based detection
        already_framed = _photo_already_framed(img)
        if already_framed:
            img, border_cropped = crop_borders(img)
        else:
            img, doc_found = detect_and_crop_document(img, raw_data=raw_data)
            if doc_found:
                border_cropped = True
                if _expects_portrait:
                    img, face_result = _orient_by_face_detection(img)
                    if face_result is True:
                        orientation_corrected = True
                    elif face_result is False:
                        pass  # already upright
                    elif img.shape[1] > img.shape[0]:
                        img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
                        orientation_corrected = True
                        logger.info("[ENHANCEMENT] photo: landscape→portrait fallback (no face)")
            else:
                img, border_cropped = crop_borders(img)
                # Fallback rotation: if EXIF gave nothing, try Hough-based detection
                if not orientation_corrected:
                    rotation = detect_large_rotation(img)
                    if rotation is not None:
                        img = apply_large_rotation(img, rotation)
                        orientation_corrected = True
                        logger.info(f"[ENHANCEMENT] photo fallback rotation: {rotation}°")

    # 3. Exposure — compute mean brightness on processed image
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    mean_brightness = float(np.mean(gray))

    if mean_brightness < _PHOTO_BRIGHTNESS_MIN or mean_brightness > _PHOTO_BRIGHTNESS_MAX:
        gamma = _compute_gamma_for_brightness(mean_brightness)
        img = gamma_correct(img, gamma)
        logger.info(
            f"[ENHANCEMENT] photo gamma correction: brightness={mean_brightness:.1f}, γ={gamma:.2f}"
        )
        exposure_corrected = True

    # 3. Sharpness — use breakdown if available, otherwise compute inline
    if breakdown is not None:
        sharp_score = breakdown.sharpness
    else:
        from processors.quality import compute_sharpness
        gray2 = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        sharp_score = compute_sharpness(gray2)

    if sharp_score < _PHOTO_SHARPNESS_THRESHOLD:
        img = apply_unsharp_mask(img)
        logger.info(f"[ENHANCEMENT] photo unsharp mask: sharpness_score={sharp_score:.3f}")
        sharpened = True

    return img, orientation_corrected, exposure_corrected, sharpened, border_cropped


def _enhance_signature(
    img: NDArray[np.uint8],
    raw_data: bytes,
    breakdown: Optional[QualityBreakdown],
) -> Tuple[NDArray[np.uint8], bool, bool, bool, bool]:
    """
    Signature enhancement pipeline.

    Operations:
      1. EXIF rotation
      2. Border crop       — scanner borders removed if detected
      3. Sharpness check  → unsharp mask if needed
      4. Otsu binarization (always — produces clean black-on-white output)

    Returns:
        (img, orientation_corrected, binarized, sharpened, border_cropped)
    """
    orientation_corrected = False
    binarized = False
    sharpened = False
    border_cropped = False

    # 1. EXIF rotation
    img, orientation_corrected = correct_orientation_exif(img, raw_data)

    # 2. Border crop (scanner black borders)
    img, border_cropped = crop_borders(img)

    # 3. Sharpness check
    if breakdown is not None:
        sharp_score = breakdown.sharpness
    else:
        from processors.quality import compute_sharpness
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        sharp_score = compute_sharpness(gray)

    if sharp_score < _PHOTO_SHARPNESS_THRESHOLD:
        img = apply_unsharp_mask(img, sigma=1.0, strength=1.2)
        logger.info(f"[ENHANCEMENT] signature unsharp mask: sharpness_score={sharp_score:.3f}")
        sharpened = True

    # 3. Otsu binarization (always for signatures)
    img, binarized = otsu_binarize(img)
    if binarized:
        logger.info("[ENHANCEMENT] signature Otsu binarization applied")

    return img, orientation_corrected, binarized, sharpened, border_cropped


def _enhance_document(
    img: NDArray[np.uint8],
    raw_data: bytes,
    options: EnhancementOptions,
) -> Tuple[NDArray[np.uint8], bool, bool, bool, bool]:
    """
    Document enhancement pipeline.

    Operations:
      1. EXIF auto-rotate  — corrects phone camera orientation via EXIF
      2. Border crop       — scanner borders removed if detected
      3. Orientation correction (Hough skew + large-rotation detection)
      4. NLM denoising     — gated by GUARD-001
      5. White balance + CLAHE — gated by GUARD-001

    Returns:
        (img, orientation_corrected, denoised, color_normalized, border_cropped)
    """
    skip_enhancement = should_skip_enhancement(options)
    if skip_enhancement:
        logger.info("[ENHANCEMENT] skipped (readable document)")

    border_cropped = False
    denoised = False
    color_normalized = False

    # Step 1: EXIF auto-rotate (phone camera uploads).
    # raw_data already went through _apply_exif_transpose in enhance_image,
    # so this is a no-op for phone photos.  Kept here as a guardrail for
    # callers that bypass enhance_image and call _enhance_document directly.
    img, orientation_corrected = correct_orientation_exif(img, raw_data)

    # Step 2: Document boundary detection → perspective warp → crop.
    # Tries Vision API first, then cascades through OpenCV detectors.
    # Passes raw_data so the Vision stage can include the image bytes.
    img, doc_found = detect_and_crop_document(img, raw_data=raw_data)
    if doc_found:
        border_cropped = True
        orientation_corrected = True
    else:
        img, border_cropped = crop_borders(img)
        if options.correct_orientation:
            img, orientation_corrected = correct_orientation(img)

    if options.denoise and not skip_enhancement:
        img, denoised = denoise(img, strength=options.denoise_strength)

    if options.normalize_color and not skip_enhancement:
        img, _ = auto_white_balance(img)
        img, color_normalized = normalize_color(
            img,
            clip_limit=options.clahe_clip_limit,
            grid_size=options.clahe_grid_size,
        )

    # WP-7: Sauvola binarisation — only when caller requests binary output AND
    # CLAHE actually ran (skip_enhancement=False).  Sauvola on a CLAHE-normalised
    # image produces cleaner results than on a raw photo with ambient gradients.
    # When GUARD-001 skips enhancement, Stage 5 convert_colour_mode handles this.
    if options.binarise_output and not skip_enhancement:
        from processors.schema import _sauvola_threshold
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        mask = _sauvola_threshold(gray)
        black_on_white = cv2.bitwise_not(mask)
        img = cv2.cvtColor(black_on_white, cv2.COLOR_GRAY2BGR)
        color_normalized = True
        logger.info("[ENHANCEMENT] document Sauvola binarisation applied (WP-7)")

    return img, orientation_corrected, denoised, color_normalized, border_cropped


def should_skip_enhancement(options: EnhancementOptions) -> bool:
    """
    GUARD-001: Determine if enhancement should be skipped.
    
    Skip denoise and CLAHE for readable images with quality > 0.75.
    
    Args:
        options: Enhancement options with quality_score and is_readable
        
    Returns:
        True if enhancement should be skipped
    """
    if options.quality_score is None:
        return False
    
    if options.quality_score > READABLE_QUALITY_THRESHOLD and options.is_readable:
        return True
    
    return False


def enhance_image(
    data: bytes,
    options: Optional[EnhancementOptions] = None,
) -> EnhancementResult:
    """
    Route to the correct enhancement branch based on document_type, refined by
    document_category and document_subtype where available.

    Routing rules (in priority order):
    1. category="signature" or document_type="signature" → signature pipeline
    2. category in _DOCUMENT_PIPELINE_CATEGORIES (e.g. "identity", "academic")
       → document pipeline regardless of document_type value.
       This ensures identity cards (PAN, Aadhaar, Voter ID …) get perspective
       correction even when the app sends document_type="photo".
    3. document_type="photo" → photo pipeline
    4. default → document pipeline

    - photo     → EXIF rotation, perspective crop, gamma correction, unsharp mask
    - signature → EXIF rotation, unsharp mask, Otsu binarization
    - document  → perspective crop, NLM denoising, CLAHE (GUARD-001 gated)

    Args:
        data: Raw image bytes
        options: Enhancement configuration (uses defaults if None)

    Returns:
        EnhancementResult with processed image and operation flags

    Raises:
        WorkerError: If enhancement fails completely
    """
    if options is None:
        options = EnhancementOptions()

    try:
        # EXIF auto-rotate: correct phone camera orientation before any pipeline
        # routing.  This ensures Vision API, OpenCV contour detection, and all
        # colour corrections see a properly uprighted image.
        # After this call, all downstream EXIF reads return angle=0 (no-op).
        data = _apply_exif_transpose(data)

        img = decode_image(data)

        # ── Category-based routing override ───────────────────────────────
        # document_category carries the user's explicit intent (from vault
        # taxonomy) and is more precise than the coarse 3-value document_type.
        _category = (options.document_category or "").lower()
        _subtype  = options.document_subtype or ""

        if _category == "signature" or options.document_type == "signature":
            doc_type = "signature"
        elif _category in _DOCUMENT_PIPELINE_CATEGORIES:
            # e.g. identity, academic, certificate, financial → full document
            # pipeline with perspective correction
            doc_type = "document"
        else:
            doc_type = options.document_type  # honour explicit value

        if doc_type == "photo":
            img, orientation_corrected, exposure_corrected, sharpened, border_cropped = (
                _enhance_photo(img, data, options.quality_breakdown, options)
            )
            result_data = encode_image(img, format="jpeg", quality=97)
            return EnhancementResult(
                image_data=result_data,
                orientation_corrected=orientation_corrected,
                denoised=sharpened,            # repurposed: True = unsharp mask applied
                color_normalized=exposure_corrected,
                border_cropped=border_cropped,
            )

        elif doc_type == "signature":
            img, orientation_corrected, binarized, sharpened, border_cropped = (
                _enhance_signature(img, data, options.quality_breakdown)
            )
            result_data = encode_image(img, format="jpeg", quality=97)
            return EnhancementResult(
                image_data=result_data,
                orientation_corrected=orientation_corrected,
                denoised=sharpened,            # repurposed: True = unsharp mask applied
                color_normalized=binarized,    # repurposed: True = Otsu binarization applied
                border_cropped=border_cropped,
            )

        else:  # document
            img, orientation_corrected, denoised, color_normalized, border_cropped = (
                _enhance_document(img, data, options)
            )
            result_data = encode_image(img, format="jpeg", quality=97)
            return EnhancementResult(
                image_data=result_data,
                orientation_corrected=orientation_corrected,
                denoised=denoised,
                color_normalized=color_normalized,
                border_cropped=border_cropped,
            )

    except WorkerError:
        raise
    except Exception as e:
        raise WorkerError(
            code=ErrorCode.ENHANCE_FAILED,
            stage=ProcessingStage.ENHANCE,
            message=f"Enhancement failed: {str(e)}",
            details={"exception_type": type(e).__name__},
        )


def enhance_image_minimal(data: bytes) -> EnhancementResult:
    """
    Apply minimal enhancement (orientation only).
    
    Use this for images that already have good quality.
    """
    return enhance_image(data, EnhancementOptions(
        correct_orientation=True,
        denoise=False,
        normalize_color=False,
    ))


__all__ = [
    'enhance_image',
    'enhance_image_minimal',
    'EnhancementOptions',
    'EnhancementResult',
    # Document branch
    'correct_orientation',
    'denoise',
    'normalize_color',
    'auto_white_balance',
    'detect_large_rotation',
    'apply_large_rotation',
    'should_skip_enhancement',
    'READABLE_QUALITY_THRESHOLD',
    # Photo / signature branch
    'get_exif_rotation_angle',
    'correct_orientation_exif',
    'gamma_correct',
    'apply_unsharp_mask',
    'bilateral_denoise',
    'otsu_binarize',
    'crop_borders',
    # Document boundary detection + straighten
    'detect_and_crop_document',
    '_order_corners',
    '_perspective_crop',
    '_find_quad_contour',
    '_fallback_perspective_crop',
    '_hough_fine_tune_rotation',
    '_trim_white_border',
]
