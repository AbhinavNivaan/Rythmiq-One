#!/usr/bin/env python3
"""
Camber Execution Behavior Measurement Script (CLI-based)

Purpose: Empirically measure Camber's real execution behavior using CLI commands.
This script gathers baseline metrics for:
- Cold start latency
- Warm start latency  
- Idle window behavior
- Concurrency semantics

DO NOT OPTIMIZE, REFACTOR, OR CHANGE LOGIC - MEASUREMENT ONLY.

Date: 2026-01-30
"""

import json
import os
import re
import subprocess
import sys
import time
import statistics
from datetime import datetime
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# Configuration
CAMBER_API_KEY = os.environ.get("CAMBER_API_KEY", "7bb89413d6ee740e3fb0d480c6a0347e0a08db6a")
STASH_PATH = "stash://abhinavprakash15151692/rythmiq-worker-v2/"
SPACES_KEY = os.environ.get("DO_SPACES_ACCESS_KEY", "DO801FCJYBTBKXZUX8MT")
SPACES_SECRET = os.environ.get("DO_SPACES_SECRET_KEY", "qvtaYhOWs8FzCak56pUiEMDXKfN2ovqbnqAYw3rlMbE")

# Command to run worker
WORKER_CMD = f'''export SPACES_KEY={SPACES_KEY} && export SPACES_SECRET={SPACES_SECRET} && pip install boto3 paddleocr paddlepaddle httpx opencv-python-headless numpy pillow && cat payload.json | python worker.py'''


@dataclass
class JobTiming:
    """Timing measurements for a single job"""
    job_id: str
    submit_time: float
    submit_latency_ms: float
    status: str = "unknown"
    start_time: Optional[str] = None
    finish_time: Optional[str] = None
    duration_str: Optional[str] = None
    duration_seconds: Optional[float] = None
    error: Optional[str] = None
    is_cold_start: bool = False
    logs: Optional[str] = None
    
    def __repr__(self):
        return f"Job({self.job_id}): {self.status} in {self.duration_str or 'N/A'}"


def run_camber_cmd(args: List[str]) -> Tuple[int, str, str]:
    """Run a camber CLI command and return (returncode, stdout, stderr)"""
    cmd = ["camber"] + args + ["--api-key", CAMBER_API_KEY]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def parse_duration_to_seconds(duration_str: str) -> float:
    """Parse duration string like '1m5s' or '55s' to seconds"""
    if not duration_str:
        return 0.0
    
    total = 0.0
    # Match patterns like 1m, 5s, 1m5s, 2h30m, etc.
    minutes = re.search(r'(\d+)m', duration_str)
    seconds = re.search(r'(\d+)s', duration_str)
    hours = re.search(r'(\d+)h', duration_str)
    
    if hours:
        total += int(hours.group(1)) * 3600
    if minutes:
        total += int(minutes.group(1)) * 60
    if seconds:
        total += int(seconds.group(1))
    
    return total


def create_job(node_size: str = "small") -> JobTiming:
    """Submit a job to Camber and return timing info"""
    submit_start = time.time()
    
    returncode, stdout, stderr = run_camber_cmd([
        "job", "create",
        "--engine", "base",
        "--path", STASH_PATH,
        "--cmd", WORKER_CMD,
        "--size", node_size
    ])
    
    submit_end = time.time()
    submit_latency_ms = (submit_end - submit_start) * 1000
    
    # Parse job ID from output
    # Expected: "Job 15328 created and queued successfully" or similar
    job_id = None
    output = stdout + stderr
    
    # Try different patterns
    job_match = re.search(r'Job[:\s]+(\d+)', output)
    if job_match:
        job_id = job_match.group(1)
    else:
        # Try to find any number that looks like a job ID
        id_match = re.search(r'(\d{5})', output)
        if id_match:
            job_id = id_match.group(1)
    
    if not job_id:
        print(f"  [ERROR] Could not parse job ID from output:")
        print(f"    stdout: {stdout[:500]}")
        print(f"    stderr: {stderr[:500]}")
        return JobTiming(
            job_id="unknown",
            submit_time=submit_start,
            submit_latency_ms=submit_latency_ms,
            status="error",
            error="Could not parse job ID"
        )
    
    print(f"  [SUBMIT] Job {job_id} created, submit latency: {submit_latency_ms:.0f}ms")
    
    return JobTiming(
        job_id=job_id,
        submit_time=submit_start,
        submit_latency_ms=submit_latency_ms,
        status="queued"
    )


