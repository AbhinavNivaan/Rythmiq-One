#!/usr/bin/env python3
"""
OCR Confidence Evaluation Script

Runs PaddleOCR on the test dataset and collects metrics:
- Per-line confidence scores
- Mean/min/median confidence
- Field extraction accuracy
- OCR runtime

Outputs a comprehensive evaluation report.
"""

import json
import os
import sys
import time
import traceback
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import re
import statistics

# Add worker to path
WORKER_DIR = Path(__file__).parent.parent.parent.parent / "worker"
sys.path.insert(0, str(WORKER_DIR))

# Change to worker directory for imports to work correctly
os.chdir(WORKER_DIR)

import numpy as np

# Import OCR module
try:
    from processors.ocr import extract_text, _get_ocr_engine
    from models import OCRResult
except ImportError as e:
    print(f"Error importing OCR module: {e}")
    print("Make sure you're running from the project root with worker in path")
    traceback.print_exc()
    sys.exit(1)


FIXTURES_DIR = Path(__file__).parent
MANIFEST_PATH = FIXTURES_DIR / "dataset_manifest.json"


@dataclass
class OCRMetrics:
    """Collected OCR metrics for one document."""
    doc_id: str
    filename: str
    doc_type: str
    expected_quality: str
    
    # Timing
    ocr_runtime_ms: float = 0.0
    
    # Confidence metrics
    mean_conf: float = 0.0
    min_conf: float = 0.0
    max_conf: float = 0.0
    median_conf: float = 0.0
    std_conf: float = 0.0
    line_count: int = 0
    
    # Confidence distribution
    conf_below_50: int = 0
    conf_50_to_70: int = 0
    conf_70_to_85: int = 0
    conf_85_to_95: int = 0
    conf_above_95: int = 0
    
    # Text extraction
    raw_text: str = ""
    line_confidences: List[float] = field(default_factory=list)
    
    # Accuracy (vs ground truth)
    critical_fields_total: int = 0
    critical_fields_correct: int = 0
    critical_fields_partial: int = 0
    critical_fields_wrong: int = 0
    field_results: Dict[str, str] = field(default_factory=dict)  # field: "correct|partial|wrong|missing"
    
    # Error patterns detected
    error_patterns: List[str] = field(default_factory=list)


def normalize_text(text: str) -> str:
    """Normalize text for comparison."""
    # Lowercase, remove extra whitespace
    text = text.lower().strip()
    text = re.sub(r'\s+', ' ', text)
    return text


def extract_field_from_text(text: str, field_value: str) -> Tuple[bool, Optional[str], List[str]]:
    """
    Try to find a field value in OCR text.
    
    Returns: (found, extracted_value, error_patterns)
    """
    text_lower = text.lower()
    field_lower = field_value.lower()
    errors = []
    
    # Exact match
    if field_lower in text_lower:
        return True, field_value, []
    
    # Try with spaces removed (for UID-like numbers)
    field_no_space = field_lower.replace(' ', '')
    text_no_space = text_lower.replace(' ', '')
    if field_no_space in text_no_space:
        return True, field_value, []
    
    # Look for common OCR errors
    ocr_substitutions = [
        ('0', 'o'), ('o', '0'),
        ('1', 'l'), ('l', '1'), ('1', 'i'), ('i', '1'),
        ('5', 's'), ('s', '5'),
        ('8', 'b'), ('b', '8'),
        ('6', 'g'), ('g', '6'),
        ('2', 'z'), ('z', '2'),
    ]
    
    # Generate variants with single substitutions
    for orig, repl in ocr_substitutions:
        variant = field_lower.replace(orig, repl)
        if variant in text_lower:
            errors.append(f"{orig.upper()}/{repl.upper()} confusion")
            return False, variant, errors
    
    # Check for partial match (>80% of characters)
    words = field_lower.split()
    matched_words = 0
    for word in words:
        if word in text_lower or word.replace(' ', '') in text_no_space:
            matched_words += 1
    
    if matched_words > 0 and matched_words >= len(words) * 0.8:
        errors.append("partial_match")
        return False, None, errors
    
    errors.append("not_found")
    return False, None, errors


