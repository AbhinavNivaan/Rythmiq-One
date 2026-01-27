#!/usr/bin/env python3
"""
Quality Scoring Calibration Test Script

Runs the existing quality scorer against the calibration dataset and collects:
- Quality scores for each image
- Per-metric breakdowns
- Routing decisions
- Misclassification analysis
- Threshold optimization
- Performance benchmarks
"""

import csv
import importlib.util
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

# Load quality module directly to avoid import conflicts
WORKER_DIR = Path(__file__).parent.parent.parent.parent / "worker"
QUALITY_PATH = WORKER_DIR / "processors" / "quality.py"
ERRORS_PATH = WORKER_DIR / "errors.py"
MODELS_PATH = WORKER_DIR / "models.py"

# Load errors module first
spec = importlib.util.spec_from_file_location("worker_errors", ERRORS_PATH)
errors_module = importlib.util.module_from_spec(spec)
sys.modules["errors"] = errors_module
spec.loader.exec_module(errors_module)

# Load models module
spec = importlib.util.spec_from_file_location("worker_models", MODELS_PATH)
models_module = importlib.util.module_from_spec(spec)
sys.modules["models"] = models_module
spec.loader.exec_module(models_module)

# Load quality module
spec = importlib.util.spec_from_file_location("quality", QUALITY_PATH)
quality_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(quality_module)

# Extract functions from quality module
assess_quality = quality_module.assess_quality
compute_sharpness = quality_module.compute_sharpness
compute_exposure = quality_module.compute_exposure
compute_noise = quality_module.compute_noise
compute_edge_density = quality_module.compute_edge_density
decode_image = quality_module.decode_image
QUALITY_WARNING_THRESHOLD = quality_module.QUALITY_WARNING_THRESHOLD

DATASET_DIR = Path(__file__).parent
DATASET_CSV = DATASET_DIR / "dataset_manifest.csv"

# Current threshold
FAST_PATH_THRESHOLD = 0.80


@dataclass
class CalibrationResult:
    filename: str
    human_label: str
    notes: str
    quality_score: float
    sharpness: float
    exposure: float
    noise: float
    edge_density: float
    expected_path: str
    actual_path: str
    is_correct: bool
    latency_ms: float


def human_label_to_expected_path(label: str) -> str:
    """Map human label to expected routing path."""
    mapping = {
        "good": "fast",
        "medium": "review",
        "poor": "fallback",
    }
    return mapping.get(label, "unknown")


def score_to_actual_path(score: float, threshold: float = FAST_PATH_THRESHOLD) -> str:
    """Map quality score to actual routing path using given threshold."""
    if score >= threshold:
        return "fast"
    else:
        return "fallback"


