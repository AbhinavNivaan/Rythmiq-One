#!/usr/bin/env python3
"""
Generate synthetic test images for schema validation.

Creates test images per portal schema:
- clean: Standard passport-style photo
- large: High-resolution borderline image
- noisy: Complex background with noise
- borderline: Image close to size limit after compression
- tiny: Very small input requiring upscale
- huge: Extremely large input
- white: Near-white image
- black: Near-black image

Run from project root:
    python tests/fixtures/schema_validation/generate_test_images.py
"""

import os
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

# Output directory
OUTPUT_DIR = Path(__file__).parent


# =============================================================================
# Portal Schema Definitions (seeded in DB)
# =============================================================================
PORTAL_SCHEMAS = {
    "neet_ug_2026": {
        "name": "NEET UG 2026",
        "width": 200,
        "height": 230,
        "dpi": 200,
        "max_kb": 100,
    },
    "jee_main_2026": {
        "name": "JEE Main 2026",
        "width": 350,
        "height": 450,
        "dpi": 300,
        "max_kb": 150,
    },
    "aadhaar_update": {
        "name": "Aadhaar Update",
        "width": 200,
        "height": 230,
        "dpi": 200,
        "max_kb": 100,
    },
    "passport_seva": {
        "name": "Passport Seva (India)",
        "width": 413,
        "height": 531,
        "dpi": 300,
        "max_kb": 300,
    },
    "college_generic": {
        "name": "College Generic",
        "width": 400,
        "height": 500,
        "dpi": 200,
        "max_kb": 200,
    },
}


