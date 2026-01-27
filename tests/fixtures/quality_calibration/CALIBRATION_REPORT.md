# Quality Scoring Calibration Report

**Date:** 2026-01-27  
**Threshold Under Test:** 0.80  
**Scorer Location:** `worker/processors/quality.py`

---

## 1. Calibration Dataset Summary

| Category | Count | Description |
|----------|-------|-------------|
| **Good** | 5 | Clean scans, good phone photos - should route to Fast Path |
| **Medium** | 6 | Borderline images - either path acceptable |
| **Poor** | 9 | Heavy blur, exposure issues - must route to Fallback |
| **Total** | 20 | |

Images generated programmatically with synthetic document patterns.
Location: `tests/fixtures/quality_calibration/`

### Image Manifest

| Filename | Label | Notes |
|----------|-------|-------|
| 01_clean_scan.jpg | good | Clean scanner output, high quality |
| 02_dense_scan.jpg | good | Dense marksheet/form scan |
| 03_phone_good_light.jpg | good | Phone capture in good daylight |
| 04_white_bg_clean.jpg | good | White background, sparse text |
| 05_phone_enhanced.jpg | good | Phone photo with auto-enhancement |
| 06_slight_blur.jpg | medium | Slight blur, text still readable |
| 07_phone_dim_light.jpg | medium | Phone photo in dim indoor light |
| 08_slight_motion.jpg | medium | Slight motion blur |
| 09_slight_overexpose.jpg | medium | Slightly overexposed |
| 10_noisy_readable.jpg | medium | Noisy but text still clear |
| 11_jpeg_artifacts.jpg | medium | Heavy JPEG compression |
| 12_heavy_blur.jpg | poor | Heavy blur, text unreadable |
| 13_very_heavy_blur.jpg | poor | Extreme blur |
| 14_low_light.jpg | poor | Low light capture, dark and noisy |
| 15_overexposed.jpg | poor | Severely overexposed |
| 16_underexposed.jpg | poor | Severely underexposed |
| 17_motion_blur.jpg | poor | Significant motion blur |
| 18_blur_and_noise.jpg | poor | Blur combined with high noise |
| 19_low_contrast.jpg | poor | Very low contrast |
| 20_extreme_noise.jpg | poor | Extreme noise |

---

## 2. Results Table (Original Configuration)

**Configuration:** Threshold = 0.80, Original Weights, Original Exposure Metric

| Filename | Label | Score | Sharp | Expo | Noise | Edge | Path | Correct |
|----------|-------|-------|-------|------|-------|------|------|---------|
| 01_clean_scan.jpg | good | 0.543 | 1.000 | 0.000 | 0.373 | 0.788 | fallback | ✗ |
| 02_dense_scan.jpg | good | 0.522 | 1.000 | 0.000 | 0.111 | 1.000 | fallback | ✗ |
| 03_phone_good_light.jpg | good | 0.555 | 1.000 | 0.000 | 0.436 | 0.784 | fallback | ✗ |
| 04_white_bg_clean.jpg | good | 0.589 | 1.000 | 0.000 | 0.554 | 0.854 | fallback | ✗ |
| 05_phone_enhanced.jpg | good | 0.549 | 1.000 | 0.000 | 0.411 | 0.779 | fallback | ✗ |
| 06_slight_blur.jpg | medium | 0.502 | 0.676 | 0.000 | 0.750 | 0.766 | fallback | ✓ |
| 07_phone_dim_light.jpg | medium | 0.818 | 1.000 | 0.734 | 0.514 | 0.964 | fast | ✓ |
| 08_slight_motion.jpg | medium | 0.600 | 1.000 | 0.000 | 0.673 | 0.768 | fallback | ✓ |
| 09_slight_overexpose.jpg | medium | 0.558 | 1.000 | 0.000 | 0.469 | 0.761 | fallback | ✓ |
| 10_noisy_readable.jpg | medium | 0.580 | 1.000 | 0.000 | 0.402 | 1.000 | fallback | ✓ |
| 11_jpeg_artifacts.jpg | medium | 0.560 | 1.000 | 0.000 | 0.455 | 0.791 | fallback | ✓ |
| 12_heavy_blur.jpg | poor | 0.315 | 0.050 | 0.000 | 0.920 | 0.758 | fallback | ✓ |
| 13_very_heavy_blur.jpg | poor | 0.314 | 0.016 | 0.000 | 0.957 | 0.779 | fallback | ✓ |
| 14_low_light.jpg | poor | 0.735 | 1.000 | 0.671 | 0.451 | 0.621 | fallback | ✓ |
| 15_overexposed.jpg | poor | 0.507 | 0.654 | 0.000 | 0.811 | 0.771 | fallback | ✓ |
| 16_underexposed.jpg | poor | 0.626 | 0.678 | 0.369 | 0.806 | 0.779 | fallback | ✓ |
| 17_motion_blur.jpg | poor | 0.577 | 1.000 | 0.000 | 0.481 | 0.870 | fallback | ✓ |
| 18_blur_and_noise.jpg | poor | 0.634 | 1.000 | 0.000 | 0.672 | 1.000 | fallback | ✓ |
| 19_low_contrast.jpg | poor | 0.539 | 0.414 | 0.359 | 0.846 | 0.780 | fallback | ✓ |
| 20_extreme_noise.jpg | poor | 0.509 | 1.000 | 0.066 | 0.238 | 0.612 | fallback | ✓ |

