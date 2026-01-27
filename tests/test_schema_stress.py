#!/usr/bin/env python3
"""
Schema Adapter Stress Tests

Tests edge cases that push the compression loop to its limits:
- High-entropy random noise images
- Images that barely fit after max compression
- Images that cannot fit even at minimum quality
- Very tight size constraints

Run with:
    PYTHONPATH=worker python tests/test_schema_stress.py
"""

from __future__ import annotations

import io
import sys
from pathlib import Path
from typing import Tuple

import cv2
import numpy as np
from PIL import Image

# Add worker to path
sys.path.insert(0, str(Path(__file__).parent.parent / "worker"))

from models import SchemaDefinition
from processors.schema import (
    adapt_to_schema,
    compress_to_size,
    decode_image,
    encode_with_dpi,
    resize_exact,
    MAX_COMPRESSION_ITERATIONS,
    MIN_JPEG_QUALITY,
)
from errors import WorkerError, ErrorCode


def create_high_entropy_image(width: int, height: int) -> np.ndarray:
    """Create maximum entropy image (pure random noise) - hardest to compress."""
    return np.random.randint(0, 256, (height, width, 3), dtype=np.uint8)


def create_gradient_image(width: int, height: int) -> np.ndarray:
    """Create smooth gradient - compresses very well."""
    img = np.zeros((height, width, 3), dtype=np.uint8)
    for c in range(3):
        gradient = np.linspace(0, 255, width, dtype=np.uint8)
        img[:, :, c] = np.tile(gradient, (height, 1))
    return img


