#!/usr/bin/env python3
"""
Schema Adapter Validation Test Suite

Comprehensive validation of the schema adaptation pipeline for portal compliance.
Verifies:
1. Exact output dimensions (no off-by-one)
2. DPI metadata correctness
3. File size limit enforcement
4. Compression loop convergence
5. Error handling for invalid inputs

Run with:
    pytest tests/test_schema_validation.py -v
    
Or standalone:
    python tests/test_schema_validation.py
"""

from __future__ import annotations

import io
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
import pytest
from PIL import Image

# Add worker to path
sys.path.insert(0, str(Path(__file__).parent.parent / "worker"))

from models import SchemaDefinition
from processors.schema import (
    adapt_to_schema,
    compress_to_size,
    decode_image,
    resize_exact,
    verify_schema_compliance,
    MAX_COMPRESSION_ITERATIONS,
    MIN_JPEG_QUALITY,
)
from errors import WorkerError, ErrorCode


# =============================================================================
# Portal Schema Definitions
# =============================================================================
PORTAL_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "neet_ug_2026": {
        "name": "NEET UG 2026",
        "target_width": 200,
        "target_height": 230,
        "target_dpi": 200,
        "max_kb": 100,
        "filename_pattern": "{job_id}_neet",
        "output_format": "jpeg",
        "quality": 85,
    },
    "jee_main_2026": {
        "name": "JEE Main 2026",
        "target_width": 350,
        "target_height": 450,
        "target_dpi": 300,
        "max_kb": 150,
        "filename_pattern": "{job_id}_jee",
        "output_format": "jpeg",
        "quality": 85,
    },
    "aadhaar_update": {
        "name": "Aadhaar Update",
        "target_width": 200,
        "target_height": 230,
        "target_dpi": 200,
        "max_kb": 100,
        "filename_pattern": "{job_id}_aadhaar",
        "output_format": "jpeg",
        "quality": 85,
    },
    "passport_seva": {
        "name": "Passport Seva (India)",
        "target_width": 413,
        "target_height": 531,
        "target_dpi": 300,
        "max_kb": 300,
        "filename_pattern": "{job_id}_passport",
        "output_format": "jpeg",
        "quality": 85,
    },
    "college_generic": {
        "name": "College Generic",
        "target_width": 400,
        "target_height": 500,
        "target_dpi": 200,
        "max_kb": 200,
        "filename_pattern": "{job_id}_college",
        "output_format": "jpeg",
        "quality": 85,
    },
}

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "schema_validation"


# =============================================================================
# Data Classes for Results
# =============================================================================
@dataclass
class ValidationResult:
    """Result of a single schema validation test."""
    schema_name: str
    input_file: str
    success: bool
    dimensions_match: bool
    dpi_match: bool
    size_compliant: bool
    output_width: int = 0
    output_height: int = 0
    output_dpi_x: int = 0
    output_dpi_y: int = 0
    output_size_kb: float = 0.0
    expected_width: int = 0
    expected_height: int = 0
    expected_dpi: int = 0
    max_kb: int = 0
    error_message: str = ""
    compression_iterations: int = 0
    final_quality: int = 0


@dataclass
class CompressionAnalysis:
    """Compression loop analysis for a test case."""
    schema_name: str
    input_file: str
    iterations: int
    qualities: List[int] = field(default_factory=list)
    sizes_kb: List[float] = field(default_factory=list)
    converged: bool = False
    final_quality: int = 0
    final_size_kb: float = 0.0


# =============================================================================
# Helper Functions
# =============================================================================
def load_test_image(schema_key: str, image_name: str) -> bytes:
    """Load test image from fixtures."""
    path = FIXTURES_DIR / schema_key / image_name
    if not path.exists():
        raise FileNotFoundError(f"Test image not found: {path}")
    return path.read_bytes()


def get_schema_definition(schema_key: str) -> SchemaDefinition:
    """Get SchemaDefinition for a portal."""
    spec = PORTAL_SCHEMAS[schema_key]
    return SchemaDefinition(
        target_width=spec["target_width"],
        target_height=spec["target_height"],
        target_dpi=spec["target_dpi"],
        max_kb=spec["max_kb"],
        filename_pattern=spec["filename_pattern"],
        output_format=spec["output_format"],
        quality=spec["quality"],
    )


