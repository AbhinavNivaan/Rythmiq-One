"""
CPU-only image quality assessment for Camber worker.

Computes quality metrics using standard image processing techniques:
- Laplacian variance (sharpness/blur detection)
- Histogram analysis (exposure balance)
- Noise estimation (signal-to-noise ratio)
- Edge density (content richness)

No GPU. No ML models. Pure NumPy/OpenCV operations.
"""

from __future__ import annotations

from typing import Tuple

import cv2
import numpy as np
from numpy.typing import NDArray

from models import QualityBreakdown, QualityResult
from errors import WorkerError, ErrorCode, ProcessingStage


# Quality thresholds
QUALITY_WARNING_THRESHOLD = 0.80
SHARPNESS_MIN = 50.0  # Below this is considered blurry
SHARPNESS_MAX = 500.0  # Normalize to this range
# Photo-specific sharpness constants — portraits have smoother regions than text
SHARPNESS_MIN_PHOTO = 20.0
SHARPNESS_MAX_PHOTO = 300.0

# Type-aware quality weights — each document type has different priorities
QUALITY_WEIGHTS = {
    "photo":     {"sharpness": 0.25, "exposure": 0.20, "noise": 0.20,
                  "saturation": 0.20, "contrast": 0.15, "edge_density": 0.00},
    "signature": {"sharpness": 0.40, "exposure": 0.30, "noise": 0.20,
                  "saturation": 0.00, "contrast": 0.00, "edge_density": 0.10},
    "document":  {"sharpness": 0.35, "exposure": 0.30, "noise": 0.20,
                  "saturation": 0.00, "contrast": 0.00, "edge_density": 0.15},
}


def compute_sharpness(gray: NDArray[np.uint8]) -> float:
    """
    Compute sharpness using Laplacian variance.
    
    Higher values indicate sharper images.
    Blurry images have low variance in the Laplacian.
    
    Args:
        gray: Grayscale image as uint8 array
        
    Returns:
        Normalized sharpness score [0.0, 1.0]
    """
    laplacian = cv2.Laplacian(gray, cv2.CV_64F)
    variance = laplacian.var()

    # Normalize to [0, 1] range using [SHARPNESS_MIN, SHARPNESS_MAX].
    # Images below SHARPNESS_MIN are considered blurry and score 0.0.
    normalized = (variance - SHARPNESS_MIN) / (SHARPNESS_MAX - SHARPNESS_MIN)
    return float(min(max(normalized, 0.0), 1.0))


def compute_exposure(gray: NDArray[np.uint8]) -> float:
    """
    Compute exposure for document images using contrast measurement.
    
    Documents have bimodal histograms (white paper + dark text).
    Good exposure = high contrast = high histogram standard deviation.
    
    Unlike natural scene photography where middle-gray (127) is ideal,
    documents are expected to have bright backgrounds (200-240) with
    dark text, resulting in high standard deviation.
    
    Args:
        gray: Grayscale image as uint8 array
        
    Returns:
        Exposure balance score [0.0, 1.0]
    """
    # Compute histogram
    hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
    hist = hist.flatten() / hist.sum()
    
    # Calculate histogram statistics
    values = np.arange(256)
    mean_val = np.sum(values * hist)
    std_val = np.sqrt(np.sum(((values - mean_val) ** 2) * hist))
    
    # Score based on contrast (standard deviation)
    # Good documents have std > 60 (bimodal: dark text + light background)
    # Bad exposure (washed out or too dark): std < 30
    if std_val < 20:
        # Very low contrast - bad
        score = std_val / 20 * 0.5
    elif std_val < 40:
        # Low contrast
        score = 0.5 + 0.3 * ((std_val - 20) / 20)
    elif std_val < 80:
        # Good contrast
        score = 0.8 + 0.2 * ((std_val - 40) / 40)
    else:
        # High contrast - ideal for documents
        score = 1.0
    
    # Penalize extreme cases (nearly blank or completely dark)
    dark_fraction = hist[0:30].sum()
    bright_fraction = hist[225:256].sum()
    
    if dark_fraction > 0.9:
        # Almost entirely dark - likely underexposed or blank dark image
        score *= 0.3
    elif bright_fraction > 0.98:
        # Almost entirely white - blank page or completely washed out
        score *= 0.5
    
    return float(score)


