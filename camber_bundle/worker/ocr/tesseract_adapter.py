"""
Tesseract OCR adapter for document text extraction.

Uses pytesseract (Python wrapper for Tesseract CLI).
Supports PNG, JPEG, TIFF images. PDFs are explicitly rejected.
"""

from typing import Tuple, Optional
from dataclasses import dataclass
import io

# pytesseract is the only external OCR dependency
import pytesseract
from PIL import Image

from errors.error_codes import ProcessingError, ErrorCode, ProcessingStage


# Default configuration
DEFAULT_MAX_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB
DEFAULT_LANGUAGE = "eng"


@dataclass(frozen=True)
class OCRResult:
    """
    Immutable OCR result.
    
    Contains extracted text, confidence score, and page count.
    For single images, page_count is always 1.
    """
    text: str
    confidence: float  # 0.0 to 1.0
    page_count: int


def detect_format(data: bytes) -> Optional[str]:
    """
    Detect image format from magic bytes.
    
    Returns MIME type or None if unrecognized.
    This is deterministic - no guessing based on content.
    """
    if len(data) < 4:
        return None
    
    # PNG: 89 50 4E 47
    if data[0:4] == b'\x89PNG':
        return "image/png"
    
    # JPEG: FF D8 FF
    if data[0:3] == b'\xff\xd8\xff':
        return "image/jpeg"
    
    # TIFF: 49 49 2A 00 (little-endian) or 4D 4D 00 2A (big-endian)
    if data[0:4] == b'II*\x00' or data[0:4] == b'MM\x00*':
        return "image/tiff"
    
    # PDF: %PDF - explicitly rejected
    if data[0:4] == b'%PDF':
        return "application/pdf"
    
    return None


def extract_text(
    data: bytes,
    language: str = DEFAULT_LANGUAGE,
    max_size_bytes: int = DEFAULT_MAX_SIZE_BYTES
) -> OCRResult:
    """
    Extract text from image bytes using Tesseract.
    
    Args:
        data: Raw image bytes (PNG, JPEG, or TIFF)
        language: Tesseract language code (e.g., "eng", "fra")
        max_size_bytes: Maximum allowed file size
        
    Returns:
        OCRResult with extracted text and confidence
        
    Raises:
        ProcessingError: For any OCR failure (deterministic error codes)
    """
    # Validate: empty data
    if not data or len(data) == 0:
        raise ProcessingError(
            code=ErrorCode.CORRUPT_DATA,
            stage=ProcessingStage.OCR,
            details={"reason": "empty_data"}
        )
    
    # Validate: size limit
    if len(data) > max_size_bytes:
        raise ProcessingError(
            code=ErrorCode.SIZE_EXCEEDED,
            stage=ProcessingStage.OCR,
            details={
                "size_bytes": len(data),
                "max_bytes": max_size_bytes
            }
        )
    
    # Validate: format detection
    format_type = detect_format(data)
    
    if format_type is None:
        raise ProcessingError(
            code=ErrorCode.UNSUPPORTED_FORMAT,
            stage=ProcessingStage.OCR,
            details={"reason": "unrecognized_format"}
        )
    
    if format_type == "application/pdf":
        raise ProcessingError(
            code=ErrorCode.UNSUPPORTED_FORMAT,
            stage=ProcessingStage.OCR,
            details={"reason": "pdf_not_supported"}
        )
    
    # Attempt to open image with PIL
    try:
        image = Image.open(io.BytesIO(data))
    except Exception:
        raise ProcessingError(
            code=ErrorCode.CORRUPT_DATA,
            stage=ProcessingStage.OCR,
            details={"reason": "image_decode_failed"}
        )
    
    # Run Tesseract OCR
    try:
        # Get text with detailed data for confidence calculation
        ocr_data = pytesseract.image_to_data(
            image,
            lang=language,
            output_type=pytesseract.Output.DICT
        )
        
        # Extract text (joining all recognized words)
        words = ocr_data.get("text", [])
        text = " ".join(w for w in words if w.strip())
        
        # Calculate average confidence (exclude -1 values which indicate no text)
        confidences = [
            c for c in ocr_data.get("conf", [])
            if isinstance(c, (int, float)) and c >= 0
        ]
        
        if confidences:
            avg_confidence = sum(confidences) / len(confidences) / 100.0  # Convert to 0-1
        else:
            avg_confidence = 0.0
        
        # Validate: no text extracted
        if not text.strip():
            raise ProcessingError(
                code=ErrorCode.OCR_FAILURE,
                stage=ProcessingStage.OCR,
                details={"reason": "no_text_extracted"}
            )
        
        return OCRResult(
            text=text,
            confidence=min(1.0, max(0.0, avg_confidence)),  # Clamp to [0, 1]
            page_count=1
        )
        
    except ProcessingError:
        # Re-raise our own errors
        raise
    except Exception:
        # Any Tesseract error becomes OCR_FAILURE
        raise ProcessingError(
            code=ErrorCode.OCR_FAILURE,
            stage=ProcessingStage.OCR,
            details={"reason": "tesseract_error"}
        )