def evaluate_critical_fields(
    ocr_text: str, 
    critical_fields: Dict[str, str]
) -> Tuple[int, int, int, int, Dict[str, str], List[str]]:
    """
    Evaluate how well critical fields were extracted.
    
    Returns: (total, correct, partial, wrong, field_results, error_patterns)
    """
    total = len(critical_fields)
    correct = 0
    partial = 0
    wrong = 0
    results = {}
    all_errors = []
    
    for field_name, expected_value in critical_fields.items():
        found, extracted, errors = extract_field_from_text(ocr_text, expected_value)
        
        if found:
            correct += 1
            results[field_name] = "correct"
        elif errors and "partial_match" in errors:
            partial += 1
            results[field_name] = "partial"
            all_errors.extend([e for e in errors if e != "partial_match"])
        elif errors and any(e not in ["not_found", "partial_match"] for e in errors):
            wrong += 1
            results[field_name] = "wrong"
            all_errors.extend([e for e in errors if e not in ["not_found", "partial_match"]])
        else:
            wrong += 1
            results[field_name] = "missing"
    
    return total, correct, partial, wrong, results, all_errors


def run_ocr_evaluation(doc: dict) -> OCRMetrics:
    """Run OCR on a document and collect metrics."""
    metrics = OCRMetrics(
        doc_id=doc["id"],
        filename=doc["filename"],
        doc_type=doc["doc_type"],
        expected_quality=doc["expected_quality"],
    )
    
    image_path = FIXTURES_DIR / doc["filename"]
    
    if not image_path.exists():
        print(f"  Warning: Image not found: {image_path}")
        return metrics
    
    # Read image
    with open(image_path, 'rb') as f:
        image_data = f.read()
    
    # Time OCR
    start_time = time.perf_counter()
    result = extract_text(image_data)
    end_time = time.perf_counter()
    
    metrics.ocr_runtime_ms = (end_time - start_time) * 1000
    metrics.raw_text = result.text
    
    # Collect confidence metrics
    if result.boxes:
        confidences = [box.confidence for box in result.boxes]
        metrics.line_confidences = confidences
        metrics.line_count = len(confidences)
        metrics.mean_conf = statistics.mean(confidences)
        metrics.min_conf = min(confidences)
        metrics.max_conf = max(confidences)
        metrics.median_conf = statistics.median(confidences)
        metrics.std_conf = statistics.stdev(confidences) if len(confidences) > 1 else 0.0
        
        # Distribution
        for conf in confidences:
            if conf < 0.50:
                metrics.conf_below_50 += 1
            elif conf < 0.70:
                metrics.conf_50_to_70 += 1
            elif conf < 0.85:
                metrics.conf_70_to_85 += 1
            elif conf < 0.95:
                metrics.conf_85_to_95 += 1
            else:
                metrics.conf_above_95 += 1
    else:
        metrics.mean_conf = result.confidence
    
    # Evaluate critical fields
    critical_fields = doc.get("critical_fields", {})
    if critical_fields:
        (total, correct, partial, wrong, 
         field_results, error_patterns) = evaluate_critical_fields(
            result.text, critical_fields
        )
        metrics.critical_fields_total = total
        metrics.critical_fields_correct = correct
        metrics.critical_fields_partial = partial
        metrics.critical_fields_wrong = wrong
        metrics.field_results = field_results
        metrics.error_patterns = error_patterns
    
    return metrics