def compute_exposure_photo(gray: NDArray[np.uint8]) -> float:
    """
    Compute exposure score for photos using mean brightness.

    Photos are well-exposed when mean brightness is in the 80–200 range.
    Unlike documents, they do NOT require a high-contrast bimodal histogram;
    a smooth portrait background scores perfectly here.

    Args:
        gray: Grayscale image as uint8 array

    Returns:
        Exposure score [0.0, 1.0]
    """
    mean_brightness = float(np.mean(gray))

    if mean_brightness < 80:
        # Underexposed: 0 at pitch-black, 1.0 at mean=80
        return mean_brightness / 80.0
    elif mean_brightness <= 200:
        # Ideal range
        return 1.0
    else:
        # Overexposed: 1.0 at mean=200, 0 at mean=255
        return (255.0 - mean_brightness) / 55.0


def compute_noise(gray: NDArray[np.uint8]) -> float:
    """
    Estimate noise level using high-pass filter residual.
    
    Lower noise is better. Returns inverted score where
    1.0 = no noise, 0.0 = very noisy.
    
    Args:
        gray: Grayscale image as uint8 array
        
    Returns:
        Noise quality score [0.0, 1.0] (higher is less noisy)
    """
    # Apply Gaussian blur to get "ideal" image
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    
    # Compute residual (noise)
    residual = gray.astype(np.float32) - blurred.astype(np.float32)
    
    # Standard deviation of residual estimates noise level
    noise_std = np.std(residual)
    
    # Normalize: typical noise std is 0-30
    # Higher std = more noise = lower quality
    noise_normalized = min(noise_std / 30.0, 1.0)
    
    # Invert so higher is better
    return float(1.0 - noise_normalized)


def compute_edge_density(gray: NDArray[np.uint8]) -> float:
    """
    Compute edge density as a measure of content richness.
    
    Documents should have a reasonable amount of edges (text, lines).
    Too few edges might indicate blank regions.
    Too many might indicate excessive noise.
    
    Args:
        gray: Grayscale image as uint8 array
        
    Returns:
        Edge density score [0.0, 1.0]
    """
    # Canny edge detection
    edges = cv2.Canny(gray, 50, 150)
    
    # Compute density (percentage of edge pixels)
    total_pixels = gray.shape[0] * gray.shape[1]
    edge_pixels = np.count_nonzero(edges)
    density = edge_pixels / total_pixels
    
    # Ideal density for clean cropped documents is 2–12 % (text lines on white paper).
    # The wider ideal band (vs. a full scene photo which has more background texture)
    # prevents penalising clean document crops that were correctly separated from a
    # busy background.
    if density < 0.01:
        # Nearly blank — no content
        score = density / 0.01
    elif density < 0.03:
        # Very low — sparse text or margins
        score = 0.75 + 0.25 * ((density - 0.01) / 0.02)
    elif density < 0.12:
        # Ideal range for text documents
        score = 1.0
    elif density < 0.22:
        # Getting noisy
        score = 1.0 - 0.3 * ((density - 0.12) / 0.10)
    else:
        # Very high — probably noisy / cluttered
        score = max(0.3, 0.7 - (density - 0.22))
    
    return float(score)


def compute_sharpness_photo(gray: NDArray[np.uint8]) -> float:
    """
    Compute sharpness for photos using noise-resilient Laplacian variance.

    A light Gaussian pre-blur suppresses noise-band energy so that
    Laplacian variance reflects real focus quality rather than grain.
    Uses photo-calibrated constants (portraits have smoother regions
    than text documents).

    Args:
        gray: Grayscale image as uint8 array

    Returns:
        Normalized sharpness score [0.0, 1.0]
    """
    denoised = cv2.GaussianBlur(gray, (3, 3), 0)
    laplacian = cv2.Laplacian(denoised, cv2.CV_64F)
    variance = laplacian.var()

    normalized = (variance - SHARPNESS_MIN_PHOTO) / (SHARPNESS_MAX_PHOTO - SHARPNESS_MIN_PHOTO)
    return float(min(max(normalized, 0.0), 1.0))


def compute_saturation(img_bgr: NDArray[np.uint8]) -> float:
    """
    Compute color saturation score from the BGR image.

    Uses mean HSV saturation with a B&W-aware curve: true monochrome
    photos (mean S < 10) receive a neutral 0.50 rather than being
    penalised, while suspiciously desaturated colour photos (S 10-25)
    score lower.

    Args:
        img_bgr: BGR image as uint8 array

    Returns:
        Saturation quality score [0.0, 1.0]
    """
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    mean_sat = float(np.mean(hsv[:, :, 1]))

    if mean_sat < 10:
        # True B&W / near-monochrome — neutral score (not penalised)
        return 0.50
    elif mean_sat < 25:
        # Suspiciously desaturated colour photo
        return 0.30 + 0.20 * ((mean_sat - 10) / 15.0)
    elif mean_sat < 40:
        # Low saturation but potentially intentional
        return 0.50 + 0.50 * ((mean_sat - 25) / 15.0)
    elif mean_sat <= 160:
        # Ideal range for portraits
        return 1.0
    elif mean_sat <= 200:
        # Oversaturated
        return 1.0 - 0.5 * ((mean_sat - 160) / 40.0)
    else:
        # Extremely oversaturated
        return max(0.3, 0.5 - (mean_sat - 200) / 110.0)


