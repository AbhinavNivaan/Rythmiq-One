"""
Camber CPU Worker Processors Package.

This package contains all image processing modules:
- quality: CPU-only quality assessment
- document_ai: Google Cloud Document AI OCR (primary)
- ocr: PaddleOCR text extraction (legacy fallback)
- enhancement: Image enhancement (denoise, color, orientation)
- schema: Schema adaptation (resize, DPI, compression)
"""

from processors.quality import assess_quality, check_quality_warning, QualityResult
from processors.document_ai import extract_text_safe as docai_extract_text, DocumentAIResult
from processors.enhancement import enhance_image, EnhancementResult
from processors.schema import adapt_to_schema, SchemaResult
from processors.vision_crop import get_crop_corners

__all__ = [
    # Quality
    'assess_quality',
    'check_quality_warning',
    'QualityResult',
    # OCR (Document AI)
    'docai_extract_text',
    'DocumentAIResult',
    # Enhancement
    'enhance_image',
    'EnhancementResult',
    # Schema
    'adapt_to_schema',
    'SchemaResult',
    # Vision crop
    'get_crop_corners',
]
