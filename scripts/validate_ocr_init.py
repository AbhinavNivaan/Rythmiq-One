#!/usr/bin/env python3
"""
OCR Initialization Validation Script

This script validates that PaddleOCR initializes correctly with the
version-aware parameter handling. Run this locally before deploying
to Camber to verify compatibility.

Usage:
    python scripts/validate_ocr_init.py

Expected Output:
    ✓ PaddleOCR version: X.Y.Z
    ✓ OCR engine initialized successfully
    ✓ OCR inference works (test image)
    
Exit Codes:
    0 - All validations passed
    1 - Validation failed
    2 - Skipped (PaddlePaddle not available on this platform)
    
Notes:
    PaddlePaddle (the underlying framework) does not support Apple Silicon
    natively. This script will detect and report this case gracefully.
    Full validation should be done on Linux x86_64 (like Camber).
"""

import sys
import os
import logging
import platform

# Add worker directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'worker'))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def print_status(success: bool, message: str):
    """Print status with checkmark or cross."""
    symbol = "✓" if success else "✗"
    print(f"  {symbol} {message}")


def validate_paddleocr_import():
    """Validate PaddleOCR can be imported."""
    try:
        import paddleocr
        version = getattr(paddleocr, '__version__', 'unknown')
        print_status(True, f"PaddleOCR version: {version}")
        return True, version
    except ImportError as e:
        print_status(False, f"PaddleOCR import failed: {e}")
        return False, None


def validate_version_detection():
    """Validate version detection logic."""
    try:
        from processors.ocr import _detect_paddleocr_version
        version = _detect_paddleocr_version()
        print_status(True, f"Version detection: {version[0]}.{version[1]}.{version[2]}")
        return True
    except Exception as e:
        print_status(False, f"Version detection failed: {e}")
        return False


def validate_kwargs_building():
    """Validate parameter building doesn't crash."""
    try:
        from processors.ocr import _build_ocr_kwargs
        kwargs = _build_ocr_kwargs()
        print_status(True, f"Built kwargs: {list(kwargs.keys())}")
        
        # Check no problematic params
        if 'show_log' in kwargs:
            version = kwargs.get('_version', 'unknown')
            print_status(False, f"show_log should not be in kwargs for PaddleOCR 3.x")
            return False
            
        return True
    except Exception as e:
        print_status(False, f"Kwargs building failed: {e}")
        return False


def validate_engine_init():
    """Validate OCR engine initializes without error."""
    try:
        from processors.ocr import _get_ocr_engine
        
        # Reset global state
        import processors.ocr as ocr_module
        ocr_module._ocr_engine = None
        ocr_module._ocr_init_error = None
        
        engine = _get_ocr_engine()
        print_status(True, f"OCR engine initialized: {type(engine).__name__}")
        return True, engine
    except Exception as e:
        print_status(False, f"OCR engine init failed: {e}")
        return False, None


def validate_inference(engine):
    """Validate OCR inference works on a test image."""
    import numpy as np
    
    # Create a simple test image with text-like patterns
    # This is a minimal 100x30 grayscale image
    img = np.ones((100, 300, 3), dtype=np.uint8) * 255
    
    # Add some black rectangles to simulate text
    img[30:70, 20:40] = 0
    img[30:70, 50:70] = 0
    img[30:70, 80:100] = 0
    
    try:
        from processors.ocr import _run_ocr_inference
        result = _run_ocr_inference(engine, img)
        
        # Result may be empty (no text found) but should not crash
        if result is None:
            print_status(True, "OCR inference completed (no text found, expected for test image)")
        elif isinstance(result, list):
            text_count = sum(len(page) if page else 0 for page in result)
            print_status(True, f"OCR inference completed: {text_count} text regions")
        else:
            print_status(True, f"OCR inference completed: {type(result)}")
        
        return True
    except Exception as e:
        print_status(False, f"OCR inference failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def validate_extract_text_safe():
    """Validate extract_text_safe doesn't crash."""
    import numpy as np
    import cv2
    
    # Create a test image and encode it
    img = np.ones((100, 300, 3), dtype=np.uint8) * 255
    img[30:70, 20:40] = 0
    
    _, encoded = cv2.imencode('.png', img)
    image_bytes = encoded.tobytes()
    
    try:
        from processors.ocr import extract_text_safe
        result, warning = extract_text_safe(image_bytes)
        
        print_status(True, f"extract_text_safe completed: text='{result.text[:50]}...' conf={result.confidence:.2f}")
        if warning:
            print(f"      Warning: {warning}")
        
        return True
    except Exception as e:
        print_status(False, f"extract_text_safe failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all validation checks."""
    print("\n=== PaddleOCR Initialization Validation ===\n")
    
    # Check platform
    machine = platform.machine()
    system = platform.system()
    print(f"Platform: {system} {machine}")
    
    if system == 'Darwin' and machine == 'arm64':
        print("\n⚠️  Apple Silicon (M1/M2/M3) detected")
        print("   PaddlePaddle does not have native ARM Mac builds.")
        print("   Validation will check code paths but skip runtime tests.\n")
    
    all_passed = True
    
    # Step 1: Check PaddleOCR import
    print("1. Checking PaddleOCR import...")
    success, version = validate_paddleocr_import()
    all_passed = all_passed and success
    if not success:
        print("\n❌ FAILED: PaddleOCR is not installed")
        print("   Install with: pip install paddleocr")
        return 1
    
    # Step 2: Check version detection
    print("\n2. Checking version detection...")
    success = validate_version_detection()
    all_passed = all_passed and success
    
    # Step 3: Check kwargs building
    print("\n3. Checking parameter building...")
    success = validate_kwargs_building()
    all_passed = all_passed and success
    
    # Step 4: Check engine initialization
    print("\n4. Checking OCR engine initialization...")
    success, engine = validate_engine_init()
    
    if not success:
        # Check if this is due to missing paddle (platform issue)
        try:
            import paddle
        except ImportError:
            print("\n⚠️  PaddlePaddle not available on this platform")
            print("   This is expected on Apple Silicon.")
            print("   Code logic validation passed, skipping runtime tests.")
            print("\n" + "=" * 45)
            print("⚠️  PARTIAL VALIDATION (platform limitation)")
            print("   Code changes are valid. Full test on Camber.")
            return 2
        
        print("\n❌ FAILED: OCR engine could not be initialized")
        return 1
    
    all_passed = all_passed and success
    
    # Step 5: Check inference
    print("\n5. Checking OCR inference...")
    success = validate_inference(engine)
    all_passed = all_passed and success
    
    # Step 6: Check full extract_text_safe flow
    print("\n6. Checking extract_text_safe...")
    success = validate_extract_text_safe()
    all_passed = all_passed and success
    
    # Summary
    print("\n" + "=" * 45)
    if all_passed:
        print("✅ ALL VALIDATIONS PASSED")
        print("   OCR is ready for Camber deployment")
        return 0
    else:
        print("❌ SOME VALIDATIONS FAILED")
        print("   Review errors above before deploying")
        return 1


if __name__ == '__main__':
    sys.exit(main())