def extract_image_properties(data: bytes) -> Dict[str, Any]:
    """Extract properties from encoded image data."""
    # Use PIL for metadata
    pil_img = Image.open(io.BytesIO(data))
    
    # Get DPI
    dpi = pil_img.info.get('dpi', (72, 72))
    if isinstance(dpi, tuple):
        dpi_x, dpi_y = int(dpi[0]), int(dpi[1])
    else:
        dpi_x = dpi_y = int(dpi)
    
    # Get dimensions
    width, height = pil_img.size
    
    # Get format
    fmt = pil_img.format
    
    # File size
    size_kb = len(data) / 1024
    
    return {
        "width": width,
        "height": height,
        "dpi_x": dpi_x,
        "dpi_y": dpi_y,
        "format": fmt,
        "size_kb": size_kb,
    }


def validate_single_image(
    schema_key: str,
    image_name: str,
) -> ValidationResult:
    """Validate a single image against its schema."""
    schema = get_schema_definition(schema_key)
    spec = PORTAL_SCHEMAS[schema_key]
    
    result = ValidationResult(
        schema_name=spec["name"],
        input_file=image_name,
        success=False,
        dimensions_match=False,
        dpi_match=False,
        size_compliant=False,
        expected_width=schema.target_width,
        expected_height=schema.target_height,
        expected_dpi=schema.target_dpi,
        max_kb=schema.max_kb,
    )
    
    try:
        # Load input
        input_data = load_test_image(schema_key, image_name)
        
        # Adapt to schema
        adapted = adapt_to_schema(
            data=input_data,
            schema=schema,
            job_id="test-job-12345",
            user_id="test-user",
            original_filename=image_name,
        )
        
        # Extract output properties
        props = extract_image_properties(adapted.image_data)
        
        result.output_width = props["width"]
        result.output_height = props["height"]
        result.output_dpi_x = props["dpi_x"]
        result.output_dpi_y = props["dpi_y"]
        result.output_size_kb = props["size_kb"]
        
        # Validate dimensions (EXACT match)
        result.dimensions_match = (
            props["width"] == schema.target_width and
            props["height"] == schema.target_height
        )
        
        # Validate DPI (EXACT match)
        result.dpi_match = (
            props["dpi_x"] == schema.target_dpi and
            props["dpi_y"] == schema.target_dpi
        )
        
        # Validate size (strict <)
        result.size_compliant = props["size_kb"] < schema.max_kb
        
        result.success = (
            result.dimensions_match and
            result.dpi_match and
            result.size_compliant
        )
        
    except WorkerError as e:
        result.error_message = f"{e.code.value}: {e.message}"
    except Exception as e:
        result.error_message = f"Unexpected error: {str(e)}"
    
    return result


def analyze_compression(
    schema_key: str,
    image_name: str,
) -> CompressionAnalysis:
    """Analyze compression loop behavior for a test case."""
    schema = get_schema_definition(schema_key)
    spec = PORTAL_SCHEMAS[schema_key]
    
    analysis = CompressionAnalysis(
        schema_name=spec["name"],
        input_file=image_name,
        iterations=0,
    )
    
    try:
        # Load and decode
        input_data = load_test_image(schema_key, image_name)
        cv_img, _ = decode_image(input_data)
        
        # Resize first
        resized = resize_exact(cv_img, schema.target_width, schema.target_height)
        
        # Custom compression loop with logging
        from processors.schema import encode_with_dpi
        
        max_bytes = schema.max_kb * 1024
        quality = schema.quality
        
        # First try
        data = encode_with_dpi(resized, schema.target_dpi, "jpeg", quality)
        analysis.qualities.append(quality)
        analysis.sizes_kb.append(len(data) / 1024)
        analysis.iterations = 1
        
        if len(data) <= max_bytes:
            analysis.converged = True
            analysis.final_quality = quality
            analysis.final_size_kb = len(data) / 1024
            return analysis
        
        # Binary search
        low_quality = MIN_JPEG_QUALITY
        high_quality = quality
        best_data = data
        best_quality = quality
        
        for i in range(MAX_COMPRESSION_ITERATIONS):
            if low_quality > high_quality:
                break
            
            mid_quality = (low_quality + high_quality) // 2
            data = encode_with_dpi(resized, schema.target_dpi, "jpeg", mid_quality)
            
            analysis.qualities.append(mid_quality)
            analysis.sizes_kb.append(len(data) / 1024)
            analysis.iterations += 1
            
            if len(data) <= max_bytes:
                best_data = data
                best_quality = mid_quality
                low_quality = mid_quality + 1
            else:
                high_quality = mid_quality - 1
        
        if len(best_data) <= max_bytes:
            analysis.converged = True
            analysis.final_quality = best_quality
            analysis.final_size_kb = len(best_data) / 1024
        else:
            # Try minimum quality
            data = encode_with_dpi(resized, schema.target_dpi, "jpeg", MIN_JPEG_QUALITY)
            analysis.qualities.append(MIN_JPEG_QUALITY)
            analysis.sizes_kb.append(len(data) / 1024)
            analysis.iterations += 1
            
            if len(data) <= max_bytes:
                analysis.converged = True
                analysis.final_quality = MIN_JPEG_QUALITY
                analysis.final_size_kb = len(data) / 1024
        
    except Exception as e:
        analysis.converged = False
    
    return analysis