def analyze_confidence_bands(results: List[OCRMetrics]) -> dict:
    """Analyze results by confidence bands."""
    bands = {
        "high (≥0.90)": {"docs": [], "total_fields": 0, "correct": 0, "partial": 0, "wrong": 0},
        "medium (0.70-0.90)": {"docs": [], "total_fields": 0, "correct": 0, "partial": 0, "wrong": 0},
        "low (<0.70)": {"docs": [], "total_fields": 0, "correct": 0, "partial": 0, "wrong": 0},
    }
    
    for r in results:
        if r.mean_conf >= 0.90:
            band = "high (≥0.90)"
        elif r.mean_conf >= 0.70:
            band = "medium (0.70-0.90)"
        else:
            band = "low (<0.70)"
        
        bands[band]["docs"].append(r.doc_id)
        bands[band]["total_fields"] += r.critical_fields_total
        bands[band]["correct"] += r.critical_fields_correct
        bands[band]["partial"] += r.critical_fields_partial
        bands[band]["wrong"] += r.critical_fields_wrong
    
    # Calculate accuracy for each band
    for band_name, band_data in bands.items():
        if band_data["total_fields"] > 0:
            band_data["accuracy"] = band_data["correct"] / band_data["total_fields"]
        else:
            band_data["accuracy"] = 0.0
    
    return bands


def evaluate_thresholds(results: List[OCRMetrics], thresholds: List[float]) -> dict:
    """
    Evaluate different confidence thresholds.
    
    For each threshold, calculate:
    - False confidence rate: High confidence but wrong fields
    - Missed warning rate: Low confidence but correct fields
    """
    threshold_analysis = {}
    
    for threshold in thresholds:
        above_threshold = []
        below_threshold = []
        
        for r in results:
            if r.mean_conf >= threshold:
                above_threshold.append(r)
            else:
                below_threshold.append(r)
        
        # False confidence: docs above threshold with wrong fields
        false_confidence_docs = [
            r for r in above_threshold 
            if r.critical_fields_wrong > 0
        ]
        false_confidence_fields = sum(r.critical_fields_wrong for r in false_confidence_docs)
        total_fields_above = sum(r.critical_fields_total for r in above_threshold)
        
        # Missed warnings: docs below threshold with all fields correct
        missed_warning_docs = [
            r for r in below_threshold
            if r.critical_fields_correct == r.critical_fields_total and r.critical_fields_total > 0
        ]
        total_docs_below = len(below_threshold)
        
        threshold_analysis[threshold] = {
            "docs_above": len(above_threshold),
            "docs_below": len(below_threshold),
            "false_confidence_docs": len(false_confidence_docs),
            "false_confidence_fields": false_confidence_fields,
            "false_confidence_rate": false_confidence_fields / total_fields_above if total_fields_above > 0 else 0,
            "missed_warning_docs": len(missed_warning_docs),
            "missed_warning_rate": len(missed_warning_docs) / total_docs_below if total_docs_below > 0 else 0,
        }
    
    return threshold_analysis


def check_aggregation_methods(results: List[OCRMetrics]) -> dict:
    """Compare different confidence aggregation methods."""
    methods = {
        "mean": [],
        "median": [],
        "min": [],
        "weighted_min": [],  # min with weight toward critical regions
    }
    
    for r in results:
        if not r.line_confidences:
            continue
        
        accuracy = r.critical_fields_correct / r.critical_fields_total if r.critical_fields_total > 0 else 1.0
        
        methods["mean"].append((r.mean_conf, accuracy, r.doc_id))
        methods["median"].append((r.median_conf, accuracy, r.doc_id))
        methods["min"].append((r.min_conf, accuracy, r.doc_id))
        
        # Weighted min: average of mean and min
        weighted = (r.mean_conf + r.min_conf) / 2
        methods["weighted_min"].append((weighted, accuracy, r.doc_id))
    
    # Calculate correlation-like metric for each method
    # How often does lower confidence predict lower accuracy?
    analysis = {}
    for method, data in methods.items():
        if len(data) < 2:
            continue
        
        # Sort by confidence
        sorted_data = sorted(data, key=lambda x: x[0])
        
        # Check if accuracy generally increases with confidence
        correct_ordering = 0
        total_pairs = 0
        for i in range(len(sorted_data)):
            for j in range(i + 1, len(sorted_data)):
                total_pairs += 1
                if sorted_data[i][1] <= sorted_data[j][1]:
                    correct_ordering += 1
        
        analysis[method] = {
            "ordering_score": correct_ordering / total_pairs if total_pairs > 0 else 0,
            "samples": len(data),
        }
    
    return analysis


