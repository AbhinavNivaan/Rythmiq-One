"""
PaddleOCR-based text extraction for Camber CPU worker.

Configuration:
- CPU only (use_gpu=False)
- English language (lang='en')
- Angle classification enabled (use_angle_cls=True)

This module is designed for single-shot execution.
The OCR engine is initialized lazily and not cached between runs.

Compatibility:
- Supports both PaddleOCR 2.x and 3.x APIs
- PaddleOCR 3.x removed `show_log` parameter (use logging system instead)
- Uses feature detection to handle version differences gracefully
"""

from __future__ import annotations

import inspect
import logging
import os
from typing import List, Optional, Tuple

import cv2
import numpy as np
from numpy.typing import NDArray

from models import OCRBox, OCRResult
from errors import WorkerError, ErrorCode, ProcessingStage


# Suppress PaddleOCR's verbose logging (works for both 2.x and 3.x)
logging.getLogger('ppocr').setLevel(logging.WARNING)
logging.getLogger('paddle').setLevel(logging.WARNING)

# PaddleOCR 3.x uses paddleocr.utils.logging
try:
    logging.getLogger('paddleocr').setLevel(logging.WARNING)
except Exception:
    pass


# Lazy-loaded OCR engine (no global state, created per-call)
_ocr_engine = None
_ocr_init_error: Optional[str] = None


def _detect_paddleocr_version() -> tuple:
    """
    Detect installed PaddleOCR version.
    
    Returns:
        Tuple of (major, minor, patch) or (0, 0, 0) if unknown
    """
    try:
        import paddleocr
        version_str = getattr(paddleocr, '__version__', '0.0.0')
        parts = version_str.split('.')
        return tuple(int(p) for p in parts[:3])
    except Exception:
        return (0, 0, 0)


def _build_ocr_kwargs() -> dict:
    """
    Build PaddleOCR constructor kwargs with version-aware parameter filtering.
    
    PaddleOCR 3.x removed several parameters:
    - `show_log` (use logging system instead)
    - `use_gpu` (use device parameter or auto-detect)
    - `enable_mkldnn` (auto-detected in 3.x)
    - `det_db_thresh`, `det_db_box_thresh`, etc. (use config files)
    
    This function detects the available parameters and builds a compatible kwargs dict.
    """
    # Parameters for PaddleOCR 2.x only
    v2_kwargs = {
        'lang': 'en',
        'use_gpu': False,
        'use_angle_cls': True,
        'show_log': False,
        'enable_mkldnn': True,
        'cpu_threads': 4,
        'det_db_thresh': 0.3,
        'det_db_box_thresh': 0.5,
        'det_db_unclip_ratio': 1.6,
        'rec_batch_num': 6,
    }
    
    # Parameters for PaddleOCR 3.x (completely new API)
    # Note: 3.x uses 'lang' but removed 'use_gpu' (uses device='cpu' instead)
    v3_kwargs = {
        'lang': 'en',
        'use_doc_orientation_classify': False,
        'use_doc_unwarping': False,
        'use_textline_orientation': False,
    }
    
    try:
        from paddleocr import PaddleOCR
        
        # Detect version
        version = _detect_paddleocr_version()
        is_v3 = version[0] >= 3
        
        logging.debug(f"PaddleOCR version detected: {version}, is_v3: {is_v3}")
        
        if is_v3:
            # PaddleOCR 3.x: use new simplified parameters
            kwargs = dict(v3_kwargs)
            
            # Check if 'device' parameter exists (for explicit CPU mode)
            sig = inspect.signature(PaddleOCR.__init__)
            valid_params = set(sig.parameters.keys())
            if 'device' in valid_params:
                kwargs['device'] = 'cpu'
        else:
            # PaddleOCR 2.x: use detailed parameters
            kwargs = dict(v2_kwargs)
        
        return kwargs
        
    except Exception as e:
        # If detection fails, return minimal safe kwargs (lang only)
        logging.warning(f"PaddleOCR parameter detection failed: {e}, using minimal config")
        return {'lang': 'en'}


