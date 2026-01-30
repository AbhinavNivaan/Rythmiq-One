#!/usr/bin/env python3
"""
CPU Baseline Benchmark for Rythmiq One Worker.

Runs a controlled benchmark to measure actual CPU consumption per document.
This is the first step in capacity planning - MEASURE, don't estimate.

Usage:
    # Run benchmark with 10 test documents
    python benchmark.py --count 10 --output results.json
    
    # Run with custom test data
    python benchmark.py --input test-data/fixtures/ --count 20
    
    # Quick sanity check
    python benchmark.py --count 3 --verbose

Output:
    JSON file with per-document and aggregate metrics.
"""

import argparse
import json
import os
import sys
import subprocess
import tempfile
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional, Dict, Any
import statistics


# Add worker to path
WORKER_DIR = Path(__file__).parent.parent / "worker"
sys.path.insert(0, str(WORKER_DIR))


@dataclass
class DocumentResult:
    """Result for a single document benchmark."""
    doc_id: int
    filename: str
    input_size_bytes: int
    total_cpu_seconds: float
    total_wall_seconds: float
    processing_path: str
    execution_temperature: str
    stages: Dict[str, float]
    success: bool
    error: Optional[str] = None


@dataclass
class BenchmarkSummary:
    """Aggregate benchmark statistics."""
    total_documents: int
    successful_documents: int
    failed_documents: int
    
    # CPU metrics
    total_cpu_seconds: float
    avg_cpu_seconds: float
    min_cpu_seconds: float
    max_cpu_seconds: float
    p50_cpu_seconds: float
    p95_cpu_seconds: float
    std_cpu_seconds: float
    
    # Wall time metrics
    avg_wall_seconds: float
    
    # Path breakdown
    fast_path_count: int
    fast_path_avg_cpu: float
    standard_path_count: int
    standard_path_avg_cpu: float
    
    # Cold/warm breakdown
    cold_count: int
    cold_avg_cpu: float
    warm_count: int
    warm_avg_cpu: float
    
    # Stage breakdown (averages)
    stage_breakdown: Dict[str, float]
    
    # Projections
    projected_monthly_cpu_hours_700: float
    projected_monthly_cpu_hours_1000: float
    projected_monthly_cpu_hours_1300: float
    budget_status_1000: str  # "UNDER", "MARGINAL", "OVER"


def create_test_payload(
    test_file: Path,
    job_id: str,
    storage_config: Dict[str, str],
) -> Dict[str, Any]:
    """Create a worker payload for a test document."""
    return {
        "job_id": job_id,
        "user_id": str(uuid.uuid4()),
        "portal_schema": {
            "id": "benchmark-schema",
            "name": "benchmark",
            "version": 1,
            "schema_definition": {
                "target_width": 600,
                "target_height": 800,
                "target_dpi": 300,
                "max_kb": 200,
                "filename_pattern": "{job_id}",
                "output_format": "jpeg",
                "quality": 85,
            },
        },
        "input": {
            "artifact_source": "path",
            "artifact_url": None,
            "raw_path": str(test_file.absolute()),
            "mime_type": "image/jpeg",
            "original_filename": test_file.name,
        },
        "storage": storage_config,
    }


def run_worker_benchmark(
    payload: Dict[str, Any],
    worker_path: Path,
) -> Dict[str, Any]:
    """
    Run the instrumented worker with a payload and capture output.
    
    Returns:
        Parsed JSON output from worker
    """
    payload_json = json.dumps(payload)
    
    try:
        result = subprocess.run(
            [sys.executable, str(worker_path)],
            input=payload_json,
            capture_output=True,
            text=True,
            timeout=120,  # 2 minute timeout
        )
        
        if result.returncode != 0:
            return {
                "status": "FAILED",
                "error": {
                    "message": f"Worker exited with code {result.returncode}",
                    "stderr": result.stderr[:500] if result.stderr else None,
                },
            }
        
        # Parse output JSON
        output = json.loads(result.stdout.strip())
        return output
        
    except subprocess.TimeoutExpired:
        return {
            "status": "FAILED",
            "error": {"message": "Worker timed out after 120s"},
        }
    except json.JSONDecodeError as e:
        return {
            "status": "FAILED",
            "error": {"message": f"Invalid JSON output: {str(e)}"},
        }
    except Exception as e:
        return {
            "status": "FAILED",
            "error": {"message": f"Unexpected error: {str(e)}"},
        }


def find_test_documents(input_dir: Path, count: int) -> List[Path]:
    """Find test documents in the input directory."""
    extensions = {'.jpg', '.jpeg', '.png', '.tiff', '.tif', '.pdf'}
    documents = []
    
    for ext in extensions:
        documents.extend(input_dir.glob(f'**/*{ext}'))
        documents.extend(input_dir.glob(f'**/*{ext.upper()}'))
    
    if not documents:
        raise ValueError(f"No image files found in {input_dir}")
    
    # Repeat documents if we need more than available
    selected = []
    while len(selected) < count:
        for doc in documents:
            if len(selected) >= count:
                break
            selected.append(doc)
    
    return selected