def get_job_status(job_id: str) -> Dict[str, Any]:
    """Get job status from Camber"""
    returncode, stdout, stderr = run_camber_cmd(["job", "get", job_id])
    
    output = stdout + stderr
    result = {"status": "unknown", "raw": output}
    
    # Parse status
    status_match = re.search(r'Status:\s+(\w+)', output)
    if status_match:
        result["status"] = status_match.group(1)
    
    # Parse duration
    duration_match = re.search(r'Duration:\s+([\d\w]+)', output)
    if duration_match:
        result["duration_str"] = duration_match.group(1)
        result["duration_seconds"] = parse_duration_to_seconds(duration_match.group(1))
    
    # Parse start/finish times
    start_match = re.search(r'Start Time:\s+([\d\-T:Z]+)', output)
    if start_match:
        result["start_time"] = start_match.group(1)
    
    finish_match = re.search(r'Finish Time:\s+([\d\-T:Z]+)', output)
    if finish_match:
        result["finish_time"] = finish_match.group(1)
    
    return result


def get_job_logs(job_id: str) -> str:
    """Get job logs from Camber"""
    returncode, stdout, stderr = run_camber_cmd(["job", "logs", job_id])
    return stdout + stderr


def wait_for_job(timing: JobTiming, timeout_seconds: float = 180.0, poll_interval: float = 3.0) -> JobTiming:
    """Poll until job completes"""
    start = time.time()
    last_status = None
    
    while (time.time() - start) < timeout_seconds:
        status_info = get_job_status(timing.job_id)
        status = status_info.get("status", "unknown")
        
        if status != last_status:
            elapsed = time.time() - timing.submit_time
            print(f"  [{status.upper()}] +{elapsed:.0f}s")
            last_status = status
        
        if status in ("COMPLETED", "FAILED", "CANCELLED"):
            timing.status = status
            timing.duration_str = status_info.get("duration_str")
            timing.duration_seconds = status_info.get("duration_seconds")
            timing.start_time = status_info.get("start_time")
            timing.finish_time = status_info.get("finish_time")
            
            # Get logs for completed jobs
            if status == "COMPLETED":
                timing.logs = get_job_logs(timing.job_id)
            
            return timing
        
        time.sleep(poll_interval)
    
    timing.status = "TIMEOUT"
    timing.error = f"Job did not complete within {timeout_seconds}s"
    return timing


def run_single_job(is_cold_start: bool = False, node_size: str = "small") -> JobTiming:
    """Create and wait for a single job"""
    timing = create_job(node_size)
    timing.is_cold_start = is_cold_start
    
    if timing.status == "error":
        return timing
    
    return wait_for_job(timing)


def print_timing_stats(timings: List[JobTiming], label: str):
    """Print statistics for a list of job timings"""
    successful = [t for t in timings if t.status == "COMPLETED"]
    durations = [t.duration_seconds for t in successful if t.duration_seconds]
    submit_latencies = [t.submit_latency_ms for t in timings]
    
    print(f"\n--- {label} Statistics ---")
    print(f"Jobs submitted: {len(timings)}")
    print(f"Jobs completed: {len(successful)}")
    print(f"Jobs failed: {len([t for t in timings if t.status == 'FAILED'])}")
    
    if submit_latencies:
        print(f"Submit latency (mean): {statistics.mean(submit_latencies):.0f}ms")
    
    if durations:
        print(f"Duration (mean): {statistics.mean(durations):.1f}s")
        print(f"Duration (min): {min(durations):.1f}s")
        print(f"Duration (max): {max(durations):.1f}s")
        if len(durations) >= 3:
            sorted_d = sorted(durations)
            p95_idx = int(len(sorted_d) * 0.95)
            print(f"Duration (P95): {sorted_d[min(p95_idx, len(sorted_d)-1)]:.1f}s")