def create_face_placeholder(width: int, height: int) -> np.ndarray:
    """Create a synthetic face placeholder for testing."""
    # Light background (passport style)
    img = np.full((height, width, 3), (230, 230, 235), dtype=np.uint8)
    
    # Face oval
    center_x = width // 2
    center_y = height // 2 - height // 10
    axes = (width // 4, height // 3)
    cv2.ellipse(img, (center_x, center_y), axes, 0, 0, 360, (180, 160, 140), -1)
    
    # Eyes
    eye_y = center_y - height // 12
    eye_offset = width // 8
    cv2.circle(img, (center_x - eye_offset, eye_y), width // 20, (50, 50, 50), -1)
    cv2.circle(img, (center_x + eye_offset, eye_y), width // 20, (50, 50, 50), -1)
    
    # Mouth
    mouth_y = center_y + height // 8
    cv2.ellipse(img, (center_x, mouth_y), (width // 10, height // 30), 0, 0, 180, (100, 80, 80), 2)
    
    # Hair
    hair_top = center_y - height // 3
    cv2.ellipse(img, (center_x, hair_top + height // 8), (width // 3, height // 5), 0, 180, 360, (30, 20, 10), -1)
    
    # Shoulders
    shoulder_y = height - height // 5
    pts = np.array([
        [0, height],
        [width, height],
        [width, shoulder_y + height // 10],
        [width // 2 + width // 3, shoulder_y],
        [width // 2, shoulder_y - height // 20],
        [width // 2 - width // 3, shoulder_y],
        [0, shoulder_y + height // 10],
    ], dtype=np.int32)
    cv2.fillPoly(img, [pts], (60, 60, 120))
    
    return img


def generate_clean_image(schema_key: str) -> None:
    """Generate a clean passport-style photo."""
    schema = PORTAL_SCHEMAS[schema_key]
    # Generate at 2x for quality, will be resized by adapter
    w, h = schema["width"] * 2, schema["height"] * 2
    img = create_face_placeholder(w, h)
    
    output_path = OUTPUT_DIR / schema_key / "clean.jpg"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), img, [cv2.IMWRITE_JPEG_QUALITY, 95])
    print(f"  ✓ {output_path}")


def generate_large_image(schema_key: str) -> None:
    """Generate a high-resolution borderline large image."""
    schema = PORTAL_SCHEMAS[schema_key]
    # Generate at 10x resolution
    w, h = schema["width"] * 10, schema["height"] * 10
    img = create_face_placeholder(w, h)
    
    # Add fine details to increase complexity
    noise = np.random.normal(0, 3, img.shape).astype(np.int16)
    img = np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    
    output_path = OUTPUT_DIR / schema_key / "large.jpg"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), img, [cv2.IMWRITE_JPEG_QUALITY, 98])
    print(f"  ✓ {output_path}")


def generate_noisy_image(schema_key: str) -> None:
    """Generate image with complex background and noise."""
    schema = PORTAL_SCHEMAS[schema_key]
    w, h = schema["width"] * 3, schema["height"] * 3
    
    # Complex textured background
    img = np.zeros((h, w, 3), dtype=np.uint8)
    for i in range(0, h, 10):
        for j in range(0, w, 10):
            color = (
                np.random.randint(100, 200),
                np.random.randint(100, 200),
                np.random.randint(100, 200),
            )
            cv2.rectangle(img, (j, i), (j + 10, i + 10), color, -1)
    
    # Overlay face
    face = create_face_placeholder(w, h)
    mask = cv2.cvtColor(face, cv2.COLOR_BGR2GRAY) < 230
    img[mask] = face[mask]
    
    # Add Gaussian noise
    noise = np.random.normal(0, 15, img.shape).astype(np.int16)
    img = np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    
    output_path = OUTPUT_DIR / schema_key / "noisy.jpg"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), img, [cv2.IMWRITE_JPEG_QUALITY, 95])
    print(f"  ✓ {output_path}")


def generate_borderline_image(schema_key: str) -> None:
    """Generate image that will be close to size limit after compression."""
    schema = PORTAL_SCHEMAS[schema_key]
    w, h = schema["width"] * 4, schema["height"] * 4
    
    # Create high-entropy image (harder to compress)
    img = create_face_placeholder(w, h)
    
    # Add random fine-grained texture
    texture = np.random.randint(0, 50, (h, w, 3), dtype=np.uint8)
    img = cv2.addWeighted(img, 0.85, texture, 0.15, 0)
    
    # Add subtle gradients
    for c in range(3):
        gradient = np.linspace(0, 30, w, dtype=np.uint8)
        gradient = np.tile(gradient, (h, 1))
        img[:, :, c] = np.clip(img[:, :, c].astype(np.int16) + gradient.astype(np.int16), 0, 255).astype(np.uint8)
    
    output_path = OUTPUT_DIR / schema_key / "borderline.jpg"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), img, [cv2.IMWRITE_JPEG_QUALITY, 98])
    print(f"  ✓ {output_path}")


def generate_tiny_image(schema_key: str) -> None:
    """Generate very small image requiring upscaling."""
    schema = PORTAL_SCHEMAS[schema_key]
    # Generate at 1/4 target size
    w, h = max(schema["width"] // 4, 50), max(schema["height"] // 4, 50)
    img = create_face_placeholder(w, h)
    
    output_path = OUTPUT_DIR / schema_key / "tiny.jpg"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    print(f"  ✓ {output_path}")


def generate_huge_image(schema_key: str) -> None:
    """Generate extremely large image (stress test)."""
    schema = PORTAL_SCHEMAS[schema_key]
    # 20x resolution
    w, h = schema["width"] * 20, schema["height"] * 20
    img = create_face_placeholder(w, h)
    
    output_path = OUTPUT_DIR / schema_key / "huge.jpg"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), img, [cv2.IMWRITE_JPEG_QUALITY, 95])
    print(f"  ✓ {output_path}")


def generate_white_image(schema_key: str) -> None:
    """Generate near-white image (edge case)."""
    schema = PORTAL_SCHEMAS[schema_key]
    w, h = schema["width"] * 2, schema["height"] * 2
    
    # Almost white with slight variations
    img = np.full((h, w, 3), 252, dtype=np.uint8)
    noise = np.random.randint(-3, 4, img.shape, dtype=np.int16)
    img = np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    
    # Add faint face outline
    center_x, center_y = w // 2, h // 2
    cv2.ellipse(img, (center_x, center_y), (w // 4, h // 3), 0, 0, 360, (245, 245, 248), 2)
    
    output_path = OUTPUT_DIR / schema_key / "white.jpg"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), img, [cv2.IMWRITE_JPEG_QUALITY, 95])
    print(f"  ✓ {output_path}")


def generate_black_image(schema_key: str) -> None:
    """Generate near-black image (edge case)."""
    schema = PORTAL_SCHEMAS[schema_key]
    w, h = schema["width"] * 2, schema["height"] * 2
    
    # Almost black with slight variations
    img = np.full((h, w, 3), 5, dtype=np.uint8)
    noise = np.random.randint(-3, 6, img.shape, dtype=np.int16)
    img = np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    
    # Add faint face outline
    center_x, center_y = w // 2, h // 2
    cv2.ellipse(img, (center_x, center_y), (w // 4, h // 3), 0, 0, 360, (15, 15, 18), 2)
    
    output_path = OUTPUT_DIR / schema_key / "black.jpg"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), img, [cv2.IMWRITE_JPEG_QUALITY, 95])
    print(f"  ✓ {output_path}")


def generate_corrupt_header(schema_key: str) -> None:
    """Generate image with intentionally corrupt header (negative test)."""
    output_path = OUTPUT_DIR / schema_key / "corrupt.bin"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write garbage that looks like it might be an image
    with open(output_path, "wb") as f:
        f.write(b'\xff\xd8\xff' + os.urandom(1000))  # Fake JPEG start
    
    print(f"  ✓ {output_path}")


def main():
    print("=" * 60)
    print("Schema Validation Test Image Generator")
    print("=" * 60)
    
    for schema_key, schema in PORTAL_SCHEMAS.items():
        print(f"\n📁 {schema['name']} ({schema['width']}×{schema['height']})")
        
        generate_clean_image(schema_key)
        generate_large_image(schema_key)
        generate_noisy_image(schema_key)
        generate_borderline_image(schema_key)
        generate_tiny_image(schema_key)
        generate_huge_image(schema_key)
        generate_white_image(schema_key)
        generate_black_image(schema_key)
        generate_corrupt_header(schema_key)
    
    print("\n" + "=" * 60)
    print("✅ Test image generation complete")
    print(f"   Output: {OUTPUT_DIR}")
    print("=" * 60)
    
    # Generate manifest
    manifest = []
    for schema_key in PORTAL_SCHEMAS:
        schema_dir = OUTPUT_DIR / schema_key
        for img_file in schema_dir.glob("*"):
            if img_file.suffix in (".jpg", ".bin"):
                manifest.append({
                    "schema": schema_key,
                    "file": str(img_file.name),
                    "path": str(img_file.relative_to(OUTPUT_DIR)),
                    "size_bytes": img_file.stat().st_size,
                })
    
    # Save manifest
    import json
    manifest_path = OUTPUT_DIR / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"\n📄 Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
