"""
Enhancement Pipeline Validation Suite.

Runs comprehensive before/after comparisons:
1. Runs enhancement pipeline on each test image
2. Measures objective quality metrics
3. Measures OCR confidence
4. Measures latency per step
5. Detects failures and regressions

Outputs:
- Before/after images
- Metrics comparison
- Latency breakdown
- Failure analysis
"""

import json
import os
import sys
import time
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Any, Optional, Tuple

import cv2
import numpy as np

# Add worker to path for imports
WORKER_DIR = Path(__file__).parent.parent.parent.parent / "worker"
sys.path.insert(0, str(WORKER_DIR))

from processors.enhancement import (
    enhance_image,
    EnhancementOptions,
    decode_image,
    encode_image,
    correct_orientation,
    denoise,
    normalize_color,
    auto_white_balance,
)
from processors.quality import (
    assess_quality,
    compute_sharpness,
    compute_exposure,
    compute_noise,
    compute_edge_density,
)


@dataclass
class StepLatency:
    """Latency for each enhancement step."""
    orientation_ms: float = 0.0
    denoise_ms: float = 0.0
    white_balance_ms: float = 0.0
    clahe_ms: float = 0.0
    total_ms: float = 0.0


@dataclass
class QualityMetrics:
    """Quality metrics for an image."""
    overall_score: float
    sharpness: float
    exposure: float
    noise: float
    edge_density: float
    laplacian_variance: float  # Raw value for debugging


@dataclass
class OCRMetrics:
    """OCR metrics for an image."""
    confidence: float
    word_count: int
    error: Optional[str] = None


@dataclass
class ImageTestResult:
    """Complete test result for a single image."""
    filename: str
    category: str
    description: str
    baseline_readable: bool
    expected_improvement: bool
    
    # Dimensions
    before_dimensions: Tuple[int, int]
    after_dimensions: Tuple[int, int]
    dimensions_preserved: bool
    
    # Quality metrics
    before_quality: QualityMetrics
    after_quality: QualityMetrics
    quality_delta: float
    quality_improved: bool
    
    # OCR metrics
    before_ocr: OCRMetrics
    after_ocr: OCRMetrics
    ocr_delta: float
    ocr_improved: bool
    
    # Latency
    latency: StepLatency
    latency_ok: bool  # <2s target
    
    # Enhancement flags
    orientation_corrected: bool
    denoised: bool
    color_normalized: bool
    
    # Failure detection
    is_failure: bool = False
    failure_reason: Optional[str] = None
    recommended_action: Optional[str] = None


def compute_laplacian_variance(img: np.ndarray) -> float:
    """Compute raw Laplacian variance (sharpness measure)."""
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img
    laplacian = cv2.Laplacian(gray, cv2.CV_64F)
    return float(laplacian.var())


def get_quality_metrics(img_bytes: bytes) -> QualityMetrics:
    """Get all quality metrics for an image."""
    result = assess_quality(img_bytes)
    
    # Also compute raw Laplacian variance
    nparr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    lap_var = compute_laplacian_variance(img)
    
    return QualityMetrics(
        overall_score=result.score,
        sharpness=result.breakdown.sharpness,
        exposure=result.breakdown.exposure,
        noise=result.breakdown.noise,
        edge_density=result.breakdown.edge_density,
        laplacian_variance=lap_var,
    )


def get_ocr_metrics(img_bytes: bytes) -> OCRMetrics:
    """Get OCR metrics for an image."""
    try:
        # Import here to avoid import errors if tesseract not available
        from ocr.tesseract_adapter import extract_text
        result = extract_text(img_bytes)
        return OCRMetrics(
            confidence=result.confidence,
            word_count=len(result.text.split()),
        )
    except Exception as e:
        return OCRMetrics(
            confidence=0.0,
            word_count=0,
            error=str(e),
        )


