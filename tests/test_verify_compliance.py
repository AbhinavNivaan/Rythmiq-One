#!/usr/bin/env python3
"""
Test for verify_schema_compliance function.

Verifies that the compliance verification catches:
- Dimension mismatches
- DPI mismatches
- Size violations
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

# Add worker to path
sys.path.insert(0, str(Path(__file__).parent.parent / "worker"))

from models import SchemaDefinition
from processors.schema import verify_schema_compliance, encode_with_dpi


def create_test_image(width: int, height: int, dpi: int, size_factor: float = 1.0) -> bytes:
    """Create a test image with specific dimensions and DPI."""
    # Create simple gradient image
    img = np.zeros((height, width, 3), dtype=np.uint8)
    for c in range(3):
        gradient = np.linspace(0, 255, width, dtype=np.uint8)
        img[:, :, c] = np.tile(gradient, (height, 1))
    
    # Encode with DPI
    quality = int(85 * size_factor)  # Adjust quality to affect size
    return encode_with_dpi(img, dpi, "jpeg", quality)


def test_verify_correct_image():
    """Test that correct images pass verification."""
    print("TEST 1: Correct image passes verification")
    print("-" * 50)
    
    schema = SchemaDefinition(
        target_width=200,
        target_height=230,
        target_dpi=200,
        max_kb=100,
        filename_pattern="{job_id}",
    )
    
    data = create_test_image(200, 230, 200)
    compliant, error = verify_schema_compliance(data, schema)
    
    print(f"  Compliant: {compliant}")
    if not compliant:
        print(f"  Error: {error}")
    assert compliant, f"Should be compliant but got: {error}"
    print("  ✓ PASS")


def test_verify_wrong_width():
    """Test that wrong width is detected."""
    print("\nTEST 2: Wrong width detected")
    print("-" * 50)
    
    schema = SchemaDefinition(
        target_width=200,
        target_height=230,
        target_dpi=200,
        max_kb=100,
        filename_pattern="{job_id}",
    )
    
    data = create_test_image(199, 230, 200)  # Off by one!
    compliant, error = verify_schema_compliance(data, schema)
    
    print(f"  Compliant: {compliant}")
    print(f"  Error: {error}")
    assert not compliant, "Should detect width mismatch"
    assert "Width" in error
    print("  ✓ PASS")


def test_verify_wrong_height():
    """Test that wrong height is detected."""
    print("\nTEST 3: Wrong height detected")
    print("-" * 50)
    
    schema = SchemaDefinition(
        target_width=200,
        target_height=230,
        target_dpi=200,
        max_kb=100,
        filename_pattern="{job_id}",
    )
    
    data = create_test_image(200, 231, 200)  # Off by one!
    compliant, error = verify_schema_compliance(data, schema)
    
    print(f"  Compliant: {compliant}")
    print(f"  Error: {error}")
    assert not compliant, "Should detect height mismatch"
    assert "Height" in error
    print("  ✓ PASS")


def test_verify_wrong_dpi():
    """Test that wrong DPI is detected."""
    print("\nTEST 4: Wrong DPI detected")
    print("-" * 50)
    
    schema = SchemaDefinition(
        target_width=200,
        target_height=230,
        target_dpi=200,
        max_kb=100,
        filename_pattern="{job_id}",
    )
    
    data = create_test_image(200, 230, 72)  # Wrong DPI!
    compliant, error = verify_schema_compliance(data, schema)
    
    print(f"  Compliant: {compliant}")
    print(f"  Error: {error}")
    assert not compliant, "Should detect DPI mismatch"
    assert "DPI" in error
    print("  ✓ PASS")


def test_verify_size_exceeded():
    """Test that size violation is detected."""
    print("\nTEST 5: Size exceeded detected")
    print("-" * 50)
    
    schema = SchemaDefinition(
        target_width=400,
        target_height=500,
        target_dpi=200,
        max_kb=1,  # Impossibly small
        filename_pattern="{job_id}",
    )
    
    # Create a larger image that won't fit in 1KB
    img = np.random.randint(0, 256, (500, 400, 3), dtype=np.uint8)
    data = encode_with_dpi(img, 200, "jpeg", 95)
    
    compliant, error = verify_schema_compliance(data, schema)
    
    print(f"  Compliant: {compliant}")
    print(f"  Error: {error}")
    print(f"  Actual size: {len(data) / 1024:.1f}KB")
    assert not compliant, "Should detect size exceeded"
    assert "Size" in error or "exceeds" in error
    print("  ✓ PASS")


def test_all_portal_schemas():
    """Test verification for all seeded portal schemas."""
    print("\nTEST 6: All portal schemas verify correctly")
    print("-" * 50)
    
    schemas = {
        "NEET UG 2026": SchemaDefinition(200, 230, 200, 100, "{job_id}"),
        "JEE Main 2026": SchemaDefinition(350, 450, 300, 150, "{job_id}"),
        "Aadhaar Update": SchemaDefinition(200, 230, 200, 100, "{job_id}"),
        "Passport Seva": SchemaDefinition(413, 531, 300, 300, "{job_id}"),
        "College Generic": SchemaDefinition(400, 500, 200, 200, "{job_id}"),
    }
    
    all_pass = True
    for name, schema in schemas.items():
        data = create_test_image(schema.target_width, schema.target_height, schema.target_dpi)
        compliant, error = verify_schema_compliance(data, schema)
        status = "✓" if compliant else "✗"
        print(f"  {status} {name}: {compliant}")
        if not compliant:
            print(f"      Error: {error}")
            all_pass = False
    
    assert all_pass, "All schemas should verify correctly"
    print("  ✓ PASS")


def main():
    print("=" * 60)
    print("VERIFY_SCHEMA_COMPLIANCE FUNCTION TESTS")
    print("=" * 60)
    
    test_verify_correct_image()
    test_verify_wrong_width()
    test_verify_wrong_height()
    test_verify_wrong_dpi()
    test_verify_size_exceeded()
    test_all_portal_schemas()
    
    print("\n" + "=" * 60)
    print("✓ ALL VERIFICATION TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()