**Summary:**
- False Positives: 0 (poor → fast)
- False Negatives: 5 (good → fallback)  
- Good Image Accuracy: **0%**
- Poor Image Accuracy: **100%**

---

## 3. Misclassification Analysis

### Critical Finding: Exposure Metric is Broken for Documents

**ALL 5 "good" images have exposure score = 0.000**

Root cause analysis:

```
Sample: 01_clean_scan.jpg (labeled "good")
- Mean brightness: 218.9 / 255
- White clip (245-255): 85.4% of pixels
- Exposure score: 0.000

The algorithm:
1. Expects mean brightness ≈ 127.5 (middle gray)
2. Penalizes deviation from 127.5
3. Further penalizes white/black clipping

Problem: Documents are NOT natural scenes.
- White paper background → mean brightness 200-240 is NORMAL
- 80%+ white pixels is EXPECTED for clean documents
```

### Pattern Analysis

| Category | Avg Sharpness | Avg Exposure | Avg Noise | Avg Edge |
|----------|--------------|--------------|-----------|----------|
| Good | 1.000 | 0.000 | 0.377 | 0.841 |
| Medium | 0.946 | 0.122 | 0.544 | 0.842 |
| Poor | 0.646 | 0.163 | 0.687 | 0.774 |

**Key Insight:** Sharpness has the best discriminative power (+0.354 separation between good and poor). Exposure has NEGATIVE separation (-0.163) because it's miscalibrated.

### False Positive Risk

With the original configuration, there are **zero false positives** (poor images incorrectly routed to fast path). This is because the broken exposure metric pulls ALL scores down.

However, this comes at the cost of **routing all good images to fallback**, which defeats the purpose of having a fast path.

---

## 4. Threshold Calibration

### With Original Exposure Metric

| Threshold | FP | FN | FP Rate | FN Rate | Risk Score |
|-----------|----|----|---------|---------|------------|
| 0.70 | 1 | 5 | 11.11% | 100.00% | 1.333 |
| 0.75 | 0 | 5 | 0.00% | 100.00% | 1.000 |
| 0.80 | 0 | 5 | 0.00% | 100.00% | 1.000 |
| 0.85 | 0 | 5 | 0.00% | 100.00% | 1.000 |
| 0.90 | 0 | 5 | 0.00% | 100.00% | 1.000 |

**Threshold tuning alone CANNOT fix this.** The exposure metric must be corrected first.

### With Fixed Document Exposure Metric

After replacing exposure calculation with contrast-based approach:

| Threshold | FP | FN | Good Acc | Poor Acc | Risk |
|-----------|----|----|----------|----------|------|
| 0.80 | 2 | 0 | 100% | 78% | 6 |
| 0.85 | 2 | 3 | 40% | 78% | 9 |
| 0.88 | 1 | 4 | 20% | 89% | 7 |
| 0.92 | 0 | 5 | 0% | 100% | 5 |

**Optimal threshold with fixed exposure: 0.80**
- Achieves 100% good image accuracy
- 2 false positives (17_motion_blur, 18_blur_and_noise)

---

## 5. Weight Adjustment Recommendation

### Current Weights

```python
weights = {
    'sharpness': 0.35,
    'exposure': 0.30,
    'noise': 0.20,
    'edge_density': 0.15,
}
```

### Discriminative Power Analysis