def calculate_summary(results: List[DocumentResult]) -> BenchmarkSummary:
    """Calculate aggregate statistics from benchmark results."""
    successful = [r for r in results if r.success]
    
    if not successful:
        raise ValueError("No successful benchmarks to summarize")
    
    cpu_times = [r.total_cpu_seconds for r in successful]
    wall_times = [r.total_wall_seconds for r in successful]
    
    # Path breakdown
    fast_path = [r for r in successful if r.processing_path == "fast"]
    standard_path = [r for r in successful if r.processing_path == "standard"]
    
    # Temperature breakdown
    cold = [r for r in successful if r.execution_temperature == "cold"]
    warm = [r for r in successful if r.execution_temperature == "warm"]
    
    # Stage aggregation
    stage_totals: Dict[str, List[float]] = {}
    for r in successful:
        for stage, cpu in r.stages.items():
            if stage not in stage_totals:
                stage_totals[stage] = []
            stage_totals[stage].append(cpu)
    
    stage_breakdown = {
        name: statistics.mean(times) for name, times in stage_totals.items()
    }
    
    # Calculate projections
    avg_cpu = statistics.mean(cpu_times)
    
    def project_monthly(docs_per_day: int) -> float:
        return avg_cpu * docs_per_day * 30 / 3600
    
    monthly_1000 = project_monthly(1000)
    
    if monthly_1000 <= 200:
        budget_status = "UNDER"
    elif monthly_1000 <= 220:
        budget_status = "MARGINAL"
    else:
        budget_status = "OVER"
    
    # Percentiles
    cpu_sorted = sorted(cpu_times)
    n = len(cpu_sorted)
    
    return BenchmarkSummary(
        total_documents=len(results),
        successful_documents=len(successful),
        failed_documents=len(results) - len(successful),
        
        total_cpu_seconds=sum(cpu_times),
        avg_cpu_seconds=avg_cpu,
        min_cpu_seconds=min(cpu_times),
        max_cpu_seconds=max(cpu_times),
        p50_cpu_seconds=cpu_sorted[int(n * 0.5)],
        p95_cpu_seconds=cpu_sorted[int(n * 0.95)] if n > 20 else cpu_sorted[-1],
        std_cpu_seconds=statistics.stdev(cpu_times) if n > 1 else 0,
        
        avg_wall_seconds=statistics.mean(wall_times),
        
        fast_path_count=len(fast_path),
        fast_path_avg_cpu=statistics.mean([r.total_cpu_seconds for r in fast_path]) if fast_path else 0,
        standard_path_count=len(standard_path),
        standard_path_avg_cpu=statistics.mean([r.total_cpu_seconds for r in standard_path]) if standard_path else 0,
        
        cold_count=len(cold),
        cold_avg_cpu=statistics.mean([r.total_cpu_seconds for r in cold]) if cold else 0,
        warm_count=len(warm),
        warm_avg_cpu=statistics.mean([r.total_cpu_seconds for r in warm]) if warm else 0,
        
        stage_breakdown=stage_breakdown,
        
        projected_monthly_cpu_hours_700=project_monthly(700),
        projected_monthly_cpu_hours_1000=monthly_1000,
        projected_monthly_cpu_hours_1300=project_monthly(1300),
        budget_status_1000=budget_status,
    )


