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
from PIL import Image

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
    # Full quality breakdown — used by photo/signature branches for per-metric decisions
    quality_breakdown: Optional[QualityBreakdown] = None


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
    
    # Detect edges
    edges = cv2.Canny(gray, 50, 150)
    
    # Use Hough transform to detect lines
    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180,
        threshold=100,
        minLineLength=50,
        maxLineGap=10,
    )
    
    if lines is None or len(lines) < 5:
        # Not enough lines to determine orientation
        return img, False
    
    # Calculate angles of all lines
    angles = []
    for line in lines:
        x1, y1, x2, y2 = line[0]
        if x2 != x1:
            angle = np.arctan2(y2 - y1, x2 - x1) * 180 / np.pi
            angles.append(angle)
    
    if not angles:
        return img, False
    
    # Find the dominant angle
    angles = np.array(angles)
    
    # Normalize angles to [-90, 90]
    angles = np.mod(angles + 90, 180) - 90
    
    # Compute histogram of angles
    hist, bin_edges = np.histogram(angles, bins=180, range=(-90, 90))
    
    # Find peak (most common angle)
    peak_idx = np.argmax(hist)
    dominant_angle = bin_edges[peak_idx] + 0.5
    
    # Only correct if angle is significant (> 1 degree)
    if abs(dominant_angle) < 1.0:
        return img, False
    
    # Rotate image
    h, w = img.shape[:2]
    center = (w // 2, h // 2)
    
    # Get rotation matrix
    rotation_matrix = cv2.getRotationMatrix2D(center, dominant_angle, 1.0)
    
    # Calculate new image bounds
    cos = abs(rotation_matrix[0, 0])
    sin = abs(rotation_matrix[0, 1])
    new_w = int(h * sin + w * cos)
    new_h = int(h * cos + w * sin)
    
    # Adjust rotation matrix for new bounds
    rotation_matrix[0, 2] += (new_w - w) / 2
    rotation_matrix[1, 2] += (new_h - h) / 2
    
    # Apply rotation
    rotated = cv2.warpAffine(
        img,
        rotation_matrix,
        (new_w, new_h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
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
# Type-specific enhancement branches
# ---------------------------------------------------------------------------

def _enhance_photo(
    img: NDArray[np.uint8],
    raw_data: bytes,
    breakdown: Optional[QualityBreakdown],
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

    # 1. EXIF rotation
    img, orientation_corrected = correct_orientation_exif(img, raw_data)

    # 2. Border crop (scanner black borders)
    img, border_cropped = crop_borders(img)

    # 2. Exposure — compute mean brightness on (possibly rotated) image
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
    options: EnhancementOptions,
) -> Tuple[NDArray[np.uint8], bool, bool, bool, bool]:
    """
    Document enhancement pipeline.

    Operations:
      1. Border crop       — scanner borders removed if detected
      2. Orientation correction (Hough skew + large-rotation detection)
      3. NLM denoising     — gated by GUARD-001
      4. White balance + CLAHE — gated by GUARD-001

    Returns:
        (img, orientation_corrected, denoised, color_normalized, border_cropped)
    """
    skip_enhancement = should_skip_enhancement(options)
    if skip_enhancement:
        logger.info("[ENHANCEMENT] skipped (readable document)")

    border_cropped = False
    orientation_corrected = False
    denoised = False
    color_normalized = False

    # Border crop first so skew/rotation detection works on clean content
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
    Route to the correct enhancement branch based on document_type.

    - photo     → EXIF rotation, gamma correction, unsharp mask
    - signature → EXIF rotation, unsharp mask, Otsu binarization
    - document  → Hough skew correction, NLM denoising, CLAHE (GUARD-001 gated)

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
        img = decode_image(data)
        doc_type = options.document_type

        if doc_type == "photo":
            img, orientation_corrected, exposure_corrected, sharpened, border_cropped = (
                _enhance_photo(img, data, options.quality_breakdown)
            )
            result_data = encode_image(img, format="jpeg", quality=95)
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
            result_data = encode_image(img, format="jpeg", quality=95)
            return EnhancementResult(
                image_data=result_data,
                orientation_corrected=orientation_corrected,
                denoised=sharpened,            # repurposed: True = unsharp mask applied
                color_normalized=binarized,    # repurposed: True = Otsu binarization applied
                border_cropped=border_cropped,
            )

        else:  # document
            img, orientation_corrected, denoised, color_normalized, border_cropped = (
                _enhance_document(img, options)
            )
            result_data = encode_image(img, format="jpeg", quality=95)
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
]
