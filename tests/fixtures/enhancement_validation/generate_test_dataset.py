"""
Generate synthetic test dataset for enhancement pipeline validation.

Creates ~15 test images covering:
- Blur types: slight, heavy, motion
- Exposure: low-light, overexposed
- Noise: grainy phone photos
- Rotation: ±1°, ±5°, 90°, 180°
- Clean images (control group)

Each image is a synthetic document with text and geometric shapes.
"""

import json
import os
import sys
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Tuple, Optional
import random

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


@dataclass
class TestImageMeta:
    """Metadata for a test image."""
    filename: str
    category: str
    description: str
    baseline_readable: bool
    expected_improvement: bool
    degradation_type: str
    degradation_severity: str  # "none", "mild", "moderate", "severe"
    rotation_applied: Optional[float] = None


def create_base_document(width: int = 600, height: int = 800) -> np.ndarray:
    """
    Create a base synthetic document image.
    White background with black text-like content and shapes.
    """
    # Create white background
    img = np.ones((height, width, 3), dtype=np.uint8) * 255
    
    # Add title area (dark header)
    cv2.rectangle(img, (20, 20), (width - 20, 80), (40, 40, 40), -1)
    cv2.putText(img, "SAMPLE DOCUMENT", (40, 60), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
    
    # Add horizontal lines (like form fields)
    for y in range(120, 700, 60):
        cv2.line(img, (40, y), (width - 40, y), (0, 0, 0), 1)
        # Add label text
        cv2.putText(img, f"Field {(y - 120) // 60 + 1}:", (45, y - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (80, 80, 80), 1)
        # Add sample value
        cv2.putText(img, f"Sample Value {random.randint(1000, 9999)}", (150, y - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)
    
    # Add a table in the middle
    table_y = 350
    table_h = 150
    cv2.rectangle(img, (40, table_y), (width - 40, table_y + table_h), (0, 0, 0), 1)
    # Table header
    cv2.rectangle(img, (40, table_y), (width - 40, table_y + 30), (200, 200, 200), -1)
    cv2.rectangle(img, (40, table_y), (width - 40, table_y + 30), (0, 0, 0), 1)
    cv2.putText(img, "Item", (60, table_y + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)
    cv2.putText(img, "Quantity", (250, table_y + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)
    cv2.putText(img, "Amount", (420, table_y + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)
    
    # Table rows
    for i, row_y in enumerate(range(table_y + 30, table_y + table_h, 30)):
        cv2.line(img, (40, row_y + 30), (width - 40, row_y + 30), (180, 180, 180), 1)
        cv2.putText(img, f"Item {i + 1}", (60, row_y + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 0), 1)
        cv2.putText(img, str(random.randint(1, 10)), (280, row_y + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 0), 1)
        cv2.putText(img, f"${random.randint(10, 999)}.00", (420, row_y + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 0), 1)
    
    # Vertical lines in table
    cv2.line(img, (230, table_y), (230, table_y + table_h), (180, 180, 180), 1)
    cv2.line(img, (400, table_y), (400, table_y + table_h), (180, 180, 180), 1)
    
    # Add footer
    cv2.putText(img, "Page 1 of 1", (width // 2 - 40, height - 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (120, 120, 120), 1)
    
    # Add a small logo/stamp area
    cv2.rectangle(img, (width - 120, height - 120), (width - 30, height - 40), (0, 0, 0), 2)
    cv2.putText(img, "VERIFIED", (width - 110, height - 70),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)
    
    return img


def apply_slight_blur(img: np.ndarray) -> np.ndarray:
    """Apply slight Gaussian blur."""
    return cv2.GaussianBlur(img, (5, 5), 1.0)


def apply_heavy_blur(img: np.ndarray) -> np.ndarray:
    """Apply heavy Gaussian blur."""
    return cv2.GaussianBlur(img, (15, 15), 5.0)


def apply_motion_blur(img: np.ndarray, kernel_size: int = 15) -> np.ndarray:
    """Apply horizontal motion blur."""
    kernel = np.zeros((kernel_size, kernel_size))
    kernel[kernel_size // 2, :] = np.ones(kernel_size) / kernel_size
    return cv2.filter2D(img, -1, kernel)


def apply_low_light(img: np.ndarray) -> np.ndarray:
    """Simulate low-light conditions (darken + add noise)."""
    # Darken the image
    darkened = (img.astype(np.float32) * 0.4).astype(np.uint8)
    
    # Add some noise
    noise = np.random.normal(0, 15, img.shape).astype(np.float32)
    noisy = np.clip(darkened.astype(np.float32) + noise, 0, 255).astype(np.uint8)
    
    return noisy


def apply_overexposure(img: np.ndarray) -> np.ndarray:
    """Simulate overexposure (brighten + wash out)."""
    # Brighten and reduce contrast
    brightened = np.clip(img.astype(np.float32) * 1.5 + 60, 0, 255).astype(np.uint8)
    return brightened


def apply_grain_noise(img: np.ndarray, intensity: float = 0.1) -> np.ndarray:
    """Add grainy noise (simulates phone camera in low light)."""
    noise = np.random.normal(0, 255 * intensity, img.shape).astype(np.float32)
    noisy = np.clip(img.astype(np.float32) + noise, 0, 255).astype(np.uint8)
    return noisy


def apply_rotation(img: np.ndarray, angle: float) -> np.ndarray:
    """Apply rotation to image."""
    h, w = img.shape[:2]
    center = (w // 2, h // 2)
    
    rotation_matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    
    # For small rotations, keep same dimensions
    if abs(angle) < 10:
        rotated = cv2.warpAffine(img, rotation_matrix, (w, h),
                                  flags=cv2.INTER_LINEAR,
                                  borderMode=cv2.BORDER_REPLICATE)
    else:
        # For large rotations, expand canvas
        cos = abs(rotation_matrix[0, 0])
        sin = abs(rotation_matrix[0, 1])
        new_w = int(h * sin + w * cos)
        new_h = int(h * cos + w * sin)
        rotation_matrix[0, 2] += (new_w - w) / 2
        rotation_matrix[1, 2] += (new_h - h) / 2
        rotated = cv2.warpAffine(img, rotation_matrix, (new_w, new_h),
                                  flags=cv2.INTER_LINEAR,
                                  borderValue=(255, 255, 255))
    
    return rotated


def generate_test_images(output_dir: Path) -> List[TestImageMeta]:
    """Generate all test images and return metadata."""
    
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata: List[TestImageMeta] = []
    
    # Seed for reproducibility
    np.random.seed(42)
    random.seed(42)
    
    # 1. Clean control image
    base = create_base_document()
    cv2.imwrite(str(output_dir / "01_clean_control.jpg"), base, [cv2.IMWRITE_JPEG_QUALITY, 95])
    metadata.append(TestImageMeta(
        filename="01_clean_control.jpg",
        category="control",
        description="Clean, high-quality document (control)",
        baseline_readable=True,
        expected_improvement=False,
        degradation_type="none",
        degradation_severity="none"
    ))
    
    # 2. Slight blur
    slight_blur = apply_slight_blur(create_base_document())
    cv2.imwrite(str(output_dir / "02_slight_blur.jpg"), slight_blur, [cv2.IMWRITE_JPEG_QUALITY, 90])
    metadata.append(TestImageMeta(
        filename="02_slight_blur.jpg",
        category="blur",
        description="Slight Gaussian blur",
        baseline_readable=True,
        expected_improvement=True,
        degradation_type="blur",
        degradation_severity="mild"
    ))
    
    # 3. Heavy blur
    heavy_blur = apply_heavy_blur(create_base_document())
    cv2.imwrite(str(output_dir / "03_heavy_blur.jpg"), heavy_blur, [cv2.IMWRITE_JPEG_QUALITY, 90])
    metadata.append(TestImageMeta(
        filename="03_heavy_blur.jpg",
        category="blur",
        description="Heavy Gaussian blur",
        baseline_readable=False,
        expected_improvement=True,
        degradation_type="blur",
        degradation_severity="severe"
    ))
    
    # 4. Motion blur
    motion_blur = apply_motion_blur(create_base_document())
    cv2.imwrite(str(output_dir / "04_motion_blur.jpg"), motion_blur, [cv2.IMWRITE_JPEG_QUALITY, 90])
    metadata.append(TestImageMeta(
        filename="04_motion_blur.jpg",
        category="blur",
        description="Horizontal motion blur",
        baseline_readable=False,
        expected_improvement=True,
        degradation_type="motion_blur",
        degradation_severity="moderate"
    ))
    
    # 5. Low light
    low_light = apply_low_light(create_base_document())
    cv2.imwrite(str(output_dir / "05_low_light.jpg"), low_light, [cv2.IMWRITE_JPEG_QUALITY, 90])
    metadata.append(TestImageMeta(
        filename="05_low_light.jpg",
        category="exposure",
        description="Low light conditions (dark + noise)",
        baseline_readable=False,
        expected_improvement=True,
        degradation_type="underexposure",
        degradation_severity="severe"
    ))
    
    # 6. Overexposed
    overexposed = apply_overexposure(create_base_document())
    cv2.imwrite(str(output_dir / "06_overexposed.jpg"), overexposed, [cv2.IMWRITE_JPEG_QUALITY, 90])
    metadata.append(TestImageMeta(
        filename="06_overexposed.jpg",
        category="exposure",
        description="Overexposed / washed out",
        baseline_readable=True,
        expected_improvement=True,
        degradation_type="overexposure",
        degradation_severity="moderate"
    ))
    
    # 7. Light grain noise
    light_grain = apply_grain_noise(create_base_document(), 0.05)
    cv2.imwrite(str(output_dir / "07_light_grain.jpg"), light_grain, [cv2.IMWRITE_JPEG_QUALITY, 90])
    metadata.append(TestImageMeta(
        filename="07_light_grain.jpg",
        category="noise",
        description="Light grain noise",
        baseline_readable=True,
        expected_improvement=True,
        degradation_type="noise",
        degradation_severity="mild"
    ))
    
    # 8. Heavy grain noise
    heavy_grain = apply_grain_noise(create_base_document(), 0.15)
    cv2.imwrite(str(output_dir / "08_heavy_grain.jpg"), heavy_grain, [cv2.IMWRITE_JPEG_QUALITY, 90])
    metadata.append(TestImageMeta(
        filename="08_heavy_grain.jpg",
        category="noise",
        description="Heavy grain noise (phone camera low-light)",
        baseline_readable=False,
        expected_improvement=True,
        degradation_type="noise",
        degradation_severity="severe"
    ))
    
    # 9. Rotation +1 degree
    rot_1 = apply_rotation(create_base_document(), 1)
    cv2.imwrite(str(output_dir / "09_rotation_1deg.jpg"), rot_1, [cv2.IMWRITE_JPEG_QUALITY, 95])
    metadata.append(TestImageMeta(
        filename="09_rotation_1deg.jpg",
        category="rotation",
        description="1 degree clockwise rotation",
        baseline_readable=True,
        expected_improvement=False,  # Too small to correct
        degradation_type="rotation",
        degradation_severity="mild",
        rotation_applied=1.0
    ))
    
    # 10. Rotation +5 degrees
    rot_5 = apply_rotation(create_base_document(), 5)
    cv2.imwrite(str(output_dir / "10_rotation_5deg.jpg"), rot_5, [cv2.IMWRITE_JPEG_QUALITY, 95])
    metadata.append(TestImageMeta(
        filename="10_rotation_5deg.jpg",
        category="rotation",
        description="5 degrees clockwise rotation",
        baseline_readable=True,
        expected_improvement=True,
        degradation_type="rotation",
        degradation_severity="moderate",
        rotation_applied=5.0
    ))
    
    # 11. Rotation -5 degrees
    rot_neg5 = apply_rotation(create_base_document(), -5)
    cv2.imwrite(str(output_dir / "11_rotation_neg5deg.jpg"), rot_neg5, [cv2.IMWRITE_JPEG_QUALITY, 95])
    metadata.append(TestImageMeta(
        filename="11_rotation_neg5deg.jpg",
        category="rotation",
        description="5 degrees counter-clockwise rotation",
        baseline_readable=True,
        expected_improvement=True,
        degradation_type="rotation",
        degradation_severity="moderate",
        rotation_applied=-5.0
    ))
    
    # 12. Rotation 90 degrees
    rot_90 = apply_rotation(create_base_document(), 90)
    cv2.imwrite(str(output_dir / "12_rotation_90deg.jpg"), rot_90, [cv2.IMWRITE_JPEG_QUALITY, 95])
    metadata.append(TestImageMeta(
        filename="12_rotation_90deg.jpg",
        category="rotation",
        description="90 degrees rotation",
        baseline_readable=True,
        expected_improvement=True,
        degradation_type="rotation",
        degradation_severity="severe",
        rotation_applied=90.0
    ))
    
    # 13. Rotation 180 degrees
    rot_180 = apply_rotation(create_base_document(), 180)
    cv2.imwrite(str(output_dir / "13_rotation_180deg.jpg"), rot_180, [cv2.IMWRITE_JPEG_QUALITY, 95])
    metadata.append(TestImageMeta(
        filename="13_rotation_180deg.jpg",
        category="rotation",
        description="180 degrees rotation (upside down)",
        baseline_readable=True,
        expected_improvement=True,
        degradation_type="rotation",
        degradation_severity="severe",
        rotation_applied=180.0
    ))
    
    # 14. Combined: low light + slight blur
    combined_1 = apply_slight_blur(apply_low_light(create_base_document()))
    cv2.imwrite(str(output_dir / "14_lowlight_blur.jpg"), combined_1, [cv2.IMWRITE_JPEG_QUALITY, 90])
    metadata.append(TestImageMeta(
        filename="14_lowlight_blur.jpg",
        category="combined",
        description="Low light + slight blur",
        baseline_readable=False,
        expected_improvement=True,
        degradation_type="multiple",
        degradation_severity="severe"
    ))
    
    # 15. Combined: noise + rotation
    combined_2 = apply_rotation(apply_grain_noise(create_base_document(), 0.08), 3)
    cv2.imwrite(str(output_dir / "15_noise_rotation.jpg"), combined_2, [cv2.IMWRITE_JPEG_QUALITY, 90])
    metadata.append(TestImageMeta(
        filename="15_noise_rotation.jpg",
        category="combined",
        description="Moderate noise + 3 degree rotation",
        baseline_readable=True,
        expected_improvement=True,
        degradation_type="multiple",
        degradation_severity="moderate",
        rotation_applied=3.0
    ))
    
    # 16. Clean but compressed (JPEG artifacts)
    base_compressed = create_base_document()
    cv2.imwrite(str(output_dir / "16_jpeg_artifacts.jpg"), base_compressed, [cv2.IMWRITE_JPEG_QUALITY, 30])
    metadata.append(TestImageMeta(
        filename="16_jpeg_artifacts.jpg",
        category="artifacts",
        description="Clean image with heavy JPEG compression",
        baseline_readable=True,
        expected_improvement=True,
        degradation_type="compression",
        degradation_severity="moderate"
    ))
    
    return metadata


def main():
    """Generate test dataset."""
    script_dir = Path(__file__).parent
    output_dir = script_dir
    
    print("Generating enhancement validation test dataset...")
    print(f"Output directory: {output_dir}")
    
    metadata = generate_test_images(output_dir)
    
    # Save metadata
    manifest = {
        "description": "Enhancement pipeline validation test dataset",
        "total_images": len(metadata),
        "images": [asdict(m) for m in metadata]
    }
    
    with open(output_dir / "dataset_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)
    
    # Print summary
    print(f"\nGenerated {len(metadata)} test images:")
    for m in metadata:
        readable = "✓" if m.baseline_readable else "✗"
        improve = "↑" if m.expected_improvement else "="
        print(f"  [{readable}|{improve}] {m.filename}: {m.description}")
    
    print(f"\nManifest saved to: {output_dir / 'dataset_manifest.json'}")


if __name__ == "__main__":
    main()
