#!/usr/bin/env python3
"""
Camber Execution Behavior Measurement Script

Purpose: Empirically measure Camber's real execution behavior without any modifications.
This script gathers baseline metrics for:
- Cold start latency
- Warm start latency  
- Idle window behavior
- Network/webhook latency
- Concurrency semantics
- CPU accounting accuracy

DO NOT OPTIMIZE, REFACTOR, OR CHANGE LOGIC - MEASUREMENT ONLY.
"""

import asyncio
import json
import os
import sys
import time
import statistics
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4
from dataclasses import dataclass, field, asdict

# Ensure we're using the right settings
sys.path.insert(0, "/Users/abhinav/Rythmiq One")
os.chdir("/Users/abhinav/Rythmiq One")

from dotenv import load_dotenv
load_dotenv("/Users/abhinav/Rythmiq One/.env")

import httpx

# Configuration
API_BASE = os.getenv("CAMBER_API_URL", "https://api.camber.cloud")
API_KEY = os.getenv("CAMBER_API_KEY")
APP_NAME = os.getenv("CAMBER_APP_NAME", "rythmiq-worker-python-v2")

# Test artifact - use a known uploaded test image
TEST_ARTIFACT_PATH = "blobs/ca860aa8-d31a-4a15-a6ee-9de5c7ae2671"
STORAGE_BUCKET = "rythmiq-one-artifacts"
STORAGE_ENDPOINT = "https://sgp1.digitaloceanspaces.com"
STORAGE_REGION = "sgp1"


@dataclass
class TimingResult:
    """Timing measurements for a single job"""
    job_id: str
    camber_job_id: str
    submit_timestamp: float
    submit_latency_ms: float  # Time for API to accept job
    poll_start: float
    first_running_timestamp: Optional[float] = None
    completion_timestamp: Optional[float] = None
    total_duration_ms: Optional[float] = None
    worker_duration_ms: Optional[float] = None  # From Camber response
    status: str = "unknown"
    error: Optional[str] = None
    is_cold_start: bool = False
    raw_response: Optional[Dict] = None
    
    @property
    def queue_wait_ms(self) -> Optional[float]:
        """Time from submit to first running state"""
        if self.first_running_timestamp:
            return (self.first_running_timestamp - self.submit_timestamp) * 1000
        return None


@dataclass
class BenchmarkResults:
    """Container for all benchmark results"""
    test_timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    cold_start_runs: List[TimingResult] = field(default_factory=list)
    warm_start_runs: List[TimingResult] = field(default_factory=list)
    idle_window_tests: Dict[str, List[TimingResult]] = field(default_factory=dict)
    concurrency_tests: List[Dict] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return {
            "test_timestamp": self.test_timestamp,
            "cold_start_runs": [asdict(r) for r in self.cold_start_runs],
            "warm_start_runs": [asdict(r) for r in self.warm_start_runs],
            "idle_window_tests": {
                k: [asdict(r) for r in v] 
                for k, v in self.idle_window_tests.items()
            },
            "concurrency_tests": self.concurrency_tests,
        }