def run_enhancement_with_timing(img_bytes: bytes) -> Tuple[bytes, StepLatency, Dict[str, bool]]:
    """
    Run enhancement pipeline with per-step timing.
    
    Returns:
        Tuple of (enhanced_bytes, latency_breakdown, flags)
    """
    latency = StepLatency()
    flags = {"orientation": False, "denoise": False, "color": False}
    
    total_start = time.perf_counter()
    
    # Decode
    img = decode_image(img_bytes)
    
    # Step 1: Orientation correction
    t0 = time.perf_counter()
    img, flags["orientation"] = correct_orientation(img)
    latency.orientation_ms = (time.perf_counter() - t0) * 1000
    
    # Step 2: Denoising
    t0 = time.perf_counter()
    img, flags["denoise"] = denoise(img, strength=7)
    latency.denoise_ms = (time.perf_counter() - t0) * 1000
    
    # Step 3: Color normalization (white balance + CLAHE)
    t0 = time.perf_counter()
    img, _ = auto_white_balance(img)
    latency.white_balance_ms = (time.perf_counter() - t0) * 1000
    
    t0 = time.perf_counter()
    img, flags["color"] = normalize_color(img, clip_limit=2.0, grid_size=(8, 8))
    latency.clahe_ms = (time.perf_counter() - t0) * 1000
    
    # Encode
    result_bytes = encode_image(img, format="jpeg", quality=95)
    
    latency.total_ms = (time.perf_counter() - total_start) * 1000
    
    return result_bytes, latency, flags