def print_summary(summary: BenchmarkSummary) -> None:
    """Print human-readable summary to stdout."""
    print("\n" + "=" * 70)
    print("BENCHMARK RESULTS")
    print("=" * 70)
    
    print(f"\n📊 Documents Processed: {summary.successful_documents}/{summary.total_documents}")
    if summary.failed_documents:
        print(f"   ⚠️  Failed: {summary.failed_documents}")
    
    print(f"\n⏱️  CPU Time per Document:")
    print(f"   Average: {summary.avg_cpu_seconds:.3f}s")
    print(f"   P50:     {summary.p50_cpu_seconds:.3f}s")
    print(f"   P95:     {summary.p95_cpu_seconds:.3f}s")
    print(f"   Min/Max: {summary.min_cpu_seconds:.3f}s / {summary.max_cpu_seconds:.3f}s")
    print(f"   StdDev:  {summary.std_cpu_seconds:.3f}s")
    
    print(f"\n🛤️  Processing Path Breakdown:")
    if summary.fast_path_count:
        print(f"   Fast:     {summary.fast_path_count} docs @ {summary.fast_path_avg_cpu:.3f}s avg")
    if summary.standard_path_count:
        print(f"   Standard: {summary.standard_path_count} docs @ {summary.standard_path_avg_cpu:.3f}s avg")
    
    print(f"\n🌡️  Execution Temperature:")
    if summary.cold_count:
        print(f"   Cold: {summary.cold_count} docs @ {summary.cold_avg_cpu:.3f}s avg")
    if summary.warm_count:
        print(f"   Warm: {summary.warm_count} docs @ {summary.warm_avg_cpu:.3f}s avg")
    
    print(f"\n📈 Stage Breakdown (average CPU seconds):")
    for stage, cpu in sorted(summary.stage_breakdown.items()):
        pct = (cpu / summary.avg_cpu_seconds * 100) if summary.avg_cpu_seconds > 0 else 0
        bar = "█" * int(pct / 5)
        print(f"   {stage:20s} {cpu:.3f}s ({pct:5.1f}%) {bar}")
    
    print(f"\n💰 CAPACITY PROJECTIONS (200 CPU-hours/month budget):")
    print(f"   @ 700 docs/day:  {summary.projected_monthly_cpu_hours_700:6.1f} CPU-hours/month")
    print(f"   @ 1000 docs/day: {summary.projected_monthly_cpu_hours_1000:6.1f} CPU-hours/month")
    print(f"   @ 1300 docs/day: {summary.projected_monthly_cpu_hours_1300:6.1f} CPU-hours/month")
    
    print(f"\n🎯 BUDGET STATUS @ 1000 docs/day: ", end="")
    if summary.budget_status_1000 == "UNDER":
        print("✅ UNDER BUDGET")
    elif summary.budget_status_1000 == "MARGINAL":
        print("⚠️  MARGINAL (within 10% of budget)")
    else:
        print("❌ OVER BUDGET")
    
    # Calculate max sustainable volume
    max_volume = int((200 * 3600) / (summary.avg_cpu_seconds * 30))
    print(f"   Maximum sustainable: {max_volume} docs/day")
    
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="CPU Baseline Benchmark for Rythmiq One Worker"
    )
    parser.add_argument(
        "--input", "-i",
        type=Path,
        default=Path("test-data/fixtures"),
        help="Directory containing test documents",
    )
    parser.add_argument(
        "--count", "-c",
        type=int,
        default=10,
        help="Number of documents to process",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        help="Output JSON file for detailed results",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print progress for each document",
    )
    parser.add_argument(
        "--worker",
        type=Path,
        default=WORKER_DIR / "worker_instrumented.py",
        help="Path to instrumented worker script",
    )
    
    args = parser.parse_args()
    
    # Validate inputs
    if not args.input.exists():
        print(f"Error: Input directory not found: {args.input}")
        sys.exit(1)
    
    if not args.worker.exists():
        print(f"Error: Worker not found: {args.worker}")
        sys.exit(1)
    
    # Find test documents
    print(f"Finding test documents in {args.input}...")
    try:
        documents = find_test_documents(args.input, args.count)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
    
    print(f"Found {len(documents)} documents for benchmark")
    
    # Mock storage config (for local testing)
    storage_config = {
        "bucket": "benchmark-bucket",
        "region": "us-east-1",
        "endpoint": "https://mock-storage.local",
    }
    
    # Run benchmarks
    results: List[DocumentResult] = []
    
    for i, doc_path in enumerate(documents):
        job_id = str(uuid.uuid4())
        
        if args.verbose:
            print(f"[{i+1}/{len(documents)}] Processing {doc_path.name}...", end=" ", flush=True)
        
        payload = create_test_payload(doc_path, job_id, storage_config)
        output = run_worker_benchmark(payload, args.worker)
        
        if output.get("status") == "SUCCESS":
            metrics = output.get("cpu_metrics", {})
            stages = {
                k: v.get("cpu_seconds", 0) 
                for k, v in metrics.get("stages", {}).items()
            }
            
            result = DocumentResult(
                doc_id=i,
                filename=doc_path.name,
                input_size_bytes=doc_path.stat().st_size,
                total_cpu_seconds=metrics.get("total_cpu_seconds", 0),
                total_wall_seconds=metrics.get("total_wall_seconds", 0),
                processing_path=metrics.get("processing_path", "unknown"),
                execution_temperature=metrics.get("execution_temperature", "unknown"),
                stages=stages,
                success=True,
            )
            
            if args.verbose:
                print(f"✓ {result.total_cpu_seconds:.3f}s CPU")
        else:
            error_msg = output.get("error", {}).get("message", "Unknown error")
            result = DocumentResult(
                doc_id=i,
                filename=doc_path.name,
                input_size_bytes=doc_path.stat().st_size,
                total_cpu_seconds=0,
                total_wall_seconds=0,
                processing_path="unknown",
                execution_temperature="unknown",
                stages={},
                success=False,
                error=error_msg,
            )
            
            if args.verbose:
                print(f"✗ {error_msg}")
        
        results.append(result)
    
    # Calculate summary
    try:
        summary = calculate_summary(results)
        print_summary(summary)
        
        # Save detailed results if output specified
        if args.output:
            output_data = {
                "summary": asdict(summary),
                "documents": [asdict(r) for r in results],
            }
            args.output.write_text(json.dumps(output_data, indent=2))
            print(f"\nDetailed results saved to: {args.output}")
        
        # Exit with appropriate code
        if summary.budget_status_1000 == "OVER":
            sys.exit(2)  # Over budget
        elif summary.budget_status_1000 == "MARGINAL":
            sys.exit(1)  # Marginal
        else:
            sys.exit(0)  # Under budget
            
    except ValueError as e:
        print(f"Error calculating summary: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