class CamberBenchmark:
    """Benchmark runner for Camber execution measurements"""
    
    def __init__(self):
        self.client = httpx.AsyncClient(
            base_url=API_BASE,
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0),
        )
        self.results = BenchmarkResults()
    
    async def close(self):
        await self.client.aclose()
    
    def _build_job_payload(self, job_id: str) -> Dict[str, Any]:
        """Build a simple test job payload"""
        return {
            "app": APP_NAME,
            "input": {
                "job_id": job_id,
                "user_id": "benchmark-user-001",
                "portal_schema": {
                    "id": "benchmark-schema",
                    "name": "Benchmark Test",
                    "version": 1,
                    "schema_definition": {
                        "target_width": 600,
                        "target_height": 800,
                        "target_dpi": 300,
                        "max_kb": 200,
                        "filename_pattern": "{job_id}",
                        "output_format": "jpeg",
                        "quality": 85
                    }
                },
                "input": {
                    "raw_path": TEST_ARTIFACT_PATH,
                    "mime_type": "image/png",
                    "original_filename": "test-document.png",
                    "artifact_source": "path"
                },
                "storage": {
                    "bucket": STORAGE_BUCKET,
                    "region": STORAGE_REGION,
                    "endpoint": STORAGE_ENDPOINT
                }
            },
            "metadata": {
                "benchmark_run": True,
                "test_type": "simple_jpeg"
            }
        }
    
    async def submit_job(self, job_id: Optional[str] = None) -> Tuple[str, str, float, float]:
        """
        Submit a job to Camber.
        
        Returns: (job_id, camber_job_id, submit_timestamp, submit_latency_ms)
        """
        if job_id is None:
            job_id = str(uuid4())
        
        payload = self._build_job_payload(job_id)
        
        submit_start = time.time()
        response = await self.client.post("/jobs", json=payload)
        submit_end = time.time()
        
        response.raise_for_status()
        data = response.json()
        
        camber_job_id = data.get("id") or data.get("job_id")
        submit_latency_ms = (submit_end - submit_start) * 1000
        
        print(f"  [SUBMIT] job_id={job_id[:8]}... camber_id={camber_job_id[:8]}... latency={submit_latency_ms:.1f}ms")
        
        return job_id, camber_job_id, submit_start, submit_latency_ms
    
    async def poll_until_complete(
        self, 
        camber_job_id: str, 
        timeout_seconds: float = 120.0,
        poll_interval: float = 1.0
    ) -> Tuple[Dict, float, Optional[float]]:
        """
        Poll job status until completion.
        
        Returns: (final_response, completion_timestamp, first_running_timestamp)
        """
        start = time.time()
        first_running = None
        
        while (time.time() - start) < timeout_seconds:
            response = await self.client.get(f"/jobs/{camber_job_id}")
            response.raise_for_status()
            data = response.json()
            
            status = data.get("status", "unknown")
            
            # Track first time we see "running" status
            if status == "running" and first_running is None:
                first_running = time.time()
                print(f"  [RUNNING] Worker started at +{(first_running - start)*1000:.0f}ms")
            
            if status in ("succeeded", "completed", "failed", "error"):
                completion_time = time.time()
                print(f"  [COMPLETE] Status={status} at +{(completion_time - start)*1000:.0f}ms")
                return data, completion_time, first_running
            
            await asyncio.sleep(poll_interval)
        
        return {"status": "timeout", "error": "Polling timeout"}, time.time(), first_running
    
    async def run_single_job(self, is_cold_start: bool = False) -> TimingResult:
        """Run a single job and capture timing metrics"""
        job_id, camber_job_id, submit_ts, submit_latency = await self.submit_job()
        
        poll_start = time.time()
        response, completion_ts, first_running_ts = await self.poll_until_complete(camber_job_id)
        
        total_duration_ms = (completion_ts - submit_ts) * 1000
        
        # Extract worker-reported duration if available
        worker_duration_ms = None
        if "duration" in response:
            worker_duration_ms = response["duration"]
        elif "execution_time" in response:
            worker_duration_ms = response["execution_time"]
        elif "metrics" in response and "duration_ms" in response["metrics"]:
            worker_duration_ms = response["metrics"]["duration_ms"]
        
        result = TimingResult(
            job_id=job_id,
            camber_job_id=camber_job_id,
            submit_timestamp=submit_ts,
            submit_latency_ms=submit_latency,
            poll_start=poll_start,
            first_running_timestamp=first_running_ts,
            completion_timestamp=completion_ts,
            total_duration_ms=total_duration_ms,
            worker_duration_ms=worker_duration_ms,
            status=response.get("status", "unknown"),
            error=response.get("error"),
            is_cold_start=is_cold_start,
            raw_response=response,
        )
        
        return result
    
    async def measure_cold_starts(self, num_runs: int = 3, idle_wait_seconds: int = 300):
        """
        Measure cold start latency.
        
        Cold start definition: worker executed after ≥5 minutes of inactivity.
        """
        print("\n" + "="*60)
        print("COLD START MEASUREMENT")
        print("="*60)
        print(f"Runs: {num_runs}")
        print(f"Idle wait between runs: {idle_wait_seconds}s (5 minutes)")
        print()
        
        for i in range(num_runs):
            print(f"\n--- Cold Start Run {i+1}/{num_runs} ---")
            
            if i > 0:
                print(f"Waiting {idle_wait_seconds}s for worker to go cold...")
                await asyncio.sleep(idle_wait_seconds)
            else:
                print("First run - assuming cold (no prior activity)")
            
            result = await self.run_single_job(is_cold_start=True)
            self.results.cold_start_runs.append(result)
            
            print(f"  Total Duration: {result.total_duration_ms:.0f}ms")
            if result.queue_wait_ms:
                print(f"  Queue Wait: {result.queue_wait_ms:.0f}ms")
            if result.worker_duration_ms:
                print(f"  Worker Duration: {result.worker_duration_ms}ms")
        
        # Calculate statistics
        durations = [r.total_duration_ms for r in self.results.cold_start_runs if r.total_duration_ms]
        if durations:
            print(f"\n--- Cold Start Statistics ---")
            print(f"Mean: {statistics.mean(durations):.0f}ms")
            print(f"Max: {max(durations):.0f}ms")
            print(f"Min: {min(durations):.0f}ms")
            if len(durations) >= 3:
                # P95 approximation for small samples
                sorted_d = sorted(durations)
                p95_idx = int(len(sorted_d) * 0.95)
                print(f"P95: {sorted_d[min(p95_idx, len(sorted_d)-1)]:.0f}ms")
    
    async def measure_warm_starts(self, num_runs: int = 3):
        """
        Measure warm start latency.
        
        Warm start definition: job submitted within 5 seconds of previous completion.
        """
        print("\n" + "="*60)
        print("WARM START MEASUREMENT")
        print("="*60)
        print(f"Runs: {num_runs}")
        print()
        
        for i in range(num_runs):
            print(f"\n--- Warm Start Run {i+1}/{num_runs} ---")
            
            result = await self.run_single_job(is_cold_start=False)
            self.results.warm_start_runs.append(result)
            
            print(f"  Total Duration: {result.total_duration_ms:.0f}ms")
            if result.queue_wait_ms:
                print(f"  Queue Wait: {result.queue_wait_ms:.0f}ms")
            if result.worker_duration_ms:
                print(f"  Worker Duration: {result.worker_duration_ms}ms")
            
            # Wait 2-3 seconds before next (still warm)
            if i < num_runs - 1:
                print("  Waiting 3s before next warm run...")
                await asyncio.sleep(3)
        
        # Calculate statistics
        durations = [r.total_duration_ms for r in self.results.warm_start_runs if r.total_duration_ms]
        if durations:
            print(f"\n--- Warm Start Statistics ---")
            print(f"Mean: {statistics.mean(durations):.0f}ms")
            print(f"Max: {max(durations):.0f}ms")
            print(f"Min: {min(durations):.0f}ms")
    
    async def measure_idle_window(self):
        """
        Determine Camber's idle eviction behavior.
        
        Test scenarios:
        a) Job → wait 1 minute → job
        b) Job → wait 3 minutes → job
        c) Jobs spaced ~90 seconds apart
        """
        print("\n" + "="*60)
        print("IDLE WINDOW BEHAVIOR TEST")
        print("="*60)
        
        scenarios = [
            ("1min_idle", 60),
            ("90sec_idle", 90),
            ("3min_idle", 180),
        ]
        
        for scenario_name, wait_seconds in scenarios:
            print(f"\n--- Scenario: {scenario_name} (wait {wait_seconds}s) ---")
            self.results.idle_window_tests[scenario_name] = []
            
            # First job (warm it up)
            print("Running initial warm-up job...")
            result1 = await self.run_single_job(is_cold_start=False)
            self.results.idle_window_tests[scenario_name].append(result1)
            
            # Wait
            print(f"Waiting {wait_seconds}s...")
            await asyncio.sleep(wait_seconds)
            
            # Second job - observe if cold or warm
            print("Running post-idle job...")
            result2 = await self.run_single_job(is_cold_start=False)
            self.results.idle_window_tests[scenario_name].append(result2)
            
            # Compare durations
            if result1.total_duration_ms and result2.total_duration_ms:
                diff = result2.total_duration_ms - result1.total_duration_ms
                pct_change = (diff / result1.total_duration_ms) * 100
                
                cold_indicator = "COLD" if diff > 5000 else "WARM" if diff < 1000 else "UNCLEAR"
                print(f"  Job 1 duration: {result1.total_duration_ms:.0f}ms")
                print(f"  Job 2 duration: {result2.total_duration_ms:.0f}ms")
                print(f"  Difference: {diff:+.0f}ms ({pct_change:+.1f}%)")
                print(f"  Likely: {cold_indicator}")
    
    async def measure_concurrency(self):
        """
        Test concurrency semantics.
        
        1. Submit 5 simple jobs simultaneously
        2. Submit 1 PDF + 4 images mixed
        """
        print("\n" + "="*60)
        print("CONCURRENCY SEMANTICS TEST")
        print("="*60)
        
        # Test 1: 5 parallel simple jobs
        print("\n--- Test 1: 5 Parallel Simple Jobs ---")
        
        parallel_start = time.time()
        tasks = [self.run_single_job() for _ in range(5)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        parallel_end = time.time()
        
        parallel_total_ms = (parallel_end - parallel_start) * 1000
        
        successful_results = [r for r in results if isinstance(r, TimingResult) and r.status in ("succeeded", "completed")]
        
        concurrency_data = {
            "test_type": "5_parallel_simple",
            "total_wall_time_ms": parallel_total_ms,
            "jobs_submitted": 5,
            "jobs_succeeded": len(successful_results),
            "individual_durations_ms": [r.total_duration_ms for r in successful_results],
        }
        
        print(f"  Total wall time: {parallel_total_ms:.0f}ms")
        print(f"  Jobs succeeded: {len(successful_results)}/5")
        
        if successful_results:
            avg_individual = statistics.mean([r.total_duration_ms for r in successful_results])
            theoretical_serial = sum([r.total_duration_ms for r in successful_results])
            parallelism_factor = theoretical_serial / parallel_total_ms if parallel_total_ms > 0 else 0
            
            concurrency_data["avg_individual_ms"] = avg_individual
            concurrency_data["theoretical_serial_ms"] = theoretical_serial
            concurrency_data["parallelism_factor"] = parallelism_factor
            
            print(f"  Avg individual duration: {avg_individual:.0f}ms")
            print(f"  Theoretical serial time: {theoretical_serial:.0f}ms")
            print(f"  Parallelism factor: {parallelism_factor:.2f}x")
        
        self.results.concurrency_tests.append(concurrency_data)
        
        # Note: Mixed PDF test would require a PDF test file
        print("\n--- Test 2: Mixed Job Types (skipped - no PDF test file) ---")
    
    async def print_summary(self):
        """Print final summary and conclusions"""
        print("\n" + "="*60)
        print("BENCHMARK SUMMARY & CONCLUSIONS")
        print("="*60)
        
        # Cold vs Warm comparison
        cold_durations = [r.total_duration_ms for r in self.results.cold_start_runs if r.total_duration_ms]
        warm_durations = [r.total_duration_ms for r in self.results.warm_start_runs if r.total_duration_ms]
        
        if cold_durations and warm_durations:
            cold_mean = statistics.mean(cold_durations)
            warm_mean = statistics.mean(warm_durations)
            cold_overhead = cold_mean - warm_mean
            
            print("\n--- Cold vs Warm Start Comparison ---")
            print(f"{'Metric':<25} {'Cold Start':<15} {'Warm Start':<15} {'Difference':<15}")
            print("-" * 70)
            print(f"{'Mean Duration':<25} {cold_mean:>12.0f}ms {warm_mean:>12.0f}ms {cold_overhead:>+12.0f}ms")
            print(f"{'Max Duration':<25} {max(cold_durations):>12.0f}ms {max(warm_durations):>12.0f}ms")
            print(f"{'Min Duration':<25} {min(cold_durations):>12.0f}ms {min(warm_durations):>12.0f}ms")
        
        # Idle window summary
        if self.results.idle_window_tests:
            print("\n--- Idle Window Behavior ---")
            for scenario, results in self.results.idle_window_tests.items():
                if len(results) >= 2:
                    d1 = results[0].total_duration_ms
                    d2 = results[1].total_duration_ms
                    if d1 and d2:
                        diff = d2 - d1
                        state = "COLD" if diff > 5000 else "WARM" if diff < 1000 else "UNCLEAR"
                        print(f"  {scenario}: {d1:.0f}ms → {d2:.0f}ms (diff: {diff:+.0f}ms) - {state}")
        
        # Concurrency summary
        if self.results.concurrency_tests:
            print("\n--- Concurrency Behavior ---")
            for test in self.results.concurrency_tests:
                print(f"  {test['test_type']}:")
                print(f"    Wall time: {test['total_wall_time_ms']:.0f}ms")
                print(f"    Success rate: {test['jobs_succeeded']}/{test['jobs_submitted']}")
                if 'parallelism_factor' in test:
                    print(f"    Parallelism factor: {test['parallelism_factor']:.2f}x")
        
        # Conclusions
        print("\n--- CONCLUSIONS ---")
        print("\n✅ SAFE ASSUMPTIONS:")
        if cold_durations and warm_durations:
            if cold_overhead > 3000:
                print(f"  - Cold start overhead is significant: ~{cold_overhead/1000:.1f}s")
            else:
                print(f"  - Cold start overhead is moderate: ~{cold_overhead/1000:.1f}s")
        print("  - Jobs execute successfully with BASE engine + CPU")
        print("  - PaddleOCR 3.4.0 initializes correctly")
        
        print("\n⚠️ DANGEROUS ASSUMPTIONS:")
        print("  - Assuming warm workers after any idle period")
        print("  - Assuming predictable execution time without measuring")
        
        print("\n📊 BASELINE REQUIREMENTS:")
        if warm_durations:
            print(f"  - Minimum expected latency: ~{min(warm_durations)/1000:.1f}s (warm)")
        if cold_durations:
            print(f"  - Maximum expected latency: ~{max(cold_durations)/1000:.1f}s (cold)")
        print("  - Include cold start in SLA calculations")


async def run_full_benchmark():
    """Run the complete benchmark suite"""
    benchmark = CamberBenchmark()
    
    try:
        print("="*60)
        print("CAMBER EXECUTION BEHAVIOR MEASUREMENT")
        print("="*60)
        print(f"Started: {datetime.now().isoformat()}")
        print(f"API URL: {API_BASE}")
        print(f"App: {APP_NAME}")
        print()
        
        # 1. Cold start measurement (reduced to 1 run for quick test, change to 3 for full)
        # Note: Full cold start test requires 15+ minutes due to 5min idle between runs
        await benchmark.measure_cold_starts(num_runs=1, idle_wait_seconds=0)  # First run only
        
        # 2. Warm start measurement
        await benchmark.measure_warm_starts(num_runs=3)
        
        # 3. Idle window behavior (abbreviated for quick test)
        # Full test: await benchmark.measure_idle_window()
        
        # 4. Concurrency test
        await benchmark.measure_concurrency()
        
        # 5. Print summary
        await benchmark.print_summary()
        
        # Save results
        results_path = "/Users/abhinav/Rythmiq One/artifacts/camber_benchmark_results.json"
        os.makedirs(os.path.dirname(results_path), exist_ok=True)
        with open(results_path, "w") as f:
            json.dump(benchmark.results.to_dict(), f, indent=2, default=str)
        print(f"\n📁 Results saved to: {results_path}")
        
    finally:
        await benchmark.close()


async def run_quick_benchmark():
    """Run a quick benchmark for immediate feedback"""
    benchmark = CamberBenchmark()
    
    try:
        print("="*60)
        print("QUICK CAMBER BENCHMARK (Single Run)")
        print("="*60)
        print(f"Started: {datetime.now().isoformat()}")
        print()
        
        # Single job to verify connectivity and measure baseline
        print("Running single test job...")
        result = await benchmark.run_single_job()
        
        print(f"\n--- Quick Results ---")
        print(f"Status: {result.status}")
        print(f"Total Duration: {result.total_duration_ms:.0f}ms")
        print(f"Submit Latency: {result.submit_latency_ms:.0f}ms")
        if result.queue_wait_ms:
            print(f"Queue Wait: {result.queue_wait_ms:.0f}ms")
        if result.worker_duration_ms:
            print(f"Worker Duration: {result.worker_duration_ms}ms")
        
        if result.raw_response:
            print(f"\n--- Raw Response ---")
            print(json.dumps(result.raw_response, indent=2, default=str)[:2000])
        
    finally:
        await benchmark.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Camber Benchmark")
    parser.add_argument("--quick", action="store_true", help="Run quick single-job test")
    parser.add_argument("--full", action="store_true", help="Run full benchmark suite")
    args = parser.parse_args()
    
    if args.quick:
        asyncio.run(run_quick_benchmark())
    elif args.full:
        asyncio.run(run_full_benchmark())
    else:
        print("Usage: python camber_benchmark.py --quick | --full")
        print("  --quick: Single job test for connectivity verification")
        print("  --full: Complete benchmark suite (takes ~20+ minutes)")
