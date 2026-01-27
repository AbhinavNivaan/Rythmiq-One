"""
Deep analysis of enhancement validation results.

Identifies:
1. Hidden failures (OCR regressions not caught by current thresholds)
2. Cases where enhancement did NOT help as expected
3. Dimension changes (orientation step)
4. Per-step analysis
"""

import json
import sys
from pathlib import Path
from typing import List, Dict, Tuple


def load_results(path: Path) -> List[Dict]:
    """Load validation results."""
    with open(path) as f:
        return json.load(f)


def analyze_ocr_regressions(results: List[Dict]) -> List[Dict]:
    """Find cases where OCR got worse."""
    regressions = []
    for r in results:
        if r["before_ocr"]["error"] is None and r["after_ocr"]["error"] is None:
            delta = r["ocr_delta"]
            if delta < -0.05:  # >5% OCR drop
                regressions.append({
                    "filename": r["filename"],
                    "category": r["category"],
                    "baseline_readable": r["baseline_readable"],
                    "before_ocr": r["before_ocr"]["confidence"],
                    "after_ocr": r["after_ocr"]["confidence"],
                    "delta": delta,
                    "severity": "CRITICAL" if delta < -0.15 else "WARNING",
                })
    return regressions


def analyze_quality_regressions(results: List[Dict]) -> List[Dict]:
    """Find cases where quality score dropped."""
    regressions = []
    for r in results:
        if r["quality_delta"] < -0.05:  # >5% quality drop
            regressions.append({
                "filename": r["filename"],
                "category": r["category"],
                "before_quality": r["before_quality"]["overall_score"],
                "after_quality": r["after_quality"]["overall_score"],
                "delta": r["quality_delta"],
                "metrics": {
                    "sharpness_delta": r["after_quality"]["sharpness"] - r["before_quality"]["sharpness"],
                    "exposure_delta": r["after_quality"]["exposure"] - r["before_quality"]["exposure"],
                    "noise_delta": r["after_quality"]["noise"] - r["before_quality"]["noise"],
                    "edge_delta": r["after_quality"]["edge_density"] - r["before_quality"]["edge_density"],
                }
            })
    return regressions


def analyze_dimension_changes(results: List[Dict]) -> List[Dict]:
    """Find cases where dimensions changed."""
    changes = []
    for r in results:
        if not r["dimensions_preserved"]:
            changes.append({
                "filename": r["filename"],
                "before": r["before_dimensions"],
                "after": r["after_dimensions"],
                "rotation_case": r["category"] == "rotation",
            })
    return changes


def analyze_orientation_effectiveness(results: List[Dict]) -> Dict:
    """Analyze how well orientation correction works."""
    rotation_cases = [r for r in results if r["category"] == "rotation"]
    
    return {
        "total_rotation_cases": len(rotation_cases),
        "corrected": sum(1 for r in rotation_cases if r["orientation_corrected"]),
        "not_corrected": sum(1 for r in rotation_cases if not r["orientation_corrected"]),
        "details": [
            {
                "filename": r["filename"],
                "description": r["description"],
                "corrected": r["orientation_corrected"],
                "quality_improved": r["quality_improved"],
                "ocr_improved": r["ocr_improved"],
            }
            for r in rotation_cases
        ]
    }


def analyze_expected_vs_actual(results: List[Dict]) -> Dict:
    """Compare expected improvement vs actual."""
    matches = []
    mismatches = []
    
    for r in results:
        expected = r["expected_improvement"]
        actual_quality = r["quality_improved"]
        actual_ocr = r["ocr_improved"]
        
        # Consider it "improved" if either metric improved
        actual = actual_quality or actual_ocr
        
        if expected and not actual:
            mismatches.append({
                "filename": r["filename"],
                "expected": "improvement",
                "actual": "no improvement",
                "quality_delta": r["quality_delta"],
                "ocr_delta": r["ocr_delta"],
            })
        elif not expected and actual:
            mismatches.append({
                "filename": r["filename"],
                "expected": "no improvement needed",
                "actual": "improved",
                "quality_delta": r["quality_delta"],
                "ocr_delta": r["ocr_delta"],
            })
        else:
            matches.append(r["filename"])
    
    return {
        "matches": len(matches),
        "mismatches": len(mismatches),
        "mismatch_details": mismatches,
    }