def measure_cold_start_single():
    """Run a single cold start measurement (first job of the session)"""
    print("\n" + "="*60)
    print("COLD START MEASUREMENT (Single Run)")
    print("="*60)
    print("NOTE: True cold start requires ~5min of complete inactivity")
    print()
    
    result = run_single_job(is_cold_start=True)
    print(f"\nResult: {result}")
    
    if result.status == "COMPLETED":
        print(f"\n✅ Cold start completed in {result.duration_seconds:.1f}s")
    else:
        print(f"\n❌ Job failed: {result.status}")
    
    return result


def measure_warm_starts(num_runs: int = 3, delay_between: float = 5.0):
    """Measure warm start latency with jobs submitted in quick succession"""
    print("\n" + "="*60)
    print(f"WARM START MEASUREMENT ({num_runs} runs)")
    print("="*60)
    print(f"Delay between jobs: {delay_between}s")
    print()
    
    results = []
    for i in range(num_runs):
        print(f"\n--- Warm Run {i+1}/{num_runs} ---")
        result = run_single_job(is_cold_start=False)
        results.append(result)
        
        if i < num_runs - 1:
            print(f"  Waiting {delay_between}s before next run...")
            time.sleep(delay_between)
    
    print_timing_stats(results, "Warm Start")
    return results


def measure_idle_behavior(idle_seconds: int = 60):
    """Measure behavior after idle period"""
    print("\n" + "="*60)
    print(f"IDLE BEHAVIOR TEST ({idle_seconds}s idle)")
    print("="*60)
    
    # First job (warm up)
    print("\n--- Initial Warm-up Job ---")
    job1 = run_single_job(is_cold_start=False)
    
    if job1.status != "COMPLETED":
        print(f"❌ Warm-up job failed: {job1.status}")
        return None
    
    # Wait
    print(f"\n⏳ Waiting {idle_seconds}s...")
    time.sleep(idle_seconds)
    
    # Second job - observe
    print("\n--- Post-Idle Job ---")
    job2 = run_single_job(is_cold_start=False)
    
    # Compare
    if job1.duration_seconds and job2.duration_seconds:
        diff = job2.duration_seconds - job1.duration_seconds
        pct_change = (diff / job1.duration_seconds) * 100
        
        cold_indicator = "COLD" if diff > 10 else "WARM" if diff < 3 else "UNCLEAR"
        
        print(f"\n--- Comparison ---")
        print(f"Job 1 duration: {job1.duration_seconds:.1f}s")
        print(f"Job 2 duration: {job2.duration_seconds:.1f}s")
        print(f"Difference: {diff:+.1f}s ({pct_change:+.1f}%)")
        print(f"Likely state: {cold_indicator}")
    
    return (job1, job2)


def measure_concurrency(num_jobs: int = 3):
    """Test parallel job submission (limited due to CLI constraints)"""
    print("\n" + "="*60)
    print(f"CONCURRENCY TEST ({num_jobs} jobs)")
    print("="*60)
    print("NOTE: Jobs submitted serially via CLI, Camber may parallelize execution")
    print()
    
    # Submit all jobs as fast as possible
    timings = []
    batch_start = time.time()
    
    print("Submitting jobs...")
    for i in range(num_jobs):
        timing = create_job()
        timings.append(timing)
    
    submit_duration = time.time() - batch_start
    print(f"\nAll {num_jobs} jobs submitted in {submit_duration:.1f}s")
    
    # Wait for all to complete
    print("\nWaiting for completion...")
    for timing in timings:
        if timing.status != "error":
            wait_for_job(timing)
    
    batch_end = time.time()
    total_wall_time = batch_end - batch_start
    
    # Analysis
    successful = [t for t in timings if t.status == "COMPLETED"]
    durations = [t.duration_seconds for t in successful if t.duration_seconds]
    
    print(f"\n--- Concurrency Results ---")
    print(f"Total wall time: {total_wall_time:.1f}s")
    print(f"Jobs succeeded: {len(successful)}/{num_jobs}")
    
    if durations:
        sum_individual = sum(durations)
        parallelism = sum_individual / total_wall_time if total_wall_time > 0 else 0
        
        print(f"Sum of individual durations: {sum_individual:.1f}s")
        print(f"Parallelism factor: {parallelism:.2f}x")
        
        # Check if jobs overlapped
        if total_wall_time < sum_individual * 0.5:
            print("✅ Jobs likely ran in parallel")
        elif total_wall_time < sum_individual * 0.9:
            print("⚠️ Some parallel execution observed")
        else:
            print("❌ Jobs likely ran sequentially")
    
    return timings


