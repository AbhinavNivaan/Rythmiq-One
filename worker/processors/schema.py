"""
Schema adaptation for Camber CPU worker.

Implements pixel-perfect document transformation:
- Exact resize to target dimensions
- DPI injection into output metadata
- Compression loop until file size < max_kb
- Filename normalization

A single pixel mismatch is a failure.
"""

from __future__ import annotations

import io
import re
from typing import Tuple

import cv2
import numpy as np
from numpy.typing import NDArray
from PIL import Image

from models import SchemaDefinition, SchemaResult
from errors import WorkerError, ErrorCode, ProcessingStage


# Maximum compression iterations to prevent infinite loops
MAX_COMPRESSION_ITERATIONS = 20

# Minimum JPEG quality threshold
MIN_JPEG_QUALITY = 20


def decode_image(data: bytes) -> Tuple[NDArray[np.uint8], Image.Image]:
    """
    Decode image bytes to both OpenCV and PIL formats.
    
    Args:
        data: Raw image bytes
        
    Returns:
        Tuple of (OpenCV BGR array, PIL Image)
        
    Raises:
        WorkerError: If image cannot be decoded
    """
    # Decode with OpenCV for resize operations
    nparr = np.frombuffer(data, np.uint8)
    cv_img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if cv_img is None:
        raise WorkerError(
            code=ErrorCode.DECODE_FAILED,
            stage=ProcessingStage.SCHEMA,
            message="Failed to decode image for schema adaptation",
        )
    
    # Also open with PIL for DPI operations
    try:
        pil_img = Image.open(io.BytesIO(data))
    except Exception as e:
        raise WorkerError(
            code=ErrorCode.DECODE_FAILED,
            stage=ProcessingStage.SCHEMA,
            message=f"Failed to decode image with PIL: {str(e)}",
        )
    
    return cv_img, pil_img


def resize_exact(
    img: NDArray[np.uint8],
    target_width: int,
    target_height: int,
) -> NDArray[np.uint8]:
    """
    Resize image to exact target dimensions.
    
    Uses INTER_LANCZOS4 for highest quality downsampling.
    A single pixel mismatch is a failure.
    
    Args:
        img: BGR image array
        target_width: Target width in pixels
        target_height: Target height in pixels
        
    Returns:
        Resized image array
        
    Raises:
        WorkerError: If resize fails or dimensions don't match
    """
    try:
        resized = cv2.resize(
            img,
            (target_width, target_height),
            interpolation=cv2.INTER_LANCZOS4,
        )
        
        # Verify exact dimensions
        h, w = resized.shape[:2]
        if w != target_width or h != target_height:
            raise WorkerError(
                code=ErrorCode.RESIZE_FAILED,
                stage=ProcessingStage.SCHEMA,
                message=f"Resize dimension mismatch: expected {target_width}x{target_height}, got {w}x{h}",
            )
        
        return resized
        
    except cv2.error as e:
        raise WorkerError(
            code=ErrorCode.RESIZE_FAILED,
            stage=ProcessingStage.SCHEMA,
            message=f"OpenCV resize failed: {str(e)}",
        )


def encode_with_dpi(
    img: NDArray[np.uint8],
    dpi: int,
    format: str = "jpeg",
    quality: int = 85,
) -> bytes:
    """
    Encode image with DPI metadata.
    
    Args:
        img: BGR image array
        dpi: Target DPI value
        format: Output format (jpeg, png)
        quality: JPEG quality (1-100)
        
    Returns:
        Encoded image bytes with DPI metadata
    """
    # Convert BGR to RGB for PIL
    rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(rgb_img)
    
    # Set DPI
    pil_img.info['dpi'] = (dpi, dpi)
    
    # Encode
    buffer = io.BytesIO()
    
    if format.lower() in ("jpeg", "jpg"):
        pil_img.save(
            buffer,
            format="JPEG",
            quality=quality,
            dpi=(dpi, dpi),
            optimize=True,
        )
    elif format.lower() == "png":
        pil_img.save(
            buffer,
            format="PNG",
            dpi=(dpi, dpi),
            optimize=True,
        )
    else:
        # Default to JPEG
        pil_img.save(
            buffer,
            format="JPEG",
            quality=quality,
            dpi=(dpi, dpi),
            optimize=True,
        )
    
    return buffer.getvalue()