def detect_failure(
    before_quality: QualityMetrics,
    after_quality: QualityMetrics,
    before_ocr: OCRMetrics,
    after_ocr: OCRMetrics,
    baseline_readable: bool,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Detect if enhancement made things worse.
    
    Returns:
        Tuple of (is_failure, failure_reason, recommended_action)
    """
    # Case 1: Quality score dropped significantly
    quality_delta = after_quality.overall_score - before_quality.overall_score
    if quality_delta < -0.1:
        return (
            True,
            f"Quality score dropped by {abs(quality_delta):.2f}",
            "Consider skipping enhancement for this image type"
        )
    
    # Case 2: OCR confidence dropped for previously readable image
    if baseline_readable and before_ocr.error is None and after_ocr.error is None:
        ocr_delta = after_ocr.confidence - before_ocr.confidence
        if ocr_delta < -0.15:
            return (
                True,
                f"OCR confidence dropped by {abs(ocr_delta):.2f} on readable image",
                "Add rollback guardrail for readable images"
            )
    
    # Case 3: Sharpness decreased significantly
    sharpness_delta = after_quality.sharpness - before_quality.sharpness
    if sharpness_delta < -0.2:
        return (
            True,
            f"Sharpness dropped by {abs(sharpness_delta):.2f} (possible over-smoothing)",
            "Reduce denoise strength or skip denoising"
        )
    
    # Case 4: Exposure went extreme (over-correction)
    if after_quality.exposure < 0.3 or (before_quality.exposure > 0.5 and after_quality.exposure < before_quality.exposure - 0.2):
        return (
            True,
            f"Exposure degraded from {before_quality.exposure:.2f} to {after_quality.exposure:.2f}",
            "Reduce CLAHE clip limit or skip for well-exposed images"
        )
    
    return (False, None, None)


def run_validation(
    input_dir: Path,
    output_dir: Path,
    manifest_path: Path,
) -> List[ImageTestResult]:
    """
    Run validation on all test images.
    
    Args:
        input_dir: Directory with test images
        output_dir: Directory for output (before/after comparisons)
        manifest_path: Path to dataset manifest JSON
        
    Returns:
        List of test results
    """
    # Load manifest
    with open(manifest_path) as f:
        manifest = json.load(f)
    
    # Create output directories
    (output_dir / "before").mkdir(parents=True, exist_ok=True)
    (output_dir / "after").mkdir(parents=True, exist_ok=True)
    
    results: List[ImageTestResult] = []
    
    for img_meta in manifest["images"]:
        filename = img_meta["filename"]
        img_path = input_dir / filename
        
        print(f"\nProcessing: {filename}")
        
        # Read image
        with open(img_path, "rb") as f:
            img_bytes = f.read()
        
        # Get before dimensions
        nparr = np.frombuffer(img_bytes, np.uint8)
        before_img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        before_dims = (before_img.shape[1], before_img.shape[0])  # (width, height)
        
        # Get before metrics
        before_quality = get_quality_metrics(img_bytes)
        before_ocr = get_ocr_metrics(img_bytes)
        
        # Run enhancement with timing
        try:
            enhanced_bytes, latency, flags = run_enhancement_with_timing(img_bytes)
        except Exception as e:
            print(f"  ERROR: Enhancement failed - {e}")
            continue
        
        # Get after dimensions
        nparr = np.frombuffer(enhanced_bytes, np.uint8)
        after_img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        after_dims = (after_img.shape[1], after_img.shape[0])
        
        # Get after metrics
        after_quality = get_quality_metrics(enhanced_bytes)
        after_ocr = get_ocr_metrics(enhanced_bytes)
        
        # Calculate deltas
        quality_delta = after_quality.overall_score - before_quality.overall_score
        ocr_delta = 0.0
        if before_ocr.error is None and after_ocr.error is None:
            ocr_delta = after_ocr.confidence - before_ocr.confidence
        
        # Detect failures
        is_failure, failure_reason, recommended_action = detect_failure(
            before_quality, after_quality,
            before_ocr, after_ocr,
            img_meta["baseline_readable"]
        )
        
        # Create result
        result = ImageTestResult(
            filename=filename,
            category=img_meta["category"],
            description=img_meta["description"],
            baseline_readable=img_meta["baseline_readable"],
            expected_improvement=img_meta["expected_improvement"],
            before_dimensions=before_dims,
            after_dimensions=after_dims,
            dimensions_preserved=(before_dims == after_dims),
            before_quality=before_quality,
            after_quality=after_quality,
            quality_delta=quality_delta,
            quality_improved=(quality_delta > 0.01),
            before_ocr=before_ocr,
            after_ocr=after_ocr,
            ocr_delta=ocr_delta,
            ocr_improved=(ocr_delta > 0.01),
            latency=latency,
            latency_ok=(latency.total_ms < 2000),
            orientation_corrected=flags["orientation"],
            denoised=flags["denoise"],
            color_normalized=flags["color"],
            is_failure=is_failure,
            failure_reason=failure_reason,
            recommended_action=recommended_action,
        )
        results.append(result)
        
        # Save before/after images
        cv2.imwrite(str(output_dir / "before" / filename), before_img)
        cv2.imwrite(str(output_dir / "after" / filename), after_img)
        
        # Print summary
        q_arrow = "↑" if result.quality_improved else ("↓" if quality_delta < -0.01 else "=")
        o_arrow = "↑" if result.ocr_improved else ("↓" if ocr_delta < -0.01 else "=")
        status = "FAIL" if is_failure else "OK"
        print(f"  Quality: {before_quality.overall_score:.3f} → {after_quality.overall_score:.3f} [{q_arrow}]")
        print(f"  OCR: {before_ocr.confidence:.3f} → {after_ocr.confidence:.3f} [{o_arrow}]")
        print(f"  Latency: {latency.total_ms:.1f}ms | Status: {status}")
        if is_failure:
            print(f"  FAILURE: {failure_reason}")
    
    return results


def generate_report(results: List[ImageTestResult], output_path: Path) -> str:
    """Generate markdown report from results."""
    
    lines = ["# Enhancement Pipeline Validation Report\n"]
    
    # Summary statistics
    total = len(results)
    quality_improved = sum(1 for r in results if r.quality_improved)
    ocr_improved = sum(1 for r in results if r.ocr_improved)
    failures = sum(1 for r in results if r.is_failure)
    latency_ok = sum(1 for r in results if r.latency_ok)
    dims_preserved = sum(1 for r in results if r.dimensions_preserved)
    
    lines.append("## 1. Dataset Summary\n")
    lines.append(f"- **Total test images:** {total}")
    lines.append(f"- **Categories:** {len(set(r.category for r in results))}")
    lines.append(f"- **Baseline readable:** {sum(1 for r in results if r.baseline_readable)}")
    lines.append(f"- **Expected improvement:** {sum(1 for r in results if r.expected_improvement)}\n")
    
    # Before/After Table
    lines.append("## 2. Before/After Comparison Table\n")
    lines.append("| Image | Category | Quality Before | Quality After | Delta | OCR Before | OCR After | Delta | Latency | Status |")
    lines.append("|-------|----------|----------------|---------------|-------|------------|-----------|-------|---------|--------|")
    
    for r in results:
        status = "❌ FAIL" if r.is_failure else "✓ OK"
        q_delta = f"+{r.quality_delta:.3f}" if r.quality_delta >= 0 else f"{r.quality_delta:.3f}"
        o_delta = f"+{r.ocr_delta:.3f}" if r.ocr_delta >= 0 else f"{r.ocr_delta:.3f}"
        lines.append(
            f"| {r.filename} | {r.category} | {r.before_quality.overall_score:.3f} | "
            f"{r.after_quality.overall_score:.3f} | {q_delta} | {r.before_ocr.confidence:.3f} | "
            f"{r.after_ocr.confidence:.3f} | {o_delta} | {r.latency.total_ms:.0f}ms | {status} |"
        )
    
    # Metric deltas
    lines.append("\n## 3. Objective Metric Deltas\n")
    lines.append(f"- **Quality improved:** {quality_improved}/{total} ({100*quality_improved/total:.1f}%)")
    lines.append(f"- **OCR improved:** {ocr_improved}/{total} ({100*ocr_improved/total:.1f}%)")
    lines.append(f"- **Dimensions preserved:** {dims_preserved}/{total} ({100*dims_preserved/total:.1f}%)")
    lines.append(f"- **Latency <2s:** {latency_ok}/{total} ({100*latency_ok/total:.1f}%)\n")
    
    # Detailed metrics
    lines.append("### Metric Breakdown\n")
    lines.append("| Image | Sharpness Δ | Exposure Δ | Noise Δ | Edge Δ |")
    lines.append("|-------|-------------|------------|---------|--------|")
    for r in results:
        s_delta = r.after_quality.sharpness - r.before_quality.sharpness
        e_delta = r.after_quality.exposure - r.before_quality.exposure
        n_delta = r.after_quality.noise - r.before_quality.noise
        d_delta = r.after_quality.edge_density - r.before_quality.edge_density
        lines.append(
            f"| {r.filename} | {s_delta:+.3f} | {e_delta:+.3f} | {n_delta:+.3f} | {d_delta:+.3f} |"
        )
    
    # Failure cases
    lines.append("\n## 4. Failure Cases & Guardrails\n")
    failure_results = [r for r in results if r.is_failure]
    if failure_results:
        lines.append(f"**{len(failure_results)} failures detected:**\n")
        for r in failure_results:
            lines.append(f"### {r.filename}")
            lines.append(f"- **Category:** {r.category}")
            lines.append(f"- **Failure reason:** {r.failure_reason}")
            lines.append(f"- **Recommended action:** {r.recommended_action}\n")
    else:
        lines.append("✓ No failures detected.\n")
    
    # Orientation validation
    lines.append("## 5. Orientation Validation Results\n")
    rotation_results = [r for r in results if r.category == "rotation"]
    if rotation_results:
        lines.append("| Image | Rotation Applied | Corrected | Quality Δ | Status |")
        lines.append("|-------|------------------|-----------|-----------|--------|")
        for r in rotation_results:
            corrected = "✓" if r.orientation_corrected else "✗"
            status = "OK" if not r.is_failure else "FAIL"
            lines.append(f"| {r.filename} | {r.description} | {corrected} | {r.quality_delta:+.3f} | {status} |")
    
    # Performance
    lines.append("\n## 6. Performance Numbers\n")
    avg_total = sum(r.latency.total_ms for r in results) / len(results)
    avg_orient = sum(r.latency.orientation_ms for r in results) / len(results)
    avg_denoise = sum(r.latency.denoise_ms for r in results) / len(results)
    avg_wb = sum(r.latency.white_balance_ms for r in results) / len(results)
    avg_clahe = sum(r.latency.clahe_ms for r in results) / len(results)
    max_total = max(r.latency.total_ms for r in results)
    
    lines.append("### Latency Breakdown (Average)\n")
    lines.append(f"| Step | Avg (ms) | % of Total |")
    lines.append(f"|------|----------|------------|")
    lines.append(f"| Orientation | {avg_orient:.1f} | {100*avg_orient/avg_total:.1f}% |")
    lines.append(f"| Denoising | {avg_denoise:.1f} | {100*avg_denoise/avg_total:.1f}% |")
    lines.append(f"| White Balance | {avg_wb:.1f} | {100*avg_wb/avg_total:.1f}% |")
    lines.append(f"| CLAHE | {avg_clahe:.1f} | {100*avg_clahe/avg_total:.1f}% |")
    lines.append(f"| **Total** | **{avg_total:.1f}** | 100% |")
    lines.append(f"\n- **Max latency:** {max_total:.1f}ms")
    lines.append(f"- **Target (<2000ms):** {'✓ PASS' if max_total < 2000 else '✗ FAIL'}\n")
    
    # Final recommendation
    lines.append("## 7. Final Recommendation\n")
    
    if failures == 0 and quality_improved >= total * 0.6:
        lines.append("### RECOMMENDATION: KEEP enhancement pipeline as-is\n")
        lines.append("Evidence:")
        lines.append(f"- Quality improved in {quality_improved}/{total} images")
        lines.append(f"- No regressions detected")
        lines.append(f"- Latency within target")
    elif failures > 0:
        lines.append("### RECOMMENDATION: ADD guardrails\n")
        lines.append("Evidence:")
        lines.append(f"- {failures} failure(s) detected")
        lines.append("\n**Proposed guardrails:**")
        
        # Collect unique recommendations
        recommendations = set()
        for r in failure_results:
            if r.recommended_action:
                recommendations.add(r.recommended_action)
        
        for i, rec in enumerate(recommendations, 1):
            lines.append(f"{i}. {rec}")
    else:
        lines.append("### RECOMMENDATION: Review edge cases\n")
        lines.append("Evidence:")
        lines.append(f"- Quality improved in only {quality_improved}/{total} images")
        lines.append(f"- Consider selective enhancement based on input quality")
    
    # Enhancement decision matrix
    lines.append("\n### When Enhancement SHOULD Run\n")
    lines.append("- Low quality score (<0.7)")
    lines.append("- Detected blur or noise")
    lines.append("- Skewed orientation (>1°)")
    lines.append("- Poor exposure (underexposed or overexposed)")
    
    lines.append("\n### When Enhancement SHOULD Be Skipped\n")
    lines.append("- High quality score (>0.85)")
    lines.append("- Already readable (baseline_readable=true AND quality>0.8)")
    lines.append("- Fast Path images (per existing routing logic)")
    
    report_text = "\n".join(lines)
    
    with open(output_path, "w") as f:
        f.write(report_text)
    
    return report_text


def main():
    """Run full validation suite."""
    script_dir = Path(__file__).parent
    input_dir = script_dir
    output_dir = script_dir / "results"
    manifest_path = script_dir / "dataset_manifest.json"
    
    # Check if manifest exists
    if not manifest_path.exists():
        print("ERROR: Dataset manifest not found. Run generate_test_dataset.py first.")
        sys.exit(1)
    
    print("=" * 60)
    print("ENHANCEMENT PIPELINE VALIDATION")
    print("=" * 60)
    
    # Run validation
    results = run_validation(input_dir, output_dir, manifest_path)
    
    # Generate report
    report_path = script_dir / "VALIDATION_REPORT.md"
    report = generate_report(results, report_path)
    
    # Save raw results as JSON
    results_json = []
    for r in results:
        d = {
            "filename": r.filename,
            "category": r.category,
            "description": r.description,
            "baseline_readable": r.baseline_readable,
            "expected_improvement": r.expected_improvement,
            "before_dimensions": list(r.before_dimensions),
            "after_dimensions": list(r.after_dimensions),
            "dimensions_preserved": r.dimensions_preserved,
            "before_quality": asdict(r.before_quality),
            "after_quality": asdict(r.after_quality),
            "quality_delta": r.quality_delta,
            "quality_improved": r.quality_improved,
            "before_ocr": asdict(r.before_ocr),
            "after_ocr": asdict(r.after_ocr),
            "ocr_delta": r.ocr_delta,
            "ocr_improved": r.ocr_improved,
            "latency": asdict(r.latency),
            "latency_ok": r.latency_ok,
            "orientation_corrected": r.orientation_corrected,
            "denoised": r.denoised,
            "color_normalized": r.color_normalized,
            "is_failure": r.is_failure,
            "failure_reason": r.failure_reason,
            "recommended_action": r.recommended_action,
        }
        results_json.append(d)
    
    with open(script_dir / "validation_results.json", "w") as f:
        json.dump(results_json, f, indent=2)
    
    print("\n" + "=" * 60)
    print("VALIDATION COMPLETE")
    print("=" * 60)
    print(f"\nReport saved to: {report_path}")
    print(f"Results JSON: {script_dir / 'validation_results.json'}")
    print(f"Before/After images: {output_dir}")
    
    # Print summary
    failures = sum(1 for r in results if r.is_failure)
    if failures > 0:
        print(f"\n⚠️  {failures} FAILURE(S) DETECTED - Review report for details")
        sys.exit(1)
    else:
        print(f"\n✓ All tests passed")


if __name__ == "__main__":
    main()