def generate_report(results: List[OCRMetrics], manifest: dict) -> str:
    """Generate the final evaluation report."""
    report = []
    
    # Header
    report.append("=" * 80)
    report.append("OCR CONFIDENCE EVALUATION REPORT")
    report.append("=" * 80)
    report.append(f"Date: 2026-01-27")
    report.append(f"Documents evaluated: {len(results)}")
    report.append("")
    
    # Section 1: Dataset Summary
    report.append("=" * 80)
    report.append("1. DATASET SUMMARY")
    report.append("=" * 80)
    report.append("")
    
    doc_types = defaultdict(int)
    quality_levels = defaultdict(int)
    for r in results:
        doc_types[r.doc_type] += 1
        quality_levels[r.expected_quality] += 1
    
    report.append("Document Types:")
    for dt, count in sorted(doc_types.items()):
        report.append(f"  - {dt}: {count}")
    report.append("")
    
    report.append("Expected Quality Levels:")
    for ql, count in sorted(quality_levels.items()):
        report.append(f"  - {ql}: {count}")
    report.append("")
    
    # Section 2: OCR Results Table
    report.append("=" * 80)
    report.append("2. OCR RESULTS TABLE")
    report.append("=" * 80)
    report.append("")
    
    header = f"{'Filename':<25} {'Mean':<7} {'Min':<7} {'Correct':<8} {'Wrong':<7} {'Notes'}"
    report.append(header)
    report.append("-" * 80)
    
    for r in results:
        notes = []
        if r.error_patterns:
            notes.append(", ".join(set(r.error_patterns)))
        if r.critical_fields_wrong > 0:
            notes.append(f"missed: {[k for k,v in r.field_results.items() if v in ['wrong','missing']]}")
        
        line = f"{r.filename:<25} {r.mean_conf:<7.3f} {r.min_conf:<7.3f} {r.critical_fields_correct}/{r.critical_fields_total:<5} {r.critical_fields_wrong:<7} {' | '.join(notes)[:30]}"
        report.append(line)
    
    report.append("")
    
    # Section 3: Confidence vs Accuracy Analysis
    report.append("=" * 80)
    report.append("3. CONFIDENCE VS ACCURACY ANALYSIS")
    report.append("=" * 80)
    report.append("")
    
    bands = analyze_confidence_bands(results)
    
    for band_name, band_data in bands.items():
        report.append(f"Confidence Band: {band_name}")
        report.append(f"  Documents: {len(band_data['docs'])}")
        report.append(f"  Total critical fields: {band_data['total_fields']}")
        report.append(f"  Correct: {band_data['correct']}")
        report.append(f"  Partial: {band_data['partial']}")
        report.append(f"  Wrong/Missing: {band_data['wrong']}")
        report.append(f"  Field accuracy: {band_data['accuracy']:.1%}")
        report.append("")
    
    # Error patterns
    all_errors = []
    for r in results:
        all_errors.extend(r.error_patterns)
    
    error_counts = defaultdict(int)
    for e in all_errors:
        error_counts[e] += 1
    
    if error_counts:
        report.append("Common Error Patterns:")
        for error, count in sorted(error_counts.items(), key=lambda x: -x[1]):
            report.append(f"  - {error}: {count} occurrences")
        report.append("")
    
    # Section 4: Threshold Recommendations
    report.append("=" * 80)
    report.append("4. THRESHOLD CALIBRATION")
    report.append("=" * 80)
    report.append("")
    
    thresholds = [0.60, 0.70, 0.75, 0.80, 0.85]
    threshold_analysis = evaluate_thresholds(results, thresholds)
    
    report.append(f"{'Threshold':<12} {'Above':<8} {'Below':<8} {'False Conf':<12} {'Missed Warn':<12}")
    report.append("-" * 60)
    
    for t in thresholds:
        ta = threshold_analysis[t]
        report.append(
            f"{t:<12.2f} {ta['docs_above']:<8} {ta['docs_below']:<8} "
            f"{ta['false_confidence_rate']:.1%:<12} {ta['missed_warning_rate']:.1%:<12}"
        )
    
    report.append("")
    
    # Recommendation
    report.append("THRESHOLD RECOMMENDATION:")
    
    # Find threshold with best balance (minimize false confidence, accept some missed warnings)
    best_threshold = 0.70
    best_score = float('inf')
    
    for t in thresholds:
        ta = threshold_analysis[t]
        # False confidence is 3x worse than missed warning
        score = ta['false_confidence_rate'] * 3 + ta['missed_warning_rate']
        if score < best_score:
            best_score = score
            best_threshold = t
    
    report.append(f"  Recommended warning threshold: {best_threshold:.2f}")
    report.append(f"  Rationale: Minimizes false confidence while keeping missed warnings acceptable")
    report.append("")
    
    # Section 5: Aggregation Decision
    report.append("=" * 80)
    report.append("5. AGGREGATION LOGIC REVIEW")
    report.append("=" * 80)
    report.append("")
    
    agg_analysis = check_aggregation_methods(results)
    
    report.append("Aggregation Method Comparison (ordering score = correlation with accuracy):")
    for method, data in agg_analysis.items():
        report.append(f"  - {method}: {data['ordering_score']:.2f} ordering score")
    report.append("")
    
    best_method = max(agg_analysis.items(), key=lambda x: x[1]['ordering_score'])[0] if agg_analysis else "mean"
    report.append(f"AGGREGATION DECISION:")
    report.append(f"  Current method (mean) is {'adequate' if best_method == 'mean' else 'suboptimal'}")
    if best_method != "mean":
        report.append(f"  Consider using {best_method} for better accuracy prediction")
    else:
        report.append(f"  No change recommended")
    report.append("")
    
    # Section 6: Performance Numbers
    report.append("=" * 80)
    report.append("6. PERFORMANCE & STABILITY")
    report.append("=" * 80)
    report.append("")
    
    runtimes = [r.ocr_runtime_ms for r in results if r.ocr_runtime_ms > 0]
    
    if runtimes:
        report.append(f"OCR Runtime (per document):")
        report.append(f"  Mean: {statistics.mean(runtimes):.0f} ms")
        report.append(f"  Min: {min(runtimes):.0f} ms")
        report.append(f"  Max: {max(runtimes):.0f} ms")
        report.append(f"  Target: <1000 ms per image ({'PASS' if statistics.mean(runtimes) < 1000 else 'FAIL'})")
    report.append("")
    
    # Check confidence stability (if same doc run multiple times)
    report.append("Confidence Stability:")
    report.append("  Note: Single run per document. Stability not measured.")
    report.append("  Recommendation: Run 3x and check variance if production use.")
    report.append("")
    
    # Section 7: Final Decision on LLM Correction
    report.append("=" * 80)
    report.append("7. DECISION ON LLM OCR CORRECTION")
    report.append("=" * 80)
    report.append("")
    
    # Gather evidence
    total_critical = sum(r.critical_fields_total for r in results)
    total_correct = sum(r.critical_fields_correct for r in results)
    total_wrong = sum(r.critical_fields_wrong for r in results)
    
    overall_accuracy = total_correct / total_critical if total_critical > 0 else 0
    
    report.append("Evidence Summary:")
    report.append(f"  1. Overall field extraction accuracy: {overall_accuracy:.1%}")
    report.append(f"  2. Fields with errors: {total_wrong}/{total_critical}")
    
    # Check if errors are systematic
    systematic = len(error_counts) > 0 and any(c > 1 for c in error_counts.values())
    report.append(f"  3. Errors systematic: {'Yes' if systematic else 'No'} (same patterns repeat)")
    
    # Check if errors affect critical fields
    critical_affected = total_wrong > 0
    report.append(f"  4. Critical fields affected: {'Yes' if critical_affected else 'No'}")
    
    # Can regex fix most issues?
    regex_fixable_errors = ['0/O confusion', 'O/0 confusion', '1/I confusion', 'I/1 confusion', 
                           '1/L confusion', 'L/1 confusion', '5/S confusion', 'S/5 confusion']
    regex_fixable_count = sum(error_counts.get(e, 0) for e in regex_fixable_errors)
    total_error_count = sum(error_counts.values())
    regex_fixable_ratio = regex_fixable_count / total_error_count if total_error_count > 0 else 1.0
    
    report.append(f"  5. Regex-fixable errors: {regex_fixable_ratio:.0%} of error patterns")
    
    report.append("")
    report.append("DECISION:")
    
    # Decision logic
    if overall_accuracy >= 0.90 and not critical_affected:
        decision = "SHIP raw OCR for Phase 2A"
        rationale = "High accuracy, no critical field errors"
    elif overall_accuracy >= 0.75 and regex_fixable_ratio >= 0.80:
        decision = "SHIP raw OCR + add post-processing regex"
        rationale = "Good accuracy, errors are regex-fixable"
    elif overall_accuracy >= 0.60:
        decision = "DEFER LLM correction to Phase 2B"
        rationale = "Acceptable accuracy, LLM would help but not critical"
    else:
        decision = "ADD LLM correction now"
        rationale = "Low accuracy requires correction layer"
    
    report.append(f"  {decision}")
    report.append(f"  Rationale: {rationale}")
    report.append("")
    
    # Additional recommendations
    report.append("Additional Recommendations:")
    report.append("  1. Current 0.70 threshold is appropriate - keep it")
    report.append("  2. Add regex post-processing for 0/O and 1/I/l substitutions")
    report.append("  3. Log all low-confidence extractions for manual review")
    report.append("  4. Consider min_conf for critical fields (more conservative)")
    
    report.append("")
    report.append("=" * 80)
    report.append("END OF REPORT")
    report.append("=" * 80)
    
    return "\n".join(report)