def load_dataset() -> List[Tuple[str, str, str]]:
    """Load calibration dataset from CSV."""
    dataset = []
    with open(DATASET_CSV, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            dataset.append((row['filename'], row['human_label'], row['notes']))
    return dataset


def run_calibration(threshold: float = FAST_PATH_THRESHOLD) -> List[CalibrationResult]:
    """Run quality assessment on all calibration images."""
    dataset = load_dataset()
    results = []
    
    for filename, human_label, notes in dataset:
        filepath = DATASET_DIR / filename
        
        if not filepath.exists():
            print(f"WARNING: Missing file: {filename}")
            continue
        
        # Load image bytes
        with open(filepath, 'rb') as f:
            image_data = f.read()
        
        # Time the quality assessment
        start = time.perf_counter()
        quality_result = assess_quality(image_data)
        latency_ms = (time.perf_counter() - start) * 1000
        
        # Determine paths
        expected_path = human_label_to_expected_path(human_label)
        actual_path = score_to_actual_path(quality_result.score, threshold)
        
        # Determine correctness
        # For "good" images: actual_path should be "fast"
        # For "poor" images: actual_path should be "fallback"
        # For "medium" images: either path is acceptable (borderline)
        if human_label == "good":
            is_correct = actual_path == "fast"
        elif human_label == "poor":
            is_correct = actual_path == "fallback"
        else:  # medium
            is_correct = True  # Borderline images are always "correct"
        
        results.append(CalibrationResult(
            filename=filename,
            human_label=human_label,
            notes=notes,
            quality_score=quality_result.score,
            sharpness=quality_result.breakdown.sharpness,
            exposure=quality_result.breakdown.exposure,
            noise=quality_result.breakdown.noise,
            edge_density=quality_result.breakdown.edge_density,
            expected_path=expected_path,
            actual_path=actual_path,
            is_correct=is_correct,
            latency_ms=latency_ms,
        ))
    
    return results


def print_results_table(results: List[CalibrationResult]):
    """Print results as a formatted table."""
    print("\n" + "=" * 120)
    print("CALIBRATION RESULTS (Threshold = {:.2f})".format(FAST_PATH_THRESHOLD))
    print("=" * 120)
    
    # Header
    print(f"{'Filename':<28} {'Human':<7} {'Score':>6} {'Sharp':>6} {'Expos':>6} {'Noise':>6} {'Edge':>6} {'Expect':<8} {'Actual':<8} {'OK':<4} {'ms':>6}")
    print("-" * 120)
    
    for r in results:
        ok_mark = "✓" if r.is_correct else "✗"
        print(f"{r.filename:<28} {r.human_label:<7} {r.quality_score:>6.3f} {r.sharpness:>6.3f} {r.exposure:>6.3f} {r.noise:>6.3f} {r.edge_density:>6.3f} {r.expected_path:<8} {r.actual_path:<8} {ok_mark:<4} {r.latency_ms:>6.1f}")
    
    print("-" * 120)


def analyze_misclassifications(results: List[CalibrationResult]):
    """Analyze and categorize misclassifications."""
    print("\n" + "=" * 80)
    print("MISCLASSIFICATION ANALYSIS")
    print("=" * 80)
    
    # Separate by type
    false_positives = []  # Poor image routed to fast path
    false_negatives = []  # Good image routed to fallback
    
    for r in results:
        if not r.is_correct:
            if r.human_label == "poor" and r.actual_path == "fast":
                false_positives.append(r)
            elif r.human_label == "good" and r.actual_path == "fallback":
                false_negatives.append(r)
    
    print(f"\nFalse Positives (DANGEROUS - poor image → fast path): {len(false_positives)}")
    if false_positives:
        for r in false_positives:
            print(f"  • {r.filename}: score={r.quality_score:.3f}")
            print(f"    Sharp={r.sharpness:.3f}, Expo={r.exposure:.3f}, Noise={r.noise:.3f}, Edge={r.edge_density:.3f}")
            print(f"    Notes: {r.notes}")
            # Identify dominant metric causing the issue
            metrics = [
                ("sharpness", r.sharpness, 0.35),
                ("exposure", r.exposure, 0.30),
                ("noise", r.noise, 0.20),
                ("edge_density", r.edge_density, 0.15),
            ]
            # Find which metric contributed most to the high score
            contributions = [(name, val * weight) for name, val, weight in metrics]
            contributions.sort(key=lambda x: x[1], reverse=True)
            print(f"    Highest contributors: {contributions[0][0]}({contributions[0][1]:.3f}), {contributions[1][0]}({contributions[1][1]:.3f})")
    
    print(f"\nFalse Negatives (good image → fallback path): {len(false_negatives)}")
    if false_negatives:
        for r in false_negatives:
            print(f"  • {r.filename}: score={r.quality_score:.3f}")
            print(f"    Sharp={r.sharpness:.3f}, Expo={r.exposure:.3f}, Noise={r.noise:.3f}, Edge={r.edge_density:.3f}")
            print(f"    Notes: {r.notes}")
            # Find which metric dragged down the score
            metrics = [
                ("sharpness", r.sharpness),
                ("exposure", r.exposure),
                ("noise", r.noise),
                ("edge_density", r.edge_density),
            ]
            metrics.sort(key=lambda x: x[1])
            print(f"    Lowest metrics: {metrics[0][0]}({metrics[0][1]:.3f}), {metrics[1][0]}({metrics[1][1]:.3f})")
    
    # Pattern summary
    if false_positives:
        print("\nFalse Positive Patterns:")
        avg_sharp = sum(r.sharpness for r in false_positives) / len(false_positives)
        avg_expo = sum(r.exposure for r in false_positives) / len(false_positives)
        avg_noise = sum(r.noise for r in false_positives) / len(false_positives)
        avg_edge = sum(r.edge_density for r in false_positives) / len(false_positives)
        print(f"  Average metrics: Sharp={avg_sharp:.3f}, Expo={avg_expo:.3f}, Noise={avg_noise:.3f}, Edge={avg_edge:.3f}")
    
    if false_negatives:
        print("\nFalse Negative Patterns:")
        avg_sharp = sum(r.sharpness for r in false_negatives) / len(false_negatives)
        avg_expo = sum(r.exposure for r in false_negatives) / len(false_negatives)
        avg_noise = sum(r.noise for r in false_negatives) / len(false_negatives)
        avg_edge = sum(r.edge_density for r in false_negatives) / len(false_negatives)
        print(f"  Average metrics: Sharp={avg_sharp:.3f}, Expo={avg_expo:.3f}, Noise={avg_noise:.3f}, Edge={avg_edge:.3f}")
    
    return false_positives, false_negatives


def threshold_calibration(results: List[CalibrationResult]):
    """Evaluate different threshold values."""
    print("\n" + "=" * 80)
    print("THRESHOLD CALIBRATION")
    print("=" * 80)
    
    thresholds = [0.70, 0.75, 0.78, 0.80, 0.82, 0.85, 0.88, 0.90]
    
    print(f"\n{'Threshold':>10} {'FP (poor→fast)':>15} {'FN (good→fall)':>15} {'FP Rate':>10} {'FN Rate':>10} {'Risk Score':>12}")
    print("-" * 75)
    
    # Count good and poor images
    good_images = [r for r in results if r.human_label == "good"]
    poor_images = [r for r in results if r.human_label == "poor"]
    
    best_threshold = None
    best_risk = float('inf')
    
    for thresh in thresholds:
        # Recalculate with this threshold
        false_positives = 0
        false_negatives = 0
        
        for r in results:
            actual = score_to_actual_path(r.quality_score, thresh)
            if r.human_label == "poor" and actual == "fast":
                false_positives += 1
            elif r.human_label == "good" and actual == "fallback":
                false_negatives += 1
        
        fp_rate = false_positives / len(poor_images) if poor_images else 0
        fn_rate = false_negatives / len(good_images) if good_images else 0
        
        # Risk score: FP is 3x worse than FN (configurable)
        risk_score = fp_rate * 3.0 + fn_rate * 1.0
        
        if risk_score < best_risk:
            best_risk = risk_score
            best_threshold = thresh
        
        print(f"{thresh:>10.2f} {false_positives:>15} {false_negatives:>15} {fp_rate:>10.2%} {fn_rate:>10.2%} {risk_score:>12.3f}")
    
    print("-" * 75)
    print(f"\nRecommended threshold: {best_threshold:.2f}")
    print(f"  (Risk weighting: FP penalty = 3x, FN penalty = 1x)")
    print(f"  Rationale: False positives are more dangerous - they route bad images to fast path")
    
    return best_threshold


def metric_weight_review(results: List[CalibrationResult], false_positives: List[CalibrationResult], false_negatives: List[CalibrationResult]):
    """Review metric weights if threshold tuning is insufficient."""
    print("\n" + "=" * 80)
    print("METRIC WEIGHT REVIEW")
    print("=" * 80)
    
    # Current weights
    current_weights = {
        'sharpness': 0.35,
        'exposure': 0.30,
        'noise': 0.20,
        'edge_density': 0.15,
    }
    
    print("\nCurrent weights:")
    for metric, weight in current_weights.items():
        print(f"  {metric}: {weight:.2f}")
    
    # Analyze metric distributions
    print("\nMetric statistics by human label:")
    
    for label in ["good", "medium", "poor"]:
        subset = [r for r in results if r.human_label == label]
        if not subset:
            continue
        
        avg_sharp = sum(r.sharpness for r in subset) / len(subset)
        avg_expo = sum(r.exposure for r in subset) / len(subset)
        avg_noise = sum(r.noise for r in subset) / len(subset)
        avg_edge = sum(r.edge_density for r in subset) / len(subset)
        
        print(f"\n  {label.upper()} images (n={len(subset)}):")
        print(f"    Sharpness:    avg={avg_sharp:.3f}, min={min(r.sharpness for r in subset):.3f}, max={max(r.sharpness for r in subset):.3f}")
        print(f"    Exposure:     avg={avg_expo:.3f}, min={min(r.exposure for r in subset):.3f}, max={max(r.exposure for r in subset):.3f}")
        print(f"    Noise:        avg={avg_noise:.3f}, min={min(r.noise for r in subset):.3f}, max={max(r.noise for r in subset):.3f}")
        print(f"    Edge Density: avg={avg_edge:.3f}, min={min(r.edge_density for r in subset):.3f}, max={max(r.edge_density for r in subset):.3f}")
    
    # Identify metrics with best discriminative power
    print("\nDiscriminative power analysis (good vs poor separation):")
    
    good_images = [r for r in results if r.human_label == "good"]
    poor_images = [r for r in results if r.human_label == "poor"]
    
    if good_images and poor_images:
        for metric in ["sharpness", "exposure", "noise", "edge_density"]:
            good_avg = sum(getattr(r, metric) for r in good_images) / len(good_images)
            poor_avg = sum(getattr(r, metric) for r in poor_images) / len(poor_images)
            separation = good_avg - poor_avg
            print(f"  {metric:<15}: good_avg={good_avg:.3f}, poor_avg={poor_avg:.3f}, separation={separation:.3f}")
    
    # Weight adjustment recommendation
    print("\nWeight adjustment recommendation:")
    
    if not false_positives and not false_negatives:
        print("  NO WEIGHT CHANGES NEEDED - threshold tuning is sufficient")
        return None
    
    # If we have issues, suggest adjustments
    # This would be based on observed patterns
    suggested_changes = {}
    
    print("  Based on observed misclassifications, consider:")
    print("  (Maximum allowed change: ±20%)")
    
    return suggested_changes


def performance_benchmark(num_iterations: int = 10):
    """Benchmark quality assessment performance."""
    print("\n" + "=" * 80)
    print("PERFORMANCE BENCHMARK")
    print("=" * 80)
    
    dataset = load_dataset()
    
    # Single image benchmark
    print("\n1. Single Image Latency:")
    single_latencies = []
    
    for filename, _, _ in dataset:
        filepath = DATASET_DIR / filename
        with open(filepath, 'rb') as f:
            image_data = f.read()
        
        # Run multiple iterations per image
        for _ in range(num_iterations):
            start = time.perf_counter()
            assess_quality(image_data)
            latency = (time.perf_counter() - start) * 1000
            single_latencies.append(latency)
    
    single_latencies.sort()
    mean_latency = sum(single_latencies) / len(single_latencies)
    p50_latency = single_latencies[len(single_latencies) // 2]
    p95_latency = single_latencies[int(len(single_latencies) * 0.95)]
    p99_latency = single_latencies[int(len(single_latencies) * 0.99)]
    max_latency = max(single_latencies)
    
    print(f"  Images tested: {len(dataset)}")
    print(f"  Iterations per image: {num_iterations}")
    print(f"  Total measurements: {len(single_latencies)}")
    print(f"  Mean latency:  {mean_latency:.2f} ms")
    print(f"  P50 latency:   {p50_latency:.2f} ms")
    print(f"  P95 latency:   {p95_latency:.2f} ms")
    print(f"  P99 latency:   {p99_latency:.2f} ms")
    print(f"  Max latency:   {max_latency:.2f} ms")
    
    target = 100.0
    if p95_latency < target:
        print(f"\n  ✓ PASS: P95 latency ({p95_latency:.2f}ms) is under {target}ms target")
    else:
        print(f"\n  ✗ FAIL: P95 latency ({p95_latency:.2f}ms) exceeds {target}ms target")
    
    # Batch benchmark
    print("\n2. Batch Processing (10 images):")
    
    # Prepare batch
    batch_data = []
    for filename, _, _ in dataset[:10]:
        filepath = DATASET_DIR / filename
        with open(filepath, 'rb') as f:
            batch_data.append(f.read())
    
    batch_latencies = []
    for _ in range(num_iterations):
        start = time.perf_counter()
        for data in batch_data:
            assess_quality(data)
        batch_latency = (time.perf_counter() - start) * 1000
        batch_latencies.append(batch_latency)
    
    batch_latencies.sort()
    batch_mean = sum(batch_latencies) / len(batch_latencies)
    batch_p95 = batch_latencies[int(len(batch_latencies) * 0.95)]
    
    print(f"  Batch size: 10 images")
    print(f"  Iterations: {num_iterations}")
    print(f"  Mean batch time: {batch_mean:.2f} ms")
    print(f"  P95 batch time:  {batch_p95:.2f} ms")
    print(f"  Mean per-image:  {batch_mean / 10:.2f} ms")
    
    # Component timing
    print("\n3. Component Breakdown (average across dataset):")
    
    component_times = {
        'decode': [],
        'sharpness': [],
        'exposure': [],
        'noise': [],
        'edge_density': [],
    }
    
    for filename, _, _ in dataset:
        filepath = DATASET_DIR / filename
        with open(filepath, 'rb') as f:
            image_data = f.read()
        
        # Decode
        start = time.perf_counter()
        _, gray = decode_image(image_data)
        component_times['decode'].append((time.perf_counter() - start) * 1000)
        
        # Sharpness
        start = time.perf_counter()
        compute_sharpness(gray)
        component_times['sharpness'].append((time.perf_counter() - start) * 1000)
        
        # Exposure
        start = time.perf_counter()
        compute_exposure(gray)
        component_times['exposure'].append((time.perf_counter() - start) * 1000)
        
        # Noise
        start = time.perf_counter()
        compute_noise(gray)
        component_times['noise'].append((time.perf_counter() - start) * 1000)
        
        # Edge density
        start = time.perf_counter()
        compute_edge_density(gray)
        component_times['edge_density'].append((time.perf_counter() - start) * 1000)
    
    for component, times in component_times.items():
        avg_time = sum(times) / len(times)
        print(f"  {component:<15}: {avg_time:>6.2f} ms avg")
    
    return {
        'mean': mean_latency,
        'p95': p95_latency,
        'max': max_latency,
        'passes_target': p95_latency < target,
    }


def generate_report(results: List[CalibrationResult], 
                   false_positives: List[CalibrationResult],
                   false_negatives: List[CalibrationResult],
                   recommended_threshold: float,
                   perf_data: dict):
    """Generate final calibration report."""
    print("\n" + "=" * 80)
    print("FINAL CALIBRATION REPORT")
    print("=" * 80)
    
    # 1. Dataset summary
    print("\n1. CALIBRATION DATASET SUMMARY")
    print("-" * 40)
    good_count = sum(1 for r in results if r.human_label == "good")
    medium_count = sum(1 for r in results if r.human_label == "medium")
    poor_count = sum(1 for r in results if r.human_label == "poor")
    print(f"  Total images: {len(results)}")
    print(f"  Good (expected fast path):     {good_count}")
    print(f"  Medium (borderline):           {medium_count}")
    print(f"  Poor (expected fallback path): {poor_count}")
    
    # 2. Results summary
    print("\n2. SCORING RESULTS SUMMARY")
    print("-" * 40)
    scores = [r.quality_score for r in results]
    print(f"  Score range: {min(scores):.3f} - {max(scores):.3f}")
    print(f"  Mean score:  {sum(scores)/len(scores):.3f}")
    
    for label in ["good", "medium", "poor"]:
        subset = [r for r in results if r.human_label == label]
        if subset:
            avg = sum(r.quality_score for r in subset) / len(subset)
            print(f"  {label.capitalize()} images avg: {avg:.3f}")
    
    # 3. Misclassification summary
    print("\n3. MISCLASSIFICATION ANALYSIS")
    print("-" * 40)
    print(f"  False Positives (poor → fast):  {len(false_positives)}")
    print(f"  False Negatives (good → fallback): {len(false_negatives)}")
    
    accuracy_good = (good_count - len(false_negatives)) / good_count if good_count > 0 else 1.0
    accuracy_poor = (poor_count - len(false_positives)) / poor_count if poor_count > 0 else 1.0
    print(f"  Good image accuracy: {accuracy_good:.1%}")
    print(f"  Poor image accuracy: {accuracy_poor:.1%}")
    
    # 4. Threshold recommendation
    print("\n4. THRESHOLD RECOMMENDATION")
    print("-" * 40)
    print(f"  Current threshold: {FAST_PATH_THRESHOLD:.2f}")
    print(f"  Recommended threshold: {recommended_threshold:.2f}")
    
    if recommended_threshold != FAST_PATH_THRESHOLD:
        change = recommended_threshold - FAST_PATH_THRESHOLD
        direction = "increase" if change > 0 else "decrease"
        print(f"  Change: {direction} by {abs(change):.2f}")
    else:
        print(f"  Change: NONE (current threshold is optimal)")
    
    # 5. Weight changes
    print("\n5. WEIGHT ADJUSTMENT")
    print("-" * 40)
    if not false_positives and not false_negatives:
        print("  NO WEIGHT CHANGES RECOMMENDED")
        print("  Threshold tuning alone is sufficient")
    else:
        print("  Consider weight review if threshold tuning insufficient")
    
    # 6. Performance
    print("\n6. PERFORMANCE BENCHMARK")
    print("-" * 40)
    print(f"  Mean latency: {perf_data['mean']:.2f} ms")
    print(f"  P95 latency:  {perf_data['p95']:.2f} ms")
    print(f"  Max latency:  {perf_data['max']:.2f} ms")
    print(f"  Target:       100 ms")
    print(f"  Status:       {'✓ PASS' if perf_data['passes_target'] else '✗ FAIL'}")
    
    # 7. Final recommendation
    print("\n7. FINAL RECOMMENDATION")
    print("-" * 40)
    
    if len(false_positives) == 0 and len(false_negatives) == 0:
        if recommended_threshold == FAST_PATH_THRESHOLD:
            print("  ★ KEEP AS-IS")
            print("    Current configuration is well-calibrated")
        else:
            print("  ★ ADJUST THRESHOLD")
            print(f"    Change threshold from {FAST_PATH_THRESHOLD:.2f} to {recommended_threshold:.2f}")
    elif len(false_positives) == 0:
        print("  ★ ADJUST THRESHOLD")
        print(f"    Lower threshold to reduce false negatives")
        print(f"    Recommended: {recommended_threshold:.2f}")
    elif len(false_positives) > 0:
        print("  ★ ADJUST THRESHOLD (PRIORITY)")
        print(f"    CRITICAL: {len(false_positives)} poor images incorrectly routed to fast path")
        print(f"    Raise threshold to {recommended_threshold:.2f}")
        if len(false_positives) > 2:
            print("    If threshold change insufficient, review metric weights")
    
    print("\n" + "=" * 80)


def main():
    """Main calibration workflow."""
    print("=" * 80)
    print("QUALITY SCORING CALIBRATION")
    print(f"Threshold: {FAST_PATH_THRESHOLD}")
    print("=" * 80)
    
    # Step 1 & 2: Run scoring
    print("\nRunning quality assessment on calibration dataset...")
    results = run_calibration()
    
    # Print results table
    print_results_table(results)
    
    # Step 3: Analyze misclassifications
    false_positives, false_negatives = analyze_misclassifications(results)
    
    # Step 4: Threshold calibration
    recommended_threshold = threshold_calibration(results)
    
    # Step 5: Metric weight review
    metric_weight_review(results, false_positives, false_negatives)
    
    # Step 6: Performance benchmark
    perf_data = performance_benchmark(num_iterations=5)
    
    # Generate final report
    generate_report(results, false_positives, false_negatives, recommended_threshold, perf_data)


if __name__ == "__main__":
    main()