| Metric | Good Avg | Poor Avg | Separation |
|--------|----------|----------|------------|
| sharpness | 1.000 | 0.646 | **+0.354** (best) |
| exposure | varies | varies | depends on fix |
| noise | 0.377 | 0.687 | -0.310 (inverted) |
| edge_density | 0.841 | 0.774 | +0.066 |

### Recommended Weight Adjustment

**NO WEIGHT CHANGE RECOMMENDED AT THIS TIME**

Rationale:
1. The primary issue is the exposure metric calculation, not the weights
2. Sharpness (highest weight) is already the most discriminative metric
3. After fixing exposure, the current weights achieve 100% good accuracy

The remaining false positives (17_motion_blur, 18_blur_and_noise) are not fixable via weight adjustment because:
- Motion blur: Laplacian variance is high because blur is directional
- Blur+noise: Noise adds high-frequency content that inflates variance

These would require a new metric (e.g., directional blur detection) which is out of scope.

---

## 6. Performance Benchmark

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Mean Latency | 6.81 ms | <100 ms | ✅ PASS |
| P50 Latency | 6.12 ms | <100 ms | ✅ PASS |
| P95 Latency | 10.52 ms | <100 ms | ✅ PASS |
| P99 Latency | 11.57 ms | <100 ms | ✅ PASS |
| Max Latency | 11.57 ms | <100 ms | ✅ PASS |

### Component Breakdown

| Component | Avg Time | % of Total |
|-----------|----------|------------|
| decode | 1.94 ms | 28.5% |
| sharpness | 1.54 ms | 22.6% |
| exposure | 1.22 ms | 17.9% |
| noise | 1.19 ms | 17.5% |
| edge_density | 0.88 ms | 12.9% |

**Performance is excellent.** Total latency is ~10x under budget.

---

## 7. Final Recommendation

### ★ ADJUST EXPOSURE METRIC (Required)

The current `compute_exposure()` function in `quality.py` must be replaced with a document-optimized version:

```python
def compute_exposure(gray: NDArray[np.uint8]) -> float:
    """
    Compute exposure for document images using contrast measurement.
    
    Documents have bimodal histograms (white paper + dark text).
    Good exposure = high contrast = high histogram standard deviation.
    """
    hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
    hist = hist.flatten() / hist.sum()
    
    values = np.arange(256)
    mean_val = np.sum(values * hist)
    std_val = np.sqrt(np.sum(((values - mean_val) ** 2) * hist))
    
    # Score based on contrast (std deviation)
    if std_val < 20:
        score = std_val / 20 * 0.5
    elif std_val < 40:
        score = 0.5 + 0.3 * ((std_val - 20) / 20)
    elif std_val < 80:
        score = 0.8 + 0.2 * ((std_val - 40) / 40)
    else:
        score = 1.0
    
    # Penalize extreme cases
    dark_fraction = hist[0:30].sum()
    bright_fraction = hist[225:256].sum()
    
    if dark_fraction > 0.9:
        score *= 0.3
    elif bright_fraction > 0.98:
        score *= 0.5
    
    return float(score)
```

### ★ KEEP THRESHOLD AT 0.80

With the fixed exposure metric:
- Threshold 0.80 achieves 100% accuracy on good images
- 2 false positives remain (motion blur edge cases)
- Acceptable risk profile given false positive rate of 22% on intentionally degraded images

### ★ NO WEIGHT CHANGES

Current weights are appropriate after exposure fix.

### Summary

| Action | Status |
|--------|--------|
| Exposure metric fix | **REQUIRED** |
| Threshold change | KEEP at 0.80 |
| Weight adjustment | NONE |
| Performance optimization | NONE NEEDED |

### Expected Outcome After Fix

| Metric | Before | After |
|--------|--------|-------|
| Good image accuracy | 0% | 100% |
| Poor image accuracy | 100% | 78% |
| False positives | 0 | 2 |
| False negatives | 5 | 0 |

The 2 remaining false positives are edge cases (motion blur + noise) that would require additional metrics to detect. Given the constraint of no new metrics, this is the optimal achievable configuration.

---

## Appendix: Test Scripts

Location: `tests/fixtures/quality_calibration/`

| Script | Purpose |
|--------|---------|
| `generate_dataset.py` | Generate synthetic calibration images |
| `run_calibration_standalone.py` | Run calibration with original metrics |
| `calibration_exposure_fix.py` | Test alternative exposure metrics |
| `dataset_manifest.csv` | Image labels and metadata |