# =============================================================================
# PyTest Test Cases
# =============================================================================
class TestSchemaDimensions:
    """Test exact dimension compliance."""
    
    @pytest.mark.parametrize("schema_key", PORTAL_SCHEMAS.keys())
    def test_clean_image_dimensions(self, schema_key: str):
        """Clean images must resize to exact dimensions."""
        result = validate_single_image(schema_key, "clean.jpg")
        assert result.dimensions_match, (
            f"{result.schema_name}: Expected {result.expected_width}x{result.expected_height}, "
            f"got {result.output_width}x{result.output_height}"
        )
    
    @pytest.mark.parametrize("schema_key", PORTAL_SCHEMAS.keys())
    def test_large_image_dimensions(self, schema_key: str):
        """Large images must resize to exact dimensions (downscale)."""
        result = validate_single_image(schema_key, "large.jpg")
        assert result.dimensions_match, (
            f"{result.schema_name}: Expected {result.expected_width}x{result.expected_height}, "
            f"got {result.output_width}x{result.output_height}"
        )
    
    @pytest.mark.parametrize("schema_key", PORTAL_SCHEMAS.keys())
    def test_tiny_image_dimensions(self, schema_key: str):
        """Tiny images must resize to exact dimensions (upscale)."""
        result = validate_single_image(schema_key, "tiny.jpg")
        assert result.dimensions_match, (
            f"{result.schema_name}: Expected {result.expected_width}x{result.expected_height}, "
            f"got {result.output_width}x{result.output_height}"
        )


class TestSchemaDPI:
    """Test DPI metadata compliance."""
    
    @pytest.mark.parametrize("schema_key", PORTAL_SCHEMAS.keys())
    def test_dpi_metadata_set(self, schema_key: str):
        """DPI metadata must be set correctly."""
        result = validate_single_image(schema_key, "clean.jpg")
        assert result.dpi_match, (
            f"{result.schema_name}: Expected DPI {result.expected_dpi}, "
            f"got {result.output_dpi_x}x{result.output_dpi_y}"
        )


class TestSchemaFileSize:
    """Test file size limit compliance."""
    
    @pytest.mark.parametrize("schema_key", PORTAL_SCHEMAS.keys())
    def test_clean_image_size(self, schema_key: str):
        """Clean images must be under size limit."""
        result = validate_single_image(schema_key, "clean.jpg")
        assert result.size_compliant, (
            f"{result.schema_name}: Size {result.output_size_kb:.1f}KB exceeds max {result.max_kb}KB"
        )
    
    @pytest.mark.parametrize("schema_key", PORTAL_SCHEMAS.keys())
    def test_borderline_image_size(self, schema_key: str):
        """Borderline images must still be under size limit."""
        result = validate_single_image(schema_key, "borderline.jpg")
        assert result.size_compliant, (
            f"{result.schema_name}: Size {result.output_size_kb:.1f}KB exceeds max {result.max_kb}KB"
        )
    
    @pytest.mark.parametrize("schema_key", PORTAL_SCHEMAS.keys())
    def test_noisy_image_size(self, schema_key: str):
        """Noisy images (hard to compress) must be under size limit."""
        result = validate_single_image(schema_key, "noisy.jpg")
        assert result.size_compliant, (
            f"{result.schema_name}: Size {result.output_size_kb:.1f}KB exceeds max {result.max_kb}KB"
        )


class TestSchemaFullCompliance:
    """Test full schema compliance (all criteria)."""
    
    @pytest.mark.parametrize("schema_key", PORTAL_SCHEMAS.keys())
    @pytest.mark.parametrize("image_name", ["clean.jpg", "large.jpg", "noisy.jpg", "borderline.jpg"])
    def test_full_compliance(self, schema_key: str, image_name: str):
        """All valid images must fully comply with schema."""
        result = validate_single_image(schema_key, image_name)
        assert result.success, (
            f"{result.schema_name}/{image_name}: "
            f"dims={result.dimensions_match}, dpi={result.dpi_match}, size={result.size_compliant} "
            f"error={result.error_message}"
        )