def compute_contrast(gray: NDArray[np.uint8]) -> float:
    """
    Compute tonal contrast using the percentile dynamic range.

    Dynamic range = P95 - P5 of grayscale intensity.  More robust than
    standard deviation because it ignores small numbers of extreme
    outlier pixels (specular highlights, dead pixels).

    Args:
        gray: Grayscale image as uint8 array

    Returns:
        Contrast quality score [0.0, 1.0]
    """
    p5 = float(np.percentile(gray, 5))
    p95 = float(np.percentile(gray, 95))
    dynamic_range = p95 - p5

    if dynamic_range < 30:
        # Very flat — almost no tonal variation
        return dynamic_range / 30.0 * 0.3
    elif dynamic_range < 80:
        # Low contrast
        return 0.3 + 0.5 * ((dynamic_range - 30) / 50.0)
    elif dynamic_range < 180:
        # Good contrast
        return 0.8 + 0.2 * min((dynamic_range - 80) / 100.0, 1.0)
    else:
        # Excellent dynamic range
        return 1.0


def decode_image(data: bytes) -> Tuple[NDArray[np.uint8], NDArray[np.uint8]]:
    """
    Decode image bytes to OpenCV arrays.
    
    Args:
        data: Raw image bytes (JPEG, PNG, etc.)
        
    Returns:
        Tuple of (BGR image, grayscale image)
        
    Raises:
        WorkerError: If image cannot be decoded
    """
    # Decode from bytes
    nparr = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if img is None:
        raise WorkerError(
            code=ErrorCode.DECODE_FAILED,
            stage=ProcessingStage.QUALITY,
            message="Failed to decode image for quality assessment",
        )
    
    # Convert to grayscale for analysis
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    return img, gray


def assess_quality(data: bytes, document_type: str = "document") -> QualityResult:
    """
    Assess image quality using CPU-only metrics.

    Uses type-aware weights so photos, signatures, and documents are each
    scored against criteria that are meaningful for their content.

    Args:
        data: Raw image bytes
        document_type: One of "photo", "signature", "document"

    Returns:
        QualityResult with overall score and breakdown

    Raises:
        WorkerError: If quality assessment fails
    """
    try:
        img_bgr, gray = decode_image(data)

        # Compute individual metrics
        # Photos use noise-resilient sharpness with photo-calibrated constants
        sharpness = compute_sharpness_photo(gray) if document_type == "photo" else compute_sharpness(gray)
        # Photos use mean-brightness exposure; documents/signatures use contrast std-dev
        exposure = compute_exposure_photo(gray) if document_type == "photo" else compute_exposure(gray)
        noise = compute_noise(gray)
        edge_density = compute_edge_density(gray)
        saturation = compute_saturation(img_bgr)
        contrast = compute_contrast(gray)

        # Type-aware weighted average
        weights = QUALITY_WEIGHTS.get(document_type, QUALITY_WEIGHTS["document"])

        overall_score = (
            weights['sharpness'] * sharpness +
            weights['exposure'] * exposure +
            weights['noise'] * noise +
            weights['edge_density'] * edge_density +
            weights.get('saturation', 0.0) * saturation +
            weights.get('contrast', 0.0) * contrast
        )

        breakdown = QualityBreakdown(
            sharpness=sharpness,
            exposure=exposure,
            noise=noise,
            edge_density=edge_density,
            saturation=saturation,
            contrast=contrast,
        )
        
        return QualityResult(
            score=overall_score,
            breakdown=breakdown,
        )
        
    except WorkerError:
        raise
    except Exception as e:
        raise WorkerError(
            code=ErrorCode.QUALITY_FAILED,
            stage=ProcessingStage.QUALITY,
            message=f"Quality assessment failed: {str(e)}",
            details={"exception_type": type(e).__name__},
        )


def check_quality_warning(score: float) -> bool:
    """
    Check if quality score warrants a warning.
    
    Args:
        score: Overall quality score
        
    Returns:
        True if score is below warning threshold
    """
    return score < QUALITY_WARNING_THRESHOLD


__all__ = [
    'assess_quality',
    'check_quality_warning',
    'compute_exposure_photo',
    'compute_sharpness_photo',
    'compute_saturation',
    'compute_contrast',
    'QualityResult',
    'QualityBreakdown',
    'QUALITY_WARNING_THRESHOLD',
    'QUALITY_WEIGHTS',
]