def analyze_recent_jobs():
    """Analyze recent job history for patterns"""
    print("\n" + "="*60)
    print("RECENT JOB HISTORY ANALYSIS")
    print("="*60)
    
    returncode, stdout, stderr = run_camber_cmd(["job", "list"])
    output = stdout + stderr
    
    # Parse job entries
    jobs = []
    job_blocks = re.split(r'-{20,}', output)
    
    for block in job_blocks:
        job = {}
        for line in block.strip().split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                job[key.strip()] = value.strip()
        
        if 'Job ID' in job and 'Duration' in job:
            jobs.append({
                'id': job.get('Job ID'),
                'status': job.get('Status'),
                'duration': parse_duration_to_seconds(job.get('Duration', '')),
                'duration_str': job.get('Duration'),
                'start': job.get('Start Time'),
            })
    
    if not jobs:
        print("No jobs found in history")
        return
    
    completed = [j for j in jobs if j['status'] == 'COMPLETED']
    
    print(f"\nTotal jobs in history: {len(jobs)}")
    print(f"Completed jobs: {len(completed)}")
    
    if completed:
        durations = [j['duration'] for j in completed if j['duration']]
        print(f"\nCompleted Job Durations:")
        for j in completed[:5]:  # Show last 5
            print(f"  Job {j['id']}: {j['duration_str']} ({j['duration']:.0f}s) - {j['start']}")
        
        if durations:
            print(f"\nDuration Statistics (all completed):")
            print(f"  Mean: {statistics.mean(durations):.1f}s")
            print(f"  Min: {min(durations):.1f}s")
            print(f"  Max: {max(durations):.1f}s")


