"""
Camber CPU Worker Processors Package.

This package contains all image processing modules:
- quality: CPU-only quality assessment
- ocr: PaddleOCR text extraction
- enhancement: Image enhancement (denoise, color, orientation)
- schema: Schema adaptation (resize, DPI, compression)
"""

from processors.quality import assess_quality, check_quality_warning, QualityResult
from processors.ocr import extract_text, extract_text_safe, OCRResult
from processors.enhancement import enhance_image, EnhancementResult
from processors.schema import adapt_to_schema, SchemaResult

__all__ = [
    # Quality
    'assess_quality',
    'check_quality_warning',
    'QualityResult',
    # OCR
    'extract_text',
    'extract_text_safe',
    'OCRResult',
    # Enhancement
    'enhance_image',
    'EnhancementResult',
    # Schema
    'adapt_to_schema',
    'SchemaResult',
]