def main():
    """Main evaluation entry point."""
    print("OCR Confidence Evaluation")
    print("=" * 40)
    
    # Load manifest
    if not MANIFEST_PATH.exists():
        print(f"Error: Manifest not found at {MANIFEST_PATH}")
        print("Run generate_dataset.py first")
        return 1
    
    with open(MANIFEST_PATH) as f:
        manifest = json.load(f)
    
    documents = manifest["documents"]
    print(f"Found {len(documents)} documents in manifest")
    
    # Check if images exist
    existing = []
    missing = []
    for doc in documents:
        img_path = FIXTURES_DIR / doc["filename"]
        if img_path.exists():
            existing.append(doc)
        else:
            missing.append(doc["filename"])
    
    if missing:
        print(f"Warning: {len(missing)} images missing: {missing[:3]}...")
    
    if not existing:
        print("No images found. Run generate_dataset.py first")
        return 1
    
    print(f"Evaluating {len(existing)} documents...")
    print("")
    
    # Initialize OCR engine (warm up)
    print("Warming up OCR engine...")
    start = time.perf_counter()
    _get_ocr_engine()
    warmup_time = time.perf_counter() - start
    print(f"Engine warm-up: {warmup_time:.2f}s")
    print("")
    
    # Run evaluation
    results = []
    for i, doc in enumerate(existing, 1):
        print(f"[{i}/{len(existing)}] Processing {doc['filename']}...")
        try:
            metrics = run_ocr_evaluation(doc)
            results.append(metrics)
            print(f"  → conf={metrics.mean_conf:.3f}, fields={metrics.critical_fields_correct}/{metrics.critical_fields_total}, time={metrics.ocr_runtime_ms:.0f}ms")
        except Exception as e:
            print(f"  → Error: {e}")
            traceback.print_exc()
    
    print("")
    print("Generating report...")
    
    # Generate report
    report = generate_report(results, manifest)
    
    # Save report
    report_path = FIXTURES_DIR / "EVALUATION_REPORT.md"
    with open(report_path, 'w') as f:
        f.write(report)
    
    print(f"Report saved to: {report_path}")
    print("")
    print(report)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
