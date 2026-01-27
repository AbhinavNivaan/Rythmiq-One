#!/usr/bin/env python3
"""
Run OCR on quality calibration images to measure confidence across quality levels.
"""

import sys
import time
import statistics
from pathlib import Path
import pytesseract
from PIL import Image

FIXTURES_DIR = Path(__file__).parent.parent / "quality_calibration"


def extract_text_with_conf(image_path: str):
    """Extract text with confidence."""
    img = Image.open(image_path)
    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    
    confidences = []
    texts = []
    
    for i in range(len(data['text'])):
        text = data['text'][i].strip()
        conf = int(data['conf'][i])
        
        if text and conf > 0:
            confidences.append(conf / 100.0)
            texts.append(text)
    
    full_text = ' '.join(texts)
    mean_conf = statistics.mean(confidences) if confidences else 0.0
    min_conf = min(confidences) if confidences else 0.0
    
    return full_text, mean_conf, min_conf, len(confidences)


def main():
    print("=" * 70)
    print("OCR Confidence on Quality Calibration Images")
    print("=" * 70)
    print()
    
    images = sorted(FIXTURES_DIR.glob("*.jpg"))
    
    if not images:
        print("No images found")
        return 1
    
    results = []
    
    for img_path in images:
        print(f"Processing {img_path.name}...", end=" ")
        start = time.perf_counter()
        text, mean_conf, min_conf, word_count = extract_text_with_conf(str(img_path))
        runtime = (time.perf_counter() - start) * 1000
        
        results.append({
            "filename": img_path.name,
            "mean_conf": mean_conf,
            "min_conf": min_conf,
            "word_count": word_count,
            "runtime_ms": runtime,
            "text_preview": text[:50] if text else "(no text)",
        })
        
        print(f"mean={mean_conf:.3f}, min={min_conf:.3f}, words={word_count}, {runtime:.0f}ms")
    
    print()
    print("=" * 70)
    print("SUMMARY BY QUALITY LABEL")
    print("=" * 70)
    
    # Group by quality label (from filename pattern)
    good = [r for r in results if any(x in r['filename'] for x in ['01_', '02_', '03_', '04_', '05_'])]
    medium = [r for r in results if any(x in r['filename'] for x in ['06_', '07_', '08_', '09_', '10_', '11_'])]
    poor = [r for r in results if any(x in r['filename'] for x in ['12_', '13_', '14_', '15_', '16_', '17_', '18_', '19_', '20_'])]
    
    for label, group in [("GOOD", good), ("MEDIUM", medium), ("POOR", poor)]:
        if group:
            mean_confs = [r['mean_conf'] for r in group]
            min_confs = [r['min_conf'] for r in group]
            print(f"\n{label} quality images ({len(group)} docs):")
            print(f"  Mean confidence: {statistics.mean(mean_confs):.3f} (range: {min(mean_confs):.3f}-{max(mean_confs):.3f})")
            print(f"  Min confidence:  {statistics.mean(min_confs):.3f} (range: {min(min_confs):.3f}-{max(min_confs):.3f})")
    
    print()
    print("=" * 70)
    print("THRESHOLD ANALYSIS")
    print("=" * 70)
    
    # Check how many docs fall under different thresholds
    for threshold in [0.50, 0.60, 0.70, 0.80, 0.90]:
        above = [r for r in results if r['mean_conf'] >= threshold]
        below = [r for r in results if r['mean_conf'] < threshold]
        
        # Check quality mix
        good_above = len([r for r in above if r in good])
        good_below = len([r for r in below if r in good])
        poor_above = len([r for r in above if r in poor])
        poor_below = len([r for r in below if r in poor])
        
        print(f"\nThreshold {threshold:.2f}:")
        print(f"  Above: {len(above)} docs (good={good_above}, poor={poor_above})")
        print(f"  Below: {len(below)} docs (good={good_below}, poor={poor_below})")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