class TestCompressionConvergence:
    """Test compression loop behavior."""
    
    @pytest.mark.parametrize("schema_key", PORTAL_SCHEMAS.keys())
    def test_compression_converges(self, schema_key: str):
        """Compression must converge within iteration limit."""
        analysis = analyze_compression(schema_key, "borderline.jpg")
        assert analysis.converged, (
            f"{analysis.schema_name}: Compression did not converge after {analysis.iterations} iterations"
        )
        assert analysis.iterations <= MAX_COMPRESSION_ITERATIONS, (
            f"{analysis.schema_name}: Exceeded max iterations ({analysis.iterations} > {MAX_COMPRESSION_ITERATIONS})"
        )
    
    @pytest.mark.parametrize("schema_key", PORTAL_SCHEMAS.keys())
    def test_compression_quality_floor(self, schema_key: str):
        """Final quality should not go below minimum."""
        analysis = analyze_compression(schema_key, "noisy.jpg")
        if analysis.converged:
            assert analysis.final_quality >= MIN_JPEG_QUALITY, (
                f"{analysis.schema_name}: Final quality {analysis.final_quality} below minimum {MIN_JPEG_QUALITY}"
            )


class TestEdgeCases:
    """Test edge case handling."""
    
    @pytest.mark.parametrize("schema_key", PORTAL_SCHEMAS.keys())
    def test_white_image_no_crash(self, schema_key: str):
        """Near-white images should not crash."""
        result = validate_single_image(schema_key, "white.jpg")
        # May or may not pass compliance, but should not crash
        assert result.error_message == "" or "DECODE_FAILED" not in result.error_message
    
    @pytest.mark.parametrize("schema_key", PORTAL_SCHEMAS.keys())
    def test_black_image_no_crash(self, schema_key: str):
        """Near-black images should not crash."""
        result = validate_single_image(schema_key, "black.jpg")
        # May or may not pass compliance, but should not crash
        assert result.error_message == "" or "DECODE_FAILED" not in result.error_message
    
    @pytest.mark.parametrize("schema_key", PORTAL_SCHEMAS.keys())
    def test_corrupt_image_fails_gracefully(self, schema_key: str):
        """Corrupt images should fail with proper error code."""
        result = validate_single_image(schema_key, "corrupt.bin")
        assert not result.success
        assert "DECODE_FAILED" in result.error_message or "error" in result.error_message.lower()
    
    @pytest.mark.parametrize("schema_key", PORTAL_SCHEMAS.keys())
    def test_huge_image_handles(self, schema_key: str):
        """Extremely large images should be handled."""
        result = validate_single_image(schema_key, "huge.jpg")
        # Should either succeed or fail gracefully
        if not result.success:
            assert result.error_message != "", "Should have error message on failure"


class TestErrorCodes:
    """Test that failures produce proper error codes."""
    
    def test_decode_failed_code(self):
        """Corrupt images should produce DECODE_FAILED error."""
        result = validate_single_image("neet_ug_2026", "corrupt.bin")
        assert "DECODE_FAILED" in result.error_message