def compress_to_size(
    img: NDArray[np.uint8],
    dpi: int,
    max_kb: int,
    format: str = "jpeg",
    initial_quality: int = 85,
) -> Tuple[bytes, int]:
    """
    Compress image until it fits within max_kb.
    
    Uses a binary search approach to find optimal quality.
    
    Args:
        img: BGR image array
        dpi: Target DPI value
        max_kb: Maximum file size in KB
        format: Output format
        initial_quality: Starting quality
        
    Returns:
        Tuple of (compressed bytes, final quality)
        
    Raises:
        WorkerError: If compression cannot achieve target size
    """
    max_bytes = max_kb * 1024
    quality = initial_quality
    
    # First try at initial quality
    data = encode_with_dpi(img, dpi, format, quality)
    
    if len(data) <= max_bytes:
        return data, quality
    
    # Binary search for optimal quality
    low_quality = MIN_JPEG_QUALITY
    high_quality = quality
    best_data = data
    best_quality = quality
    
    for _ in range(MAX_COMPRESSION_ITERATIONS):
        if low_quality > high_quality:
            break
        
        mid_quality = (low_quality + high_quality) // 2
        data = encode_with_dpi(img, dpi, format, mid_quality)
        
        if len(data) <= max_bytes:
            best_data = data
            best_quality = mid_quality
            low_quality = mid_quality + 1
        else:
            high_quality = mid_quality - 1
    
    # Final check
    if len(best_data) > max_bytes:
        # Try minimum quality as last resort
        data = encode_with_dpi(img, dpi, format, MIN_JPEG_QUALITY)
        
        if len(data) > max_bytes:
            raise WorkerError(
                code=ErrorCode.SIZE_EXCEEDED,
                stage=ProcessingStage.SCHEMA,
                message=f"Cannot compress to {max_kb}KB even at minimum quality",
                details={
                    "min_size_kb": len(data) // 1024,
                    "target_kb": max_kb,
                },
            )
        
        return data, MIN_JPEG_QUALITY
    
    return best_data, best_quality


def normalize_filename(
    pattern: str,
    job_id: str,
    user_id: str = "",
    original_filename: str = "",
) -> str:
    """
    Normalize filename according to pattern.
    
    Pattern variables:
    - {job_id}: Job UUID
    - {user_id}: User UUID  
    - {original}: Original filename (without extension)
    - {timestamp}: Unix timestamp
    
    Args:
        pattern: Filename pattern
        job_id: Job UUID
        user_id: User UUID
        original_filename: Original filename
        
    Returns:
        Normalized filename
    """
    import time
    
    # Extract original filename without extension
    original_base = original_filename.rsplit('.', 1)[0] if '.' in original_filename else original_filename
    
    # Replace pattern variables
    filename = pattern.replace("{job_id}", job_id)
    filename = filename.replace("{user_id}", user_id)
    filename = filename.replace("{original}", original_base)
    filename = filename.replace("{timestamp}", str(int(time.time())))
    
    # Sanitize: remove invalid characters
    filename = re.sub(r'[^\w\-.]', '_', filename)
    
    # Remove consecutive underscores
    filename = re.sub(r'_+', '_', filename)
    
    # Trim underscores from ends
    filename = filename.strip('_')
    
    return filename