def analyze_denoising_impact(results: List[Dict]) -> Dict:
    """Analyze denoising effectiveness by category."""
    noise_cases = [r for r in results if r["category"] == "noise"]
    
    return {
        "noise_cases": len(noise_cases),
        "details": [
            {
                "filename": r["filename"],
                "denoised": r["denoised"],
                "noise_metric_before": r["before_quality"]["noise"],
                "noise_metric_after": r["after_quality"]["noise"],
                "noise_delta": r["after_quality"]["noise"] - r["before_quality"]["noise"],
                "ocr_improved": r["ocr_improved"],
            }
            for r in noise_cases
        ]
    }


def identify_guardrails_needed(results: List[Dict]) -> List[Dict]:
    """Identify specific guardrails based on failure patterns."""
    guardrails = []
    
    # Guardrail 1: Skip enhancement for high-quality readable images
    high_quality_readable = [
        r for r in results 
        if r["baseline_readable"] 
        and r["before_quality"]["overall_score"] > 0.75
        and r["ocr_delta"] < -0.05
    ]
    if high_quality_readable:
        guardrails.append({
            "id": "GUARD-001",
            "name": "Skip for high-quality readable images",
            "trigger": "baseline_quality > 0.75 AND baseline_readable = true",
            "action": "Skip denoise and CLAHE steps",
            "affected_images": [r["filename"] for r in high_quality_readable],
            "rationale": "Enhancement degrades OCR for already-readable images",
        })
    
    # Guardrail 2: Rollback if OCR drops significantly
    ocr_drops = [r for r in results if r["ocr_delta"] < -0.10]
    if ocr_drops:
        guardrails.append({
            "id": "GUARD-002", 
            "name": "OCR quality rollback",
            "trigger": "post_enhancement_ocr < pre_enhancement_ocr - 0.10",
            "action": "Rollback to original image",
            "affected_images": [r["filename"] for r in ocr_drops],
            "rationale": "Enhancement caused significant OCR regression",
        })
    
    # Guardrail 3: Large rotation detection (90°, 180°) needs different handling
    large_rotations = [
        r for r in results 
        if r["category"] == "rotation" 
        and not r["orientation_corrected"]
        and ("90" in r["description"] or "180" in r["description"])
    ]
    if large_rotations:
        guardrails.append({
            "id": "GUARD-003",
            "name": "Large rotation detection",
            "trigger": "Detected 90°/180° rotation not corrected by Hough lines",
            "action": "Add explicit 90°/180° rotation detection via text orientation",
            "affected_images": [r["filename"] for r in large_rotations],
            "rationale": "Current orientation detection only handles skew, not major rotations",
        })
    
    # Guardrail 4: Denoise causing edge loss
    denoise_edge_loss = [
        r for r in results 
        if r["denoised"]
        and (r["after_quality"]["edge_density"] - r["before_quality"]["edge_density"]) < -0.1
    ]
    if denoise_edge_loss:
        guardrails.append({
            "id": "GUARD-004",
            "name": "Denoise edge preservation",
            "trigger": "edge_density_delta < -0.1 after denoise",
            "action": "Reduce denoise strength or skip denoise for high-detail images",
            "affected_images": [r["filename"] for r in denoise_edge_loss],
            "rationale": "Denoising is eroding important edge information",
        })
    
    return guardrails