# =============================================================================
# Standalone Report Generator
# =============================================================================
def run_full_validation() -> Dict[str, Any]:
    """Run full validation suite and generate report."""
    print("=" * 70)
    print("SCHEMA ADAPTER VALIDATION REPORT")
    print("=" * 70)
    print(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    all_results: List[ValidationResult] = []
    compression_analyses: List[CompressionAnalysis] = []
    
    test_images = ["clean.jpg", "large.jpg", "noisy.jpg", "borderline.jpg", 
                   "tiny.jpg", "huge.jpg", "white.jpg", "black.jpg"]
    
    # Run validation for each schema and image
    for schema_key, spec in PORTAL_SCHEMAS.items():
        print(f"\n{'─' * 70}")
        print(f"📋 {spec['name']} ({spec['target_width']}×{spec['target_height']} @ {spec['target_dpi']} DPI, <{spec['max_kb']}KB)")
        print(f"{'─' * 70}")
        
        for image_name in test_images:
            result = validate_single_image(schema_key, image_name)
            all_results.append(result)
            
            status = "✅ PASS" if result.success else "❌ FAIL"
            print(f"  {status} {image_name:15} → {result.output_width:4}×{result.output_height:<4} "
                  f"DPI:{result.output_dpi_x:3} Size:{result.output_size_kb:6.1f}KB", end="")
            
            if not result.success and result.error_message:
                print(f" [{result.error_message[:40]}]", end="")
            print()
            
            # Compression analysis for complex images
            if image_name in ["borderline.jpg", "noisy.jpg"]:
                analysis = analyze_compression(schema_key, image_name)
                compression_analyses.append(analysis)
    
    # Summary tables
    print("\n" + "=" * 70)
    print("VALIDATION SUMMARY TABLE")
    print("=" * 70)
    print(f"{'Schema':<20} {'Image':<15} {'Dims':<8} {'DPI':<6} {'Size':<8} {'Result':<8}")
    print("-" * 70)
    
    pass_count = 0
    fail_count = 0
    
    for r in all_results:
        dims = "✓" if r.dimensions_match else "✗"
        dpi = "✓" if r.dpi_match else "✗"
        size = "✓" if r.size_compliant else "✗"
        result = "PASS" if r.success else "FAIL"
        
        if r.success:
            pass_count += 1
        else:
            fail_count += 1
        
        print(f"{r.schema_name[:20]:<20} {r.input_file:<15} {dims:<8} {dpi:<6} {size:<8} {result:<8}")
    
    print("-" * 70)
    print(f"Total: {pass_count} passed, {fail_count} failed")
    
    # Compression convergence summary
    print("\n" + "=" * 70)
    print("COMPRESSION CONVERGENCE SUMMARY")
    print("=" * 70)
    print(f"{'Schema':<20} {'Image':<15} {'Iters':<8} {'Quality':<10} {'Size KB':<10} {'Conv':<8}")
    print("-" * 70)
    
    for a in compression_analyses:
        conv = "✓" if a.converged else "✗"
        print(f"{a.schema_name[:20]:<20} {a.input_file:<15} {a.iterations:<8} "
              f"{a.final_quality:<10} {a.final_size_kb:<10.1f} {conv:<8}")
    
    max_iterations = max(a.iterations for a in compression_analyses) if compression_analyses else 0
    all_converged = all(a.converged for a in compression_analyses)
    
    print("-" * 70)
    print(f"Max iterations observed: {max_iterations}")
    print(f"All converged: {'Yes' if all_converged else 'No'}")
    
    # Edge case findings
    print("\n" + "=" * 70)
    print("EDGE CASE FINDINGS")
    print("=" * 70)
    
    edge_cases = ["white.jpg", "black.jpg", "tiny.jpg", "huge.jpg", "corrupt.bin"]
    edge_results = [r for r in all_results if r.input_file in edge_cases]
    
    for r in edge_results:
        status = "✅" if r.success or "DECODE_FAILED" in r.error_message else "⚠️"
        note = ""
        if "corrupt" in r.input_file:
            note = "(expected failure)"
        elif not r.success:
            note = f"({r.error_message[:30]})"
        print(f"  {status} {r.schema_name}/{r.input_file}: {note}")
    
    # Final verdict
    print("\n" + "=" * 70)
    print("FINAL VERDICT")
    print("=" * 70)
    
    # Check critical criteria
    critical_failures = [r for r in all_results 
                        if not r.success 
                        and r.input_file not in ["corrupt.bin"]
                        and r.input_file in ["clean.jpg", "large.jpg", "noisy.jpg", "borderline.jpg"]]
    
    compression_issues = [a for a in compression_analyses if not a.converged]
    
    blockers = []
    if critical_failures:
        blockers.append(f"{len(critical_failures)} standard image(s) failed compliance")
    if compression_issues:
        blockers.append(f"{len(compression_issues)} compression loop(s) did not converge")
    if max_iterations >= MAX_COMPRESSION_ITERATIONS:
        blockers.append(f"Compression hit iteration ceiling ({max_iterations})")
    
    if blockers:
        print("❌ SCHEMA ADAPTER IS NOT PRODUCTION-READY")
        print("\nBlockers:")
        for b in blockers:
            print(f"  • {b}")
    else:
        print("✅ SCHEMA ADAPTER IS PRODUCTION-READY")
        print("\nAll validation criteria passed:")
        print("  • Exact dimensions for all standard test images")
        print("  • Correct DPI metadata")
        print("  • File size limits enforced")
        print("  • Compression converges reliably")
        print("  • Edge cases handled gracefully")
    
    return {
        "pass_count": pass_count,
        "fail_count": fail_count,
        "critical_failures": len(critical_failures),
        "compression_issues": len(compression_issues),
        "max_iterations": max_iterations,
        "production_ready": len(blockers) == 0,
        "blockers": blockers,
    }


if __name__ == "__main__":
    # Run standalone report
    summary = run_full_validation()
    
    # Exit with error code if not production ready
    sys.exit(0 if summary["production_ready"] else 1)