def _get_ocr_engine():
    """
    Get or create PaddleOCR engine with defensive initialization.
    
    Note: This is lazily initialized to avoid import-time side effects.
    In a single-shot worker, this will only be called once anyway.
    
    Version Compatibility:
    - PaddleOCR 2.x: Uses `show_log`, `enable_mkldnn`, detailed config
    - PaddleOCR 3.x: Uses new logging system, simplified API
    
    Error Handling:
    - Import errors raise WorkerError (PaddleOCR not installed)
    - Unknown argument errors trigger fallback to minimal config
    - Other errors raise WorkerError with details
    """
    global _ocr_engine, _ocr_init_error
    
    # If we already have an engine, return it
    if _ocr_engine is not None:
        return _ocr_engine
    
    # If we already tried and failed, raise the cached error
    if _ocr_init_error is not None:
        raise WorkerError(
            code=ErrorCode.OCR_FAILED,
            stage=ProcessingStage.OCR,
            message=_ocr_init_error,
        )
    
    try:
        from paddleocr import PaddleOCR
        
        # Suppress PaddleOCR 3.x logging via environment variable
        os.environ.setdefault('PADDLEOCR_LOG_LEVEL', 'WARNING')
        
        # Build version-aware kwargs
        kwargs = _build_ocr_kwargs()
        
        logging.info(f"Initializing PaddleOCR with kwargs: {list(kwargs.keys())}")
        
        try:
            _ocr_engine = PaddleOCR(**kwargs)
        except TypeError as e:
            # Handle "Unknown argument" errors by stripping problematic params
            error_msg = str(e).lower()
            if 'unknown argument' in error_msg or 'unexpected keyword' in error_msg:
                logging.warning(f"PaddleOCR init failed with kwargs, falling back to minimal config: {e}")
                # Fallback to absolute minimum
                _ocr_engine = PaddleOCR(lang='en', use_gpu=False)
            else:
                raise
                
    except ImportError as e:
        _ocr_init_error = f"PaddleOCR not installed: {str(e)}"
        raise WorkerError(
            code=ErrorCode.OCR_FAILED,
            stage=ProcessingStage.OCR,
            message=_ocr_init_error,
        )
    except Exception as e:
        _ocr_init_error = f"Failed to initialize OCR engine: {str(e)}"
        raise WorkerError(
            code=ErrorCode.OCR_FAILED,
            stage=ProcessingStage.OCR,
            message=_ocr_init_error,
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


def _run_ocr_inference(ocr, img):
    """
    Run OCR inference with version-aware API handling.
    
    PaddleOCR 2.x: ocr.ocr(img, cls=True) returns nested list
    PaddleOCR 3.x: ocr.ocr(img) or ocr.predict(img) returns result objects
    
    Returns:
        List in PaddleOCR 2.x format: [[[box_coords, (text, confidence)], ...]]
    """
    version = _detect_paddleocr_version()
    is_v3 = version[0] >= 3
    
    if is_v3:
        # PaddleOCR 3.x API
        # The `cls` parameter was removed in 3.x
        try:
            result = ocr.ocr(img)
        except TypeError:
            # If ocr() doesn't work, try predict() (new 3.x interface)
            try:
                result = ocr.predict(img)
            except Exception:
                result = ocr.ocr(img)
        
        # PaddleOCR 3.x may return result objects instead of raw lists
        # Convert to 2.x format if needed
        if result and hasattr(result[0], 'rec_texts'):
            # This is a 3.x result object, convert to 2.x format
            converted = []
            res = result[0]
            boxes = getattr(res, 'dt_polys', [])
            texts = getattr(res, 'rec_texts', [])
            scores = getattr(res, 'rec_scores', [])
            
            for i, (box, text, score) in enumerate(zip(boxes, texts, scores)):
                converted.append([box.tolist() if hasattr(box, 'tolist') else box, (text, float(score))])
            
            return [converted] if converted else [[]]
        
        return result
    else:
        # PaddleOCR 2.x API
        return ocr.ocr(img, cls=True)


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
        
        # Run OCR with version-aware API
        result = _run_ocr_inference(ocr, img)
        
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
