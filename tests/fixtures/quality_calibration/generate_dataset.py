#!/usr/bin/env python3
"""
Generate synthetic calibration dataset for quality scoring validation.

Creates ~20 images with diverse quality characteristics:
- Clean scans (scanner-generated)
- Phone photos (good lighting)
- Phone photos (low light)
- Slight blur
- Heavy blur
- Overexposed
- Underexposed
- White background + text
- Text-dense documents (marksheets, forms)

Each image is labeled with expected human rating:
- "good" → should go Fast Path
- "medium" → borderline
- "poor" → must go Fallback
"""

import csv
import os
from pathlib import Path

import cv2
import numpy as np

OUTPUT_DIR = Path(__file__).parent
DATASET_CSV = OUTPUT_DIR / "dataset_manifest.csv"


def create_base_document(width=800, height=1100, bg_color=255, text_density="normal"):
    """Create a base document with text-like patterns."""
    img = np.full((height, width, 3), bg_color, dtype=np.uint8)
    
    # Add text-like horizontal lines (simulate text lines)
    line_configs = {
        "sparse": (80, 60),      # Few lines, large spacing
        "normal": (40, 25),      # Normal document
        "dense": (20, 15),       # Dense text (marksheet/form)
    }
    
    line_spacing, line_height = line_configs.get(text_density, (40, 25))
    
    y = 100
    while y < height - 100:
        # Vary line length to simulate paragraphs
        line_end = int(width * np.random.uniform(0.6, 0.9))
        line_start = 50
        
        # Draw thin black rectangle to simulate text line
        cv2.rectangle(img, (line_start, y), (line_end, y + line_height // 3), 
                     (30, 30, 30), -1)
        
        # Add some word breaks
        for _ in range(np.random.randint(3, 8)):
            gap_x = np.random.randint(line_start + 50, max(line_end - 50, line_start + 60))
            gap_width = np.random.randint(10, 30)
            cv2.rectangle(img, (gap_x, y), (gap_x + gap_width, y + line_height // 3),
                         (bg_color, bg_color, bg_color), -1)
        
        y += line_spacing
    
    # Add a header-like element
    cv2.rectangle(img, (50, 30), (width - 50, 70), (20, 20, 20), -1)
    
    # Add some form-like boxes for dense documents
    if text_density == "dense":
        for i in range(3):
            box_y = 150 + i * 300
            cv2.rectangle(img, (50, box_y), (width - 50, box_y + 250), (100, 100, 100), 2)
            # Add grid lines inside
            for j in range(5):
                cv2.line(img, (50, box_y + j * 50), (width - 50, box_y + j * 50), (150, 150, 150), 1)
    
    return img


def apply_blur(img, kernel_size):
    """Apply Gaussian blur."""
    return cv2.GaussianBlur(img, (kernel_size, kernel_size), 0)


def apply_motion_blur(img, size, angle=0):
    """Apply motion blur."""
    kernel = np.zeros((size, size))
    kernel[size // 2, :] = np.ones(size)
    kernel = kernel / size
    
    # Rotate kernel for angled motion
    if angle != 0:
        center = (size // 2, size // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        kernel = cv2.warpAffine(kernel, M, (size, size))
    
    return cv2.filter2D(img, -1, kernel)


def add_noise(img, noise_level):
    """Add Gaussian noise."""
    noise = np.random.normal(0, noise_level, img.shape).astype(np.float32)
    noisy = img.astype(np.float32) + noise
    return np.clip(noisy, 0, 255).astype(np.uint8)


def adjust_brightness(img, factor):
    """Adjust brightness. factor > 1 = brighter, < 1 = darker."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    hsv = hsv.astype(np.float32)
    hsv[:, :, 2] = np.clip(hsv[:, :, 2] * factor, 0, 255)
    hsv = hsv.astype(np.uint8)
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)


def adjust_contrast(img, factor):
    """Adjust contrast. factor > 1 = more contrast, < 1 = less contrast."""
    mean = np.mean(img)
    return np.clip((img.astype(np.float32) - mean) * factor + mean, 0, 255).astype(np.uint8)


def add_jpeg_artifacts(img, quality):
    """Add JPEG compression artifacts."""
    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
    _, encoded = cv2.imencode('.jpg', img, encode_param)
    return cv2.imdecode(encoded, cv2.IMREAD_COLOR)


def simulate_low_light(img):
    """Simulate low-light phone capture: dark, noisy, low contrast."""
    # Darken
    img = adjust_brightness(img, 0.4)
    # Reduce contrast
    img = adjust_contrast(img, 0.7)
    # Add noise (typical of high ISO)
    img = add_noise(img, 25)
    return img


def simulate_overexposed(img):
    """Simulate overexposed image: washed out, low contrast."""
    img = adjust_brightness(img, 1.8)
    img = adjust_contrast(img, 0.5)
    # Clip whites
    img = np.clip(img.astype(np.float32) + 40, 0, 255).astype(np.uint8)
    return img


def simulate_underexposed(img):
    """Simulate underexposed image: too dark, detail loss."""
    img = adjust_brightness(img, 0.3)
    img = adjust_contrast(img, 1.2)  # Boost contrast to simulate recovery attempt
    return img


def generate_dataset():
    """Generate all calibration images and manifest."""
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    dataset = []
    
    # =========================================================================
    # GOOD QUALITY IMAGES (should route to Fast Path)
    # =========================================================================
    
    # 1. Clean scan - ideal scanner output
    img = create_base_document(bg_color=252)
    img = adjust_contrast(img, 1.1)  # Slight contrast boost typical of scanners
    cv2.imwrite(str(OUTPUT_DIR / "01_clean_scan.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 95])
    dataset.append(("01_clean_scan.jpg", "good", "Clean scanner output, high quality"))
    
    # 2. Clean scan - dense text (marksheet)
    img = create_base_document(bg_color=252, text_density="dense")
    img = adjust_contrast(img, 1.1)
    cv2.imwrite(str(OUTPUT_DIR / "02_dense_scan.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 95])
    dataset.append(("02_dense_scan.jpg", "good", "Dense marksheet/form scan, high quality"))
    
    # 3. Phone photo - good lighting
    img = create_base_document(bg_color=248)
    img = add_noise(img, 5)  # Very slight noise from phone sensor
    img = add_jpeg_artifacts(img, 90)
    cv2.imwrite(str(OUTPUT_DIR / "03_phone_good_light.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
    dataset.append(("03_phone_good_light.jpg", "good", "Phone capture in good daylight"))
    
    # 4. White background document - clean
    img = create_base_document(bg_color=255, text_density="sparse")
    cv2.imwrite(str(OUTPUT_DIR / "04_white_bg_clean.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 95])
    dataset.append(("04_white_bg_clean.jpg", "good", "White background, sparse text, clean"))
    
    # 5. Slightly enhanced phone photo
    img = create_base_document(bg_color=250)
    img = add_noise(img, 3)
    img = adjust_contrast(img, 1.05)
    cv2.imwrite(str(OUTPUT_DIR / "05_phone_enhanced.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 93])
    dataset.append(("05_phone_enhanced.jpg", "good", "Phone photo with auto-enhancement"))
    
    # =========================================================================
    # MEDIUM QUALITY IMAGES (borderline - could go either way)
    # =========================================================================
    
    # 6. Slight blur - just noticeable
    img = create_base_document(bg_color=250)
    img = apply_blur(img, 3)
    cv2.imwrite(str(OUTPUT_DIR / "06_slight_blur.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    dataset.append(("06_slight_blur.jpg", "medium", "Slight blur, text still readable"))
    
    # 7. Phone photo - suboptimal lighting
    img = create_base_document(bg_color=245)
    img = adjust_brightness(img, 0.75)
    img = add_noise(img, 12)
    cv2.imwrite(str(OUTPUT_DIR / "07_phone_dim_light.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 88])
    dataset.append(("07_phone_dim_light.jpg", "medium", "Phone photo in dim indoor light"))
    
    # 8. Slight motion blur
    img = create_base_document(bg_color=250)
    img = apply_motion_blur(img, 5, angle=15)
    cv2.imwrite(str(OUTPUT_DIR / "08_slight_motion.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    dataset.append(("08_slight_motion.jpg", "medium", "Slight motion blur from shaky hands"))
    
    # 9. Slightly overexposed
    img = create_base_document(bg_color=250)
    img = adjust_brightness(img, 1.3)
    cv2.imwrite(str(OUTPUT_DIR / "09_slight_overexpose.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    dataset.append(("09_slight_overexpose.jpg", "medium", "Slightly overexposed, details visible"))
    
    # 10. Noisy but readable
    img = create_base_document(bg_color=250)
    img = add_noise(img, 18)
    cv2.imwrite(str(OUTPUT_DIR / "10_noisy_readable.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 88])
    dataset.append(("10_noisy_readable.jpg", "medium", "Noisy but text still clear"))
    
    # 11. Heavy JPEG compression
    img = create_base_document(bg_color=252)
    img = add_jpeg_artifacts(img, 50)
    cv2.imwrite(str(OUTPUT_DIR / "11_jpeg_artifacts.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 50])
    dataset.append(("11_jpeg_artifacts.jpg", "medium", "Heavy JPEG compression, blockiness"))
    
    # =========================================================================
    # POOR QUALITY IMAGES (must route to Fallback)
    # =========================================================================
    
    # 12. Heavy blur - text unreadable
    img = create_base_document(bg_color=250)
    img = apply_blur(img, 11)
    cv2.imwrite(str(OUTPUT_DIR / "12_heavy_blur.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    dataset.append(("12_heavy_blur.jpg", "poor", "Heavy blur, text unreadable"))
    
    # 13. Very heavy blur
    img = create_base_document(bg_color=250)
    img = apply_blur(img, 21)
    cv2.imwrite(str(OUTPUT_DIR / "13_very_heavy_blur.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    dataset.append(("13_very_heavy_blur.jpg", "poor", "Extreme blur, document unusable"))
    
    # 14. Low light phone capture
    img = create_base_document(bg_color=250)
    img = simulate_low_light(img)
    cv2.imwrite(str(OUTPUT_DIR / "14_low_light.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    dataset.append(("14_low_light.jpg", "poor", "Low light capture, dark and noisy"))
    
    # 15. Severely overexposed
    img = create_base_document(bg_color=250)
    img = simulate_overexposed(img)
    cv2.imwrite(str(OUTPUT_DIR / "15_overexposed.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    dataset.append(("15_overexposed.jpg", "poor", "Severely overexposed, washed out"))
    
    # 16. Severely underexposed
    img = create_base_document(bg_color=250)
    img = simulate_underexposed(img)
    cv2.imwrite(str(OUTPUT_DIR / "16_underexposed.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    dataset.append(("16_underexposed.jpg", "poor", "Severely underexposed, too dark"))
    
    # 17. Motion blur - significant
    img = create_base_document(bg_color=250)
    img = apply_motion_blur(img, 15, angle=0)
    cv2.imwrite(str(OUTPUT_DIR / "17_motion_blur.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    dataset.append(("17_motion_blur.jpg", "poor", "Significant motion blur"))
    
    # 18. Combined issues - blur + noise
    img = create_base_document(bg_color=250)
    img = apply_blur(img, 7)
    img = add_noise(img, 20)
    cv2.imwrite(str(OUTPUT_DIR / "18_blur_and_noise.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    dataset.append(("18_blur_and_noise.jpg", "poor", "Blur combined with high noise"))
    
    # 19. Very low contrast
    img = create_base_document(bg_color=200)  # Gray background
    img = adjust_contrast(img, 0.3)
    img = adjust_brightness(img, 1.2)
    cv2.imwrite(str(OUTPUT_DIR / "19_low_contrast.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    dataset.append(("19_low_contrast.jpg", "poor", "Very low contrast, text fades"))
    
    # 20. Extreme noise
    img = create_base_document(bg_color=250)
    img = add_noise(img, 45)
    cv2.imwrite(str(OUTPUT_DIR / "20_extreme_noise.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    dataset.append(("20_extreme_noise.jpg", "poor", "Extreme noise, speckled image"))
    
    # Write manifest CSV
    with open(DATASET_CSV, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['filename', 'human_label', 'notes'])
        for row in dataset:
            writer.writerow(row)
    
    print(f"Generated {len(dataset)} calibration images")
    print(f"Manifest saved to: {DATASET_CSV}")
    
    # Summary by category
    good_count = sum(1 for _, label, _ in dataset if label == "good")
    medium_count = sum(1 for _, label, _ in dataset if label == "medium")
    poor_count = sum(1 for _, label, _ in dataset if label == "poor")
    print(f"\nDataset breakdown:")
    print(f"  Good:   {good_count}")
    print(f"  Medium: {medium_count}")
    print(f"  Poor:   {poor_count}")
    
    return dataset


if __name__ == "__main__":
    generate_dataset()
