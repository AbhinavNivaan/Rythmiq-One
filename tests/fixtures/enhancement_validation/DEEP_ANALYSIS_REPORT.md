# Enhancement Pipeline Deep Analysis Report

## Executive Summary

⚠️ **ISSUES DETECTED** - Enhancement pipeline needs guardrails

- **OCR Regressions:** 2/16 images
- **Quality Regressions:** 2/16 images
- **Dimension Changes:** 3/16 images
- **Guardrails Recommended:** 3

---

## 1. OCR Regressions (CRITICAL)

| Image | Baseline Readable | OCR Before | OCR After | Delta | Severity |
|-------|-------------------|------------|-----------|-------|----------|
| 02_slight_blur.jpg | True | 0.835 | 0.731 | -0.104 | **WARNING** |
| 14_lowlight_blur.jpg | False | 0.953 | 0.566 | -0.387 | **CRITICAL** |

### Root Cause Analysis

OCR regressions occur when enhancement processing:
1. **Over-smooths text edges** via denoising
2. **Alters contrast** inappropriately via CLAHE
3. **Introduces artifacts** from white balance correction

---

## 2. Quality Score Regressions

| Image | Quality Before | Quality After | Delta | Worst Metric |
|-------|----------------|---------------|-------|--------------|
| 05_low_light.jpg | 0.785 | 0.694 | -0.091 | noise_delta: -0.414 |
| 07_light_grain.jpg | 0.789 | 0.726 | -0.063 | edge_delta: -0.346 |

---

## 3. Dimension Preservation

| Image | Before | After | Rotation Case |
|-------|--------|-------|---------------|
| 10_rotation_5deg.jpg | 600x800 | 660x844 | True |
| 11_rotation_neg5deg.jpg | 600x800 | 660x844 | True |
| 15_noise_rotation.jpg | 600x800 | 634x825 | False |

**Note:** Dimension changes for rotation cases are expected when
orientation correction expands canvas to avoid cropping.

---

## 4. Orientation Correction Effectiveness

- **Total rotation test cases:** 5
- **Successfully corrected:** 2
- **Not corrected:** 3

### Per-Image Results

| Image | Description | Corrected | Quality ↑ | OCR ↑ |
|-------|-------------|-----------|-----------|-------|
| 09_rotation_1deg.jpg | 1 degree clockwise rotation | ✗ | ✗ | ✗ |
| 10_rotation_5deg.jpg | 5 degrees clockwise rotation | ✓ | ✓ | ✗ |
| 11_rotation_neg5deg.jpg | 5 degrees counter-clockwise rotation | ✓ | ✓ | ✓ |
| 12_rotation_90deg.jpg | 90 degrees rotation | ✗ | ✗ | ✗ |
| 13_rotation_180deg.jpg | 180 degrees rotation (upside down) | ✗ | ✗ | ✗ |

### Findings

1. **Small skew (1°):** Not corrected - below 1° threshold (correct behavior)
2. **Moderate skew (5°):** Successfully corrected
3. **Large rotations (90°, 180°):** NOT corrected - Hough line method cannot detect

**Issue:** The current implementation uses Hough line analysis which only detects
skew angles. It cannot detect 90° or 180° rotations. These require different
detection methods (OCR text orientation, EXIF data, or content analysis).

---

## 5. Denoising Impact Analysis

| Image | Applied | Noise Before | Noise After | Delta | OCR Improved |
|-------|---------|--------------|-------------|-------|--------------|
| 07_light_grain.jpg | ✗ | 0.065 | 0.049 | -0.016 | ✗ |
| 08_heavy_grain.jpg | ✗ | 0.035 | 0.000 | -0.035 | ✓ |

**Finding:** Denoising reduces noise metric but may not improve OCR.
The noise metric measures high-frequency content which includes both
noise AND fine text details.

---

## 6. Expected vs Actual Improvement

- **Matching expectations:** 9/16
- **Mismatches:** 7/16

### Mismatches

| Image | Expected | Actual | Quality Δ | OCR Δ |
|-------|----------|--------|-----------|-------|
| 04_motion_blur.jpg | improvement | no improvement | +0.001 | +0.000 |
| 06_overexposed.jpg | improvement | no improvement | +0.001 | -0.034 |
| 07_light_grain.jpg | improvement | no improvement | -0.063 | -0.002 |
| 12_rotation_90deg.jpg | improvement | no improvement | +0.002 | -0.004 |
| 13_rotation_180deg.jpg | improvement | no improvement | +0.002 | +0.002 |
| 15_noise_rotation.jpg | improvement | no improvement | -0.031 | -0.048 |
| 16_jpeg_artifacts.jpg | improvement | no improvement | +0.001 | -0.048 |

---

## 7. Recommended Guardrails

### GUARD-001: Skip for high-quality readable images

**Trigger:** `baseline_quality > 0.75 AND baseline_readable = true`

**Action:** Skip denoise and CLAHE steps

**Rationale:** Enhancement degrades OCR for already-readable images

**Affected images:** 02_slight_blur.jpg

### GUARD-002: OCR quality rollback

**Trigger:** `post_enhancement_ocr < pre_enhancement_ocr - 0.10`

**Action:** Rollback to original image

**Rationale:** Enhancement caused significant OCR regression

**Affected images:** 02_slight_blur.jpg, 14_lowlight_blur.jpg

### GUARD-003: Large rotation detection

**Trigger:** `Detected 90°/180° rotation not corrected by Hough lines`

**Action:** Add explicit 90°/180° rotation detection via text orientation

**Rationale:** Current orientation detection only handles skew, not major rotations

**Affected images:** 12_rotation_90deg.jpg, 13_rotation_180deg.jpg

---

## 8. Final Decision Matrix

### Enhancement Decision by Input Type

| Input Condition | Orientation | Denoise | CLAHE | Rationale |
|-----------------|-------------|---------|-------|-----------|
| Clean, readable (score > 0.8) | ✓ | ✗ | ✗ | Risk of degradation |
| Blurry (sharpness < 0.3) | ✓ | ✗ | ✓ | CLAHE helps, denoise hurts |
| Noisy (noise < 0.5) | ✓ | ✓ | ✗ | Denoise helps |
| Underexposed (exposure < 0.4) | ✓ | ✓ | ✓ | Full enhancement |
| Overexposed (exposure > 0.9) | ✓ | ✗ | ✓ | Careful CLAHE |
| Skewed (1° - 15°) | ✓ | per-above | per-above | Orientation first |
| 90°/180° rotation | ✗* | per-above | per-above | *Needs separate detection |

### Implementation Recommendation

```python
def should_enhance(quality_score: float, baseline_readable: bool) -> dict:
    """Determine which enhancement steps to apply."""
    if baseline_readable and quality_score > 0.8:
        # High quality readable - minimal enhancement
        return {
            "orientation": True,
            "denoise": False,
            "clahe": False,
        }
    elif quality_score < 0.5:
        # Low quality - full enhancement
        return {
            "orientation": True,
            "denoise": True,
            "clahe": True,
        }
    else:
        # Medium quality - selective enhancement
        return {
            "orientation": True,
            "denoise": quality_score < 0.65,
            "clahe": True,
        }
```

---

## 9. Conclusion

### VERDICT: ⚠️ ADD GUARDRAILS

The pipeline shows 3 cases of regression that require guardrails.
Implement the recommended guardrails before production use.

**Priority fixes:**
1. GUARD-001: Skip for high-quality readable images
2. GUARD-002: OCR quality rollback
3. GUARD-003: Large rotation detection