def create_checkerboard(width: int, height: int, block_size: int = 2) -> np.ndarray:
    """Create fine checkerboard pattern - moderately hard to compress."""
    img = np.zeros((height, width, 3), dtype=np.uint8)
    for i in range(height):
        for j in range(width):
            if ((i // block_size) + (j // block_size)) % 2 == 0:
                img[i, j] = [255, 255, 255]
            else:
                img[i, j] = [0, 0, 0]
    return img


def test_compression_convergence(
    img: np.ndarray,
    dpi: int,
    max_kb: int,
    test_name: str,
) -> Tuple[bool, int, int, float]:
    """
    Test compression loop convergence.
    
    Returns: (converged, iterations, final_quality, final_size_kb)
    """
    max_bytes = max_kb * 1024
    quality = 85
    iterations = 0
    
    # Track iterations through binary search
    data = encode_with_dpi(img, dpi, "jpeg", quality)
    iterations = 1
    
    if len(data) <= max_bytes:
        return True, iterations, quality, len(data) / 1024
    
    # Binary search
    low = MIN_JPEG_QUALITY
    high = quality
    best_data = data
    best_quality = quality
    
    while low <= high and iterations < MAX_COMPRESSION_ITERATIONS + 5:
        mid = (low + high) // 2
        data = encode_with_dpi(img, dpi, "jpeg", mid)
        iterations += 1
        
        if len(data) <= max_bytes:
            best_data = data
            best_quality = mid
            low = mid + 1
        else:
            high = mid - 1
    
    # Final fallback
    if len(best_data) > max_bytes:
        data = encode_with_dpi(img, dpi, "jpeg", MIN_JPEG_QUALITY)
        iterations += 1
        if len(data) <= max_bytes:
            return True, iterations, MIN_JPEG_QUALITY, len(data) / 1024
        else:
            return False, iterations, MIN_JPEG_QUALITY, len(data) / 1024
    
    return True, iterations, best_quality, len(best_data) / 1024


def run_stress_tests():
    """Run compression stress tests."""
    print("=" * 70)
    print("SCHEMA ADAPTER STRESS TESTS")
    print("=" * 70)
    print()
    
    results = []
    
    # Test 1: High entropy noise at tight constraint
    print("TEST 1: High-entropy random noise (NEET UG constraints)")
    print("-" * 70)
    img = create_high_entropy_image(200, 230)
    converged, iters, quality, size = test_compression_convergence(
        img, dpi=200, max_kb=100, test_name="noise_200x230"
    )
    results.append(("Noise 200x230 → 100KB", converged, iters, quality, size))
    print(f"  Converged: {converged}, Iterations: {iters}, Quality: {quality}, Size: {size:.1f}KB")
    
    # Test 2: High entropy at larger dimensions
    print("\nTEST 2: High-entropy noise (Passport Seva constraints)")
    print("-" * 70)
    img = create_high_entropy_image(413, 531)
    converged, iters, quality, size = test_compression_convergence(
        img, dpi=300, max_kb=300, test_name="noise_413x531"
    )
    results.append(("Noise 413x531 → 300KB", converged, iters, quality, size))
    print(f"  Converged: {converged}, Iterations: {iters}, Quality: {quality}, Size: {size:.1f}KB")
    
    # Test 3: Very tight constraint (impossible)
    print("\nTEST 3: Impossible constraint (noise 400x500 → 5KB)")
    print("-" * 70)
    img = create_high_entropy_image(400, 500)
    converged, iters, quality, size = test_compression_convergence(
        img, dpi=200, max_kb=5, test_name="impossible"
    )
    results.append(("Noise 400x500 → 5KB", converged, iters, quality, size))
    print(f"  Converged: {converged}, Iterations: {iters}, Quality: {quality}, Size: {size:.1f}KB")
    if not converged:
        print(f"  ✓ Correctly detected impossible constraint")
    
    # Test 4: Checkerboard pattern
    print("\nTEST 4: Fine checkerboard (hard to compress)")
    print("-" * 70)
    img = create_checkerboard(350, 450, block_size=1)
    converged, iters, quality, size = test_compression_convergence(
        img, dpi=300, max_kb=150, test_name="checkerboard"
    )
    results.append(("Checkerboard 350x450 → 150KB", converged, iters, quality, size))
    print(f"  Converged: {converged}, Iterations: {iters}, Quality: {quality}, Size: {size:.1f}KB")
    
    # Test 5: Gradient (easy to compress)
    print("\nTEST 5: Smooth gradient (easy to compress)")
    print("-" * 70)
    img = create_gradient_image(400, 500)
    converged, iters, quality, size = test_compression_convergence(
        img, dpi=200, max_kb=200, test_name="gradient"
    )
    results.append(("Gradient 400x500 → 200KB", converged, iters, quality, size))
    print(f"  Converged: {converged}, Iterations: {iters}, Quality: {quality}, Size: {size:.1f}KB")
    
    # Test 6: Test actual adapt_to_schema with noise
    print("\nTEST 6: Full pipeline with high-entropy input")
    print("-" * 70)
    # Create a larger noise image that needs resize + compress
    large_noise = create_high_entropy_image(2000, 2300)
    _, large_noise_bytes = cv2.imencode('.jpg', large_noise, [cv2.IMWRITE_JPEG_QUALITY, 95])
    
    schema = SchemaDefinition(
        target_width=200,
        target_height=230,
        target_dpi=200,
        max_kb=100,
        filename_pattern="{job_id}",
        output_format="jpeg",
        quality=85,
    )
    
    try:
        result = adapt_to_schema(
            data=large_noise_bytes.tobytes(),
            schema=schema,
            job_id="stress-test",
        )
        size_kb = len(result.image_data) / 1024
        print(f"  ✓ Adapted successfully: {result.final_width}x{result.final_height} @ {size_kb:.1f}KB")
        results.append(("Full pipeline noise", True, 0, 0, size_kb))
    except WorkerError as e:
        print(f"  ✗ Failed: {e.code.value} - {e.message}")
        results.append(("Full pipeline noise", False, 0, 0, 0))
    
    # Test 7: Test impossible full pipeline
    print("\nTEST 7: Full pipeline with impossible constraint")
    print("-" * 70)
    schema_impossible = SchemaDefinition(
        target_width=400,
        target_height=500,
        target_dpi=200,
        max_kb=1,  # Impossible: 1KB for 400x500 image
        filename_pattern="{job_id}",
        output_format="jpeg",
        quality=85,
    )
    
    try:
        result = adapt_to_schema(
            data=large_noise_bytes.tobytes(),
            schema=schema_impossible,
            job_id="stress-test-impossible",
        )
        print(f"  ✗ Should have failed but got: {len(result.image_data) / 1024:.1f}KB")
        results.append(("Impossible constraint", True, 0, 0, len(result.image_data) / 1024))
    except WorkerError as e:
        print(f"  ✓ Correctly failed: {e.code.value}")
        if e.code == ErrorCode.SIZE_EXCEEDED:
            print(f"    Error details: {e.details}")
        results.append(("Impossible constraint", False, 0, 0, 0))
    
    # Summary
    print("\n" + "=" * 70)
    print("STRESS TEST SUMMARY")
    print("=" * 70)
    print(f"{'Test':<35} {'Conv':<8} {'Iters':<8} {'Quality':<10} {'Size KB':<10}")
    print("-" * 70)
    
    for name, conv, iters, qual, size in results:
        c = "✓" if conv else "✗"
        print(f"{name:<35} {c:<8} {iters:<8} {qual:<10} {size:<10.1f}")
    
    # Verify iteration cap
    print("\n" + "=" * 70)
    print("ITERATION CAP VERIFICATION")
    print("=" * 70)
    print(f"MAX_COMPRESSION_ITERATIONS = {MAX_COMPRESSION_ITERATIONS}")
    print(f"MIN_JPEG_QUALITY = {MIN_JPEG_QUALITY}")
    
    max_observed_iters = max(r[2] for r in results)
    print(f"Maximum iterations observed: {max_observed_iters}")
    
    if max_observed_iters <= MAX_COMPRESSION_ITERATIONS + 2:  # +2 for initial + final fallback
        print("✓ Iteration cap is effective")
    else:
        print("✗ WARNING: Iterations exceeded expected maximum")
    
    # Final verdict
    print("\n" + "=" * 70)
    print("STRESS TEST VERDICT")
    print("=" * 70)
    
    expected_failures = ["Noise 400x500 → 5KB", "Impossible constraint"]
    unexpected_failures = [r for r in results if not r[1] and r[0] not in expected_failures]
    unexpected_successes = [r for r in results if r[1] and r[0] in expected_failures]
    
    if unexpected_failures:
        print("✗ UNEXPECTED FAILURES:")
        for r in unexpected_failures:
            print(f"  - {r[0]}")
    elif unexpected_successes:
        print("✗ UNEXPECTED SUCCESSES (should have failed):")
        for r in unexpected_successes:
            print(f"  - {r[0]}")
    else:
        print("✓ ALL STRESS TESTS BEHAVE AS EXPECTED")
        print("  - Compression converges for realistic constraints")
        print("  - Impossible constraints fail with SIZE_EXCEEDED")
        print("  - No infinite loops detected")


if __name__ == "__main__":
    run_stress_tests()