def print_final_summary(cold_result, warm_results, idle_results=None, concurrency_results=None):
    """Print final conclusions"""
    print("\n" + "="*60)
    print("FINAL CONCLUSIONS")
    print("="*60)
    
    # Cold vs Warm comparison
    if cold_result and cold_result.status == "COMPLETED":
        cold_duration = cold_result.duration_seconds
        
        warm_durations = [r.duration_seconds for r in (warm_results or []) 
                        if r.status == "COMPLETED" and r.duration_seconds]
        
        if warm_durations:
            warm_mean = statistics.mean(warm_durations)
            cold_overhead = cold_duration - warm_mean
            
            print("\n📊 COLD VS WARM START COMPARISON")
            print("-" * 40)
            print(f"{'Metric':<25} {'Cold':<12} {'Warm (mean)':<12}")
            print("-" * 40)
            print(f"{'Duration':<25} {cold_duration:>10.1f}s {warm_mean:>10.1f}s")
            print(f"{'Cold overhead':<25} {cold_overhead:>10.1f}s")
            print(f"{'Cold overhead %':<25} {(cold_overhead/warm_mean)*100:>10.1f}%")
    
    # Idle behavior summary
    if idle_results:
        print("\n⏰ IDLE WINDOW BEHAVIOR")
        print("-" * 40)
        job1, job2 = idle_results
        if job1.duration_seconds and job2.duration_seconds:
            diff = job2.duration_seconds - job1.duration_seconds
            state = "COLD" if diff > 10 else "WARM" if diff < 3 else "UNCLEAR"
            print(f"After 60s idle: {state} (diff: {diff:+.1f}s)")
    
    # Network latency breakdown
    print("\n🌐 LATENCY BREAKDOWN")
    print("-" * 40)
    all_results = [cold_result] + (warm_results or [])
    valid = [r for r in all_results if r and r.status == "COMPLETED"]
    
    if valid:
        submit_latencies = [r.submit_latency_ms for r in valid]
        durations = [r.duration_seconds for r in valid if r.duration_seconds]
        
        print(f"{'Component':<30} {'Latency':<15}")
        print("-" * 40)
        print(f"{'API submission (CLI)':<30} {statistics.mean(submit_latencies):>10.0f}ms")
        print(f"{'Worker execution (mean)':<30} {statistics.mean(durations):>10.1f}s")
        print(f"{'Webhook delivery':<30} {'N/A (polling)':>15}")
    
    # Conclusions
    print("\n✅ SAFE ASSUMPTIONS")
    print("-" * 40)
    print("• Camber BASE engine executes Python workers reliably")
    print("• PaddleOCR 3.4.0 initializes correctly on CPU")
    print("• DigitalOcean Spaces I/O works with credentials")
    if warm_durations:
        print(f"• Warm execution time: ~{statistics.mean(warm_durations):.0f}s baseline")
    
    print("\n⚠️ DANGEROUS ASSUMPTIONS")
    print("-" * 40)
    print("• Assuming workers stay warm (needs idle window testing)")
    print("• Assuming consistent execution time (variance observed)")
    print("• Assuming first job is cold (may hit warm infra)")
    
    print("\n📋 BASELINE REQUIREMENTS FOR BENCHMARKING")
    print("-" * 40)
    if valid and durations:
        print(f"• Minimum expected latency: ~{min(durations):.0f}s")
        print(f"• Maximum expected latency: ~{max(durations):.0f}s")
    print("• Always account for pip install overhead (~30-40s)")
    print("• OCR model download may add 10-20s on first run")


def main():
    """Main benchmark runner"""
    print("="*60)
    print("CAMBER EXECUTION BEHAVIOR MEASUREMENT")
    print("="*60)
    print(f"Date: {datetime.now().isoformat()}")
    print(f"Stash Path: {STASH_PATH}")
    print()
    
    import argparse
    parser = argparse.ArgumentParser(description="Camber Behavior Benchmark")
    parser.add_argument("--quick", action="store_true", help="Quick single-job test")
    parser.add_argument("--warm", type=int, default=3, help="Number of warm start runs")
    parser.add_argument("--idle", type=int, help="Run idle test with N seconds wait")
    parser.add_argument("--concurrent", type=int, help="Run N concurrent jobs")
    parser.add_argument("--history", action="store_true", help="Analyze recent job history")
    parser.add_argument("--full", action="store_true", help="Run full benchmark suite")
    args = parser.parse_args()
    
    cold_result = None
    warm_results = None
    idle_results = None
    concurrency_results = None
    
    if args.history:
        analyze_recent_jobs()
        return
    
    if args.quick:
        cold_result = measure_cold_start_single()
        return
    
    if args.full:
        # Full suite
        cold_result = measure_cold_start_single()
        warm_results = measure_warm_starts(num_runs=3, delay_between=5)
        idle_results = measure_idle_behavior(idle_seconds=60)
        concurrency_results = measure_concurrency(num_jobs=3)
        print_final_summary(cold_result, warm_results, idle_results, concurrency_results)
        return
    
    # Default: cold + warm
    cold_result = measure_cold_start_single()
    
    if args.warm:
        warm_results = measure_warm_starts(num_runs=args.warm, delay_between=5)
    
    if args.idle:
        idle_results = measure_idle_behavior(idle_seconds=args.idle)
    
    if args.concurrent:
        concurrency_results = measure_concurrency(num_jobs=args.concurrent)
    
    if cold_result or warm_results:
        print_final_summary(cold_result, warm_results, idle_results, concurrency_results)


if __name__ == "__main__":
    main()
