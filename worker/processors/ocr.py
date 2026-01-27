"""
PaddleOCR-based text extraction for Camber CPU worker.

Configuration:
- CPU only (use_gpu=False)
- English language (lang='en')
- Angle classification enabled (use_angle_cls=True)

This module is designed for single-shot execution.
The OCR engine is initialized lazily and not cached between runs.
"""

from __future__ import annotations

import logging
from typing import List, Optional, Tuple

import cv2
import numpy as np
from numpy.typing import NDArray

from models import OCRBox, OCRResult
from errors import WorkerError, ErrorCode, ProcessingStage


# Suppress PaddleOCR's verbose logging
logging.getLogger('ppocr').setLevel(logging.WARNING)


# Lazy-loaded OCR engine (no global state, created per-call)
_ocr_engine = None


def _get_ocr_engine():
    """
    Get or create PaddleOCR engine.
    
    Note: This is lazily initialized to avoid import-time side effects.
    In a single-shot worker, this will only be called once anyway.
    """
    global _ocr_engine
    
    if _ocr_engine is None:
        try:
            from paddleocr import PaddleOCR
            
            _ocr_engine = PaddleOCR(
                use_angle_cls=True,
                lang='en',
                use_gpu=False,
                show_log=False,
                # Optimize for CPU
                enable_mkldnn=True,
                cpu_threads=4,
                # Model configuration
                det_db_thresh=0.3,
                det_db_box_thresh=0.5,
                det_db_unclip_ratio=1.6,
                rec_batch_num=6,
            )
        except ImportError as e:
            raise WorkerError(
                code=ErrorCode.OCR_FAILED,
                stage=ProcessingStage.OCR,
                message=f"PaddleOCR not installed: {str(e)}",
            )
        except Exception as e:
            raise WorkerError(
                code=ErrorCode.OCR_FAILED,
                stage=ProcessingStage.OCR,
                message=f"Failed to initialize OCR engine: {str(e)}",
            )
    
    return _ocr_engine


def decode_image_for_ocr(data: bytes) -> NDArray[np.uint8]:
    """
    Decode image bytes for OCR processing.
    
    Args:
        data: Raw image bytes
        
    Returns:
        BGR image as numpy array
        
    Raises:
        WorkerError: If image cannot be decoded
    """
    nparr = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if img is None:
        raise WorkerError(
            code=ErrorCode.DECODE_FAILED,
            stage=ProcessingStage.OCR,
            message="Failed to decode image for OCR",
        )
    
    return img


def _parse_paddle_result(
    result: List,
    image_shape: Tuple[int, int, int],
) -> Tuple[str, float, List[OCRBox]]:
    """
    Parse PaddleOCR result into structured format.
    
    PaddleOCR returns a nested list structure:
    [
        [  # Page results
            [box_coords, (text, confidence)],
            ...
        ]
    ]
    
    Args:
        result: Raw PaddleOCR result
        image_shape: Shape of the input image (h, w, c)
        
    Returns:
        Tuple of (full_text, average_confidence, boxes)
    """
    if not result or not result[0]:
        return "", 0.0, []
    
    texts = []
    confidences = []
    boxes = []
    
    for line in result[0]:
        if len(line) < 2:
            continue
        
        box_coords, text_info = line
        
        if not text_info or len(text_info) < 2:
            continue
        
        text, confidence = text_info
        
        if not text or not text.strip():
            continue
        
        texts.append(text.strip())
        confidences.append(float(confidence))
        
        # Parse box coordinates
        # PaddleOCR returns 4 corner points: [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
        try:
            coords = np.array(box_coords)
            x_min = int(np.min(coords[:, 0]))
            y_min = int(np.min(coords[:, 1]))
            x_max = int(np.max(coords[:, 0]))
            y_max = int(np.max(coords[:, 1]))
            
            ocr_box = OCRBox(
                x=max(0, x_min),
                y=max(0, y_min),
                width=max(1, x_max - x_min),
                height=max(1, y_max - y_min),
                text=text.strip(),
                confidence=float(confidence),
            )
            boxes.append(ocr_box)
        except (ValueError, IndexError, TypeError):
            # Skip malformed box coordinates but keep the text
            pass
    
    # Combine all text with newlines
    full_text = '\n'.join(texts)
    
    # Calculate average confidence
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    
    return full_text, avg_confidence, boxes


def extract_text(data: bytes) -> OCRResult:
    """
    Extract text from image using PaddleOCR.
    
    This is the main entry point for OCR.
    
    Args:
        data: Raw image bytes
        
    Returns:
        OCRResult with extracted text, confidence, and bounding boxes
        
    Note:
        On OCR failure, returns empty result with warning rather than throwing.
        This follows the contract: OCR failures are handled gracefully.
    """
    try:
        # Decode image
        img = decode_image_for_ocr(data)
        
        # Get OCR engine
        ocr = _get_ocr_engine()
        
        # Run OCR
        result = ocr.ocr(img, cls=True)
        
        # Parse result
        text, confidence, boxes = _parse_paddle_result(result, img.shape)
        
        return OCRResult(
            text=text,
            confidence=confidence,
            boxes=boxes,
        )
        
    except WorkerError:
        # Re-raise worker errors (from decode or engine init)
        raise
    except Exception as e:
        # OCR runtime errors - return empty result per contract
        # "If OCR fails → return empty text + warning, do not throw"
        return OCRResult(
            text="",
            confidence=0.0,
            boxes=[],
        )


def extract_text_safe(data: bytes) -> Tuple[OCRResult, Optional[str]]:
    """
    Extract text with explicit warning handling.
    
    Args:
        data: Raw image bytes
        
    Returns:
        Tuple of (OCRResult, warning_message or None)
    """
    try:
        result = extract_text(data)
        
        warning = None
        if not result.text.strip():
            warning = "OCR returned no text"
        elif result.confidence < 0.5:
            warning = f"Low OCR confidence: {result.confidence:.2f}"
        
        return result, warning
        
    except WorkerError as e:
        # Return empty result with the error as warning
        return OCRResult(text="", confidence=0.0, boxes=[]), str(e)


__all__ = [
    'extract_text',
    'extract_text_safe',
    'OCRResult',
    'OCRBox',
]
