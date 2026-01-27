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

import logging
from dataclasses import dataclass
from typing import Optional, Tuple, Literal

import cv2
import numpy as np
from numpy.typing import NDArray

from models import EnhancementResult
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
    Apply all enhancement operations to an image.
    
    This is the main entry point for image enhancement.
    
    Includes GUARD-001: Skip denoise+CLAHE for readable images.
    
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
    
    # GUARD-001: Check if we should skip enhancement
    skip_enhancement = should_skip_enhancement(options)
    if skip_enhancement:
        logger.info("[ENHANCEMENT] skipped (readable input)")
    
    try:
        # Decode image
        img = decode_image(data)
        
        orientation_corrected = False
        denoised = False
        color_normalized = False
        
        # Apply orientation correction (always allowed)
        if options.correct_orientation:
            img, orientation_corrected = correct_orientation(img)
        
        # Apply denoising (skip if GUARD-001 triggered)
        if options.denoise and not skip_enhancement:
            img, denoised = denoise(img, strength=options.denoise_strength)
        
        # Apply color normalization (skip if GUARD-001 triggered)
        if options.normalize_color and not skip_enhancement:
            # First apply white balance
            img, _ = auto_white_balance(img)
            
            # Then apply CLAHE
            img, color_normalized = normalize_color(
                img,
                clip_limit=options.clahe_clip_limit,
                grid_size=options.clahe_grid_size,
            )
        
        # Encode result
        result_data = encode_image(img, format="jpeg", quality=95)
        
        return EnhancementResult(
            image_data=result_data,
            orientation_corrected=orientation_corrected,
            denoised=denoised,
            color_normalized=color_normalized,
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
    'correct_orientation',
    'denoise',
    'normalize_color',
    'auto_white_balance',
    'detect_large_rotation',
    'apply_large_rotation',
    'should_skip_enhancement',
    'READABLE_QUALITY_THRESHOLD',
]