def generate_deep_analysis_report(results: List[Dict], output_path: Path) -> str:
    """Generate comprehensive analysis report."""
    
    ocr_regressions = analyze_ocr_regressions(results)
    quality_regressions = analyze_quality_regressions(results)
    dimension_changes = analyze_dimension_changes(results)
    orientation_analysis = analyze_orientation_effectiveness(results)
    expected_vs_actual = analyze_expected_vs_actual(results)
    denoise_analysis = analyze_denoising_impact(results)
    guardrails = identify_guardrails_needed(results)
    
    lines = [
        "# Enhancement Pipeline Deep Analysis Report",
        "",
        "## Executive Summary",
        "",
    ]
    
    # Quick summary
    total = len(results)
    ocr_reg_count = len(ocr_regressions)
    qual_reg_count = len(quality_regressions)
    dim_change_count = len(dimension_changes)
    
    if ocr_reg_count > 0 or qual_reg_count > 0:
        lines.append("⚠️ **ISSUES DETECTED** - Enhancement pipeline needs guardrails")
    else:
        lines.append("✓ No critical issues detected")
    
    lines.extend([
        "",
        f"- **OCR Regressions:** {ocr_reg_count}/{total} images",
        f"- **Quality Regressions:** {qual_reg_count}/{total} images",
        f"- **Dimension Changes:** {dim_change_count}/{total} images",
        f"- **Guardrails Recommended:** {len(guardrails)}",
        "",
    ])
    
    # OCR Regressions (CRITICAL)
    lines.extend([
        "---",
        "",
        "## 1. OCR Regressions (CRITICAL)",
        "",
    ])
    
    if ocr_regressions:
        lines.append("| Image | Baseline Readable | OCR Before | OCR After | Delta | Severity |")
        lines.append("|-------|-------------------|------------|-----------|-------|----------|")
        for reg in ocr_regressions:
            lines.append(
                f"| {reg['filename']} | {reg['baseline_readable']} | "
                f"{reg['before_ocr']:.3f} | {reg['after_ocr']:.3f} | "
                f"{reg['delta']:+.3f} | **{reg['severity']}** |"
            )
        lines.append("")
        lines.append("### Root Cause Analysis")
        lines.append("")
        lines.append("OCR regressions occur when enhancement processing:")
        lines.append("1. **Over-smooths text edges** via denoising")
        lines.append("2. **Alters contrast** inappropriately via CLAHE")  
        lines.append("3. **Introduces artifacts** from white balance correction")
        lines.append("")
    else:
        lines.append("✓ No significant OCR regressions detected.")
        lines.append("")
    
    # Quality Regressions
    lines.extend([
        "---",
        "",
        "## 2. Quality Score Regressions",
        "",
    ])
    
    if quality_regressions:
        lines.append("| Image | Quality Before | Quality After | Delta | Worst Metric |")
        lines.append("|-------|----------------|---------------|-------|--------------|")
        for reg in quality_regressions:
            # Find worst metric
            worst_metric = min(reg["metrics"].items(), key=lambda x: x[1])
            lines.append(
                f"| {reg['filename']} | {reg['before_quality']:.3f} | "
                f"{reg['after_quality']:.3f} | {reg['delta']:+.3f} | "
                f"{worst_metric[0]}: {worst_metric[1]:+.3f} |"
            )
        lines.append("")
    else:
        lines.append("✓ No significant quality regressions detected.")
        lines.append("")
    
    # Dimension Changes
    lines.extend([
        "---",
        "",
        "## 3. Dimension Preservation",
        "",
    ])
    
    if dimension_changes:
        lines.append("| Image | Before | After | Rotation Case |")
        lines.append("|-------|--------|-------|---------------|")
        for ch in dimension_changes:
            lines.append(
                f"| {ch['filename']} | {ch['before'][0]}x{ch['before'][1]} | "
                f"{ch['after'][0]}x{ch['after'][1]} | {ch['rotation_case']} |"
            )
        lines.append("")
        lines.append("**Note:** Dimension changes for rotation cases are expected when")
        lines.append("orientation correction expands canvas to avoid cropping.")
        lines.append("")
    else:
        lines.append("✓ All dimensions preserved.")
        lines.append("")
    
    # Orientation Analysis
    lines.extend([
        "---",
        "",
        "## 4. Orientation Correction Effectiveness",
        "",
        f"- **Total rotation test cases:** {orientation_analysis['total_rotation_cases']}",
        f"- **Successfully corrected:** {orientation_analysis['corrected']}",
        f"- **Not corrected:** {orientation_analysis['not_corrected']}",
        "",
        "### Per-Image Results",
        "",
        "| Image | Description | Corrected | Quality ↑ | OCR ↑ |",
        "|-------|-------------|-----------|-----------|-------|",
    ])
    
    for detail in orientation_analysis["details"]:
        corr = "✓" if detail["corrected"] else "✗"
        qual = "✓" if detail["quality_improved"] else "✗"
        ocr = "✓" if detail["ocr_improved"] else "✗"
        lines.append(f"| {detail['filename']} | {detail['description']} | {corr} | {qual} | {ocr} |")
    
    lines.extend([
        "",
        "### Findings",
        "",
        "1. **Small skew (1°):** Not corrected - below 1° threshold (correct behavior)",
        "2. **Moderate skew (5°):** Successfully corrected",
        "3. **Large rotations (90°, 180°):** NOT corrected - Hough line method cannot detect",
        "",
        "**Issue:** The current implementation uses Hough line analysis which only detects",
        "skew angles. It cannot detect 90° or 180° rotations. These require different",
        "detection methods (OCR text orientation, EXIF data, or content analysis).",
        "",
    ])
    
    # Denoising Analysis
    lines.extend([
        "---",
        "",
        "## 5. Denoising Impact Analysis",
        "",
    ])
    
    if denoise_analysis["noise_cases"]:
        lines.append("| Image | Applied | Noise Before | Noise After | Delta | OCR Improved |")
        lines.append("|-------|---------|--------------|-------------|-------|--------------|")
        for detail in denoise_analysis["details"]:
            applied = "✓" if detail["denoised"] else "✗"
            ocr = "✓" if detail["ocr_improved"] else "✗"
            lines.append(
                f"| {detail['filename']} | {applied} | {detail['noise_metric_before']:.3f} | "
                f"{detail['noise_metric_after']:.3f} | {detail['noise_delta']:+.3f} | {ocr} |"
            )
        lines.append("")
        lines.append("**Finding:** Denoising reduces noise metric but may not improve OCR.")
        lines.append("The noise metric measures high-frequency content which includes both")
        lines.append("noise AND fine text details.")
        lines.append("")
    
    # Expected vs Actual
    lines.extend([
        "---",
        "",
        "## 6. Expected vs Actual Improvement",
        "",
        f"- **Matching expectations:** {expected_vs_actual['matches']}/{total}",
        f"- **Mismatches:** {expected_vs_actual['mismatches']}/{total}",
        "",
    ])
    
    if expected_vs_actual["mismatch_details"]:
        lines.append("### Mismatches")
        lines.append("")
        lines.append("| Image | Expected | Actual | Quality Δ | OCR Δ |")
        lines.append("|-------|----------|--------|-----------|-------|")
        for m in expected_vs_actual["mismatch_details"]:
            lines.append(
                f"| {m['filename']} | {m['expected']} | {m['actual']} | "
                f"{m['quality_delta']:+.3f} | {m['ocr_delta']:+.3f} |"
            )
        lines.append("")
    
    # Recommended Guardrails
    lines.extend([
        "---",
        "",
        "## 7. Recommended Guardrails",
        "",
    ])
    
    if guardrails:
        for g in guardrails:
            lines.extend([
                f"### {g['id']}: {g['name']}",
                "",
                f"**Trigger:** `{g['trigger']}`",
                "",
                f"**Action:** {g['action']}",
                "",
                f"**Rationale:** {g['rationale']}",
                "",
                f"**Affected images:** {', '.join(g['affected_images'])}",
                "",
            ])
    else:
        lines.append("✓ No guardrails required based on current test results.")
        lines.append("")
    
    # Final Decision Matrix
    lines.extend([
        "---",
        "",
        "## 8. Final Decision Matrix",
        "",
        "### Enhancement Decision by Input Type",
        "",
        "| Input Condition | Orientation | Denoise | CLAHE | Rationale |",
        "|-----------------|-------------|---------|-------|-----------|",
        "| Clean, readable (score > 0.8) | ✓ | ✗ | ✗ | Risk of degradation |",
        "| Blurry (sharpness < 0.3) | ✓ | ✗ | ✓ | CLAHE helps, denoise hurts |",
        "| Noisy (noise < 0.5) | ✓ | ✓ | ✗ | Denoise helps |",
        "| Underexposed (exposure < 0.4) | ✓ | ✓ | ✓ | Full enhancement |",
        "| Overexposed (exposure > 0.9) | ✓ | ✗ | ✓ | Careful CLAHE |",
        "| Skewed (1° - 15°) | ✓ | per-above | per-above | Orientation first |",
        "| 90°/180° rotation | ✗* | per-above | per-above | *Needs separate detection |",
        "",
        "### Implementation Recommendation",
        "",
        "```python",
        "def should_enhance(quality_score: float, baseline_readable: bool) -> dict:",
        '    """Determine which enhancement steps to apply."""',
        "    if baseline_readable and quality_score > 0.8:",
        "        # High quality readable - minimal enhancement",
        "        return {",
        '            "orientation": True,',
        '            "denoise": False,',
        '            "clahe": False,',
        "        }",
        "    elif quality_score < 0.5:",
        "        # Low quality - full enhancement",
        "        return {",
        '            "orientation": True,',
        '            "denoise": True,',
        '            "clahe": True,',
        "        }",
        "    else:",
        "        # Medium quality - selective enhancement",
        "        return {",
        '            "orientation": True,',
        '            "denoise": quality_score < 0.65,',
        '            "clahe": True,',
        "        }",
        "```",
        "",
        "---",
        "",
        "## 9. Conclusion",
        "",
    ])
    
    # Final verdict
    critical_issues = len(ocr_regressions) + len([r for r in quality_regressions if r["delta"] < -0.08])
    
    if critical_issues == 0:
        lines.extend([
            "### VERDICT: ✓ KEEP Pipeline (with minor adjustments)",
            "",
            "The enhancement pipeline is functioning correctly for its intended purpose.",
            "No critical regressions were detected.",
            "",
        ])
    elif critical_issues <= 3:
        lines.extend([
            "### VERDICT: ⚠️ ADD GUARDRAILS",
            "",
            f"The pipeline shows {critical_issues} cases of regression that require guardrails.",
            "Implement the recommended guardrails before production use.",
            "",
            "**Priority fixes:**",
        ])
        for i, g in enumerate(guardrails[:3], 1):
            lines.append(f"{i}. {g['id']}: {g['name']}")
        lines.append("")
    else:
        lines.extend([
            "### VERDICT: ❌ SIGNIFICANT REWORK NEEDED",
            "",
            f"The pipeline shows {critical_issues} critical regressions.",
            "Consider redesigning enhancement logic before deployment.",
            "",
        ])
    
    report_text = "\n".join(lines)
    
    with open(output_path, "w") as f:
        f.write(report_text)
    
    return report_text


def main():
    script_dir = Path(__file__).parent
    results_path = script_dir / "validation_results.json"
    output_path = script_dir / "DEEP_ANALYSIS_REPORT.md"
    
    if not results_path.exists():
        print("ERROR: validation_results.json not found. Run run_validation.py first.")
        sys.exit(1)
    
    results = load_results(results_path)
    report = generate_deep_analysis_report(results, output_path)
    
    print(f"Deep analysis report saved to: {output_path}")
    print("\n" + "=" * 60)
    print("KEY FINDINGS")
    print("=" * 60)
    
    # Print key findings
    ocr_regressions = analyze_ocr_regressions(results)
    guardrails = identify_guardrails_needed(results)
    
    if ocr_regressions:
        print(f"\n⚠️  OCR REGRESSIONS: {len(ocr_regressions)} images")
        for reg in ocr_regressions:
            print(f"   - {reg['filename']}: {reg['before_ocr']:.2f} → {reg['after_ocr']:.2f} ({reg['delta']:+.2f})")
    
    if guardrails:
        print(f"\n📋 RECOMMENDED GUARDRAILS: {len(guardrails)}")
        for g in guardrails:
            print(f"   - {g['id']}: {g['name']}")


if __name__ == "__main__":
    main()
