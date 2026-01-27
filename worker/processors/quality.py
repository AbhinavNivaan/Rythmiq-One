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
    
    # Normalize to [0, 1] range
    # Typical document images have variance between 50-500
    normalized = min(max(variance, 0.0), SHARPNESS_MAX) / SHARPNESS_MAX
    return float(normalized)


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
    
    # Ideal density for documents is around 5-15%
    # Too low = mostly blank
    # Too high = noisy or overly complex
    if density < 0.02:
        # Very low density - likely blank or nearly blank
        score = density / 0.02
    elif density < 0.05:
        # Low density - acceptable but not ideal
        score = 0.7 + 0.3 * ((density - 0.02) / 0.03)
    elif density < 0.15:
        # Ideal range
        score = 1.0
    elif density < 0.25:
        # High density - getting noisy
        score = 1.0 - 0.3 * ((density - 0.15) / 0.10)
    else:
        # Very high density - probably noisy
        score = max(0.3, 0.7 - (density - 0.25))
    
    return float(score)


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


def assess_quality(data: bytes) -> QualityResult:
    """
    Assess image quality using CPU-only metrics.
    
    This is the main entry point for quality assessment.
    
    Args:
        data: Raw image bytes
        
    Returns:
        QualityResult with overall score and breakdown
        
    Raises:
        WorkerError: If quality assessment fails
    """
    try:
        _, gray = decode_image(data)
        
        # Compute individual metrics
        sharpness = compute_sharpness(gray)
        exposure = compute_exposure(gray)
        noise = compute_noise(gray)
        edge_density = compute_edge_density(gray)
        
        # Weighted average for overall score
        # Sharpness and exposure are most important for documents
        weights = {
            'sharpness': 0.35,
            'exposure': 0.30,
            'noise': 0.20,
            'edge_density': 0.15,
        }
        
        overall_score = (
            weights['sharpness'] * sharpness +
            weights['exposure'] * exposure +
            weights['noise'] * noise +
            weights['edge_density'] * edge_density
        )
        
        breakdown = QualityBreakdown(
            sharpness=sharpness,
            exposure=exposure,
            noise=noise,
            edge_density=edge_density,
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
    'QualityResult',
    'QualityBreakdown',
    'QUALITY_WARNING_THRESHOLD',
]