def adapt_to_schema(
    data: bytes,
    schema: SchemaDefinition,
    job_id: str,
    user_id: str = "",
    original_filename: str = "",
) -> SchemaResult:
    """
    Adapt image to schema specifications.
    
    This is the main entry point for schema adaptation.
    
    Args:
        data: Raw image bytes
        schema: Target schema definition
        job_id: Job UUID for filename
        user_id: User UUID for filename
        original_filename: Original filename
        
    Returns:
        SchemaResult with adapted image and metadata
        
    Raises:
        WorkerError: If schema adaptation fails
    """
    try:
        # Decode image
        cv_img, _ = decode_image(data)
        
        # Resize to exact dimensions
        resized = resize_exact(
            cv_img,
            schema.target_width,
            schema.target_height,
        )
        
        # Verify dimensions (belt and suspenders)
        h, w = resized.shape[:2]
        if w != schema.target_width or h != schema.target_height:
            raise WorkerError(
                code=ErrorCode.RESIZE_FAILED,
                stage=ProcessingStage.SCHEMA,
                message="Post-resize dimension verification failed",
            )
        
        # Compress to size with DPI
        compressed_data, final_quality = compress_to_size(
            resized,
            dpi=schema.target_dpi,
            max_kb=schema.max_kb,
            format=schema.output_format,
            initial_quality=schema.quality,
        )
        
        # Normalize filename
        filename = normalize_filename(
            schema.filename_pattern,
            job_id=job_id,
            user_id=user_id,
            original_filename=original_filename,
        )
        
        # Add extension if not present
        ext = ".jpg" if schema.output_format.lower() in ("jpeg", "jpg") else f".{schema.output_format.lower()}"
        if not filename.lower().endswith(ext):
            filename = f"{filename}{ext}"
        
        return SchemaResult(
            image_data=compressed_data,
            final_width=schema.target_width,
            final_height=schema.target_height,
            final_dpi=schema.target_dpi,
            final_size_kb=len(compressed_data) / 1024,
            filename=filename,
        )
        
    except WorkerError:
        raise
    except Exception as e:
        raise WorkerError(
            code=ErrorCode.SCHEMA_FAILED,
            stage=ProcessingStage.SCHEMA,
            message=f"Schema adaptation failed: {str(e)}",
            details={"exception_type": type(e).__name__},
        )


def verify_schema_compliance(
    data: bytes,
    schema: SchemaDefinition,
) -> Tuple[bool, str]:
    """
    Verify that image data complies with schema.
    
    Args:
        data: Encoded image bytes
        schema: Expected schema
        
    Returns:
        Tuple of (is_compliant, error_message)
    """
    try:
        # Check file size
        size_kb = len(data) / 1024
        if size_kb > schema.max_kb:
            return False, f"Size {size_kb:.1f}KB exceeds max {schema.max_kb}KB"
        
        # Decode and check dimensions with OpenCV
        nparr = np.frombuffer(data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if img is None:
            return False, "Failed to decode image"
        
        h, w = img.shape[:2]
        if w != schema.target_width:
            return False, f"Width {w} != target {schema.target_width}"
        
        if h != schema.target_height:
            return False, f"Height {h} != target {schema.target_height}"
        
        # Verify DPI metadata using PIL
        pil_img = Image.open(io.BytesIO(data))
        dpi = pil_img.info.get('dpi', (72, 72))
        if isinstance(dpi, tuple):
            dpi_x, dpi_y = int(dpi[0]), int(dpi[1])
        else:
            dpi_x = dpi_y = int(dpi)
        
        if dpi_x != schema.target_dpi:
            return False, f"DPI X {dpi_x} != target {schema.target_dpi}"
        
        if dpi_y != schema.target_dpi:
            return False, f"DPI Y {dpi_y} != target {schema.target_dpi}"
        
        return True, ""
        
    except Exception as e:
        return False, f"Verification error: {str(e)}"



__all__ = [
    'adapt_to_schema',
    'verify_schema_compliance',
    'normalize_filename',
    'resize_exact',
    'compress_to_size',
    'SchemaResult',
    'SchemaDefinition',
]
