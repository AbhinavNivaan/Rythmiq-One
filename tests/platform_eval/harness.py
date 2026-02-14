#!/usr/bin/env python3
"""
Camber Platform Evaluation - Test Harness

This module provides utilities for running and measuring platform tests.
All timing data is captured and can be exported for analysis.

Usage:
    python -m tests.platform_eval.harness --test cold_start
    python -m tests.platform_eval.harness --test all
"""

import os
import sys
import json
import time
import subprocess
import argparse
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional
from pathlib import Path


@dataclass
class JobResult:
    """Result of a single Camber job."""
    job_id: str
    test_name: str
    status: str
    submit_time: float
    start_time: Optional[float]
    end_time: Optional[float]
    duration_seconds: Optional[float]
    queue_time_seconds: Optional[float]
    logs: str
    metadata: Dict


@dataclass 
class TestResult:
    """Result of a complete test run."""
    test_name: str
    started_at: str
    completed_at: str
    jobs: List[JobResult]
    summary: Dict


class CamberTestHarness:
    """Harness for running Camber platform evaluation tests."""
    
    def __init__(self, api_key: str, stash_path: str):
        self.api_key = api_key
        self.stash_path = stash_path
        self.results_dir = Path("test_results")
        self.results_dir.mkdir(exist_ok=True)
        
    def run_command(self, cmd: str) -> tuple[int, str, str]:
        """Run a shell command and return exit code, stdout, stderr."""
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True
        )
        return result.returncode, result.stdout, result.stderr
    
    def create_job(self, cmd: str, size: str = "small") -> str:
        """Create a Camber job and return the job ID."""
        create_cmd = f'''camber job create --engine base --size {size} \
            --path {self.stash_path} \
            --cmd '{cmd}' \
            --api-key "{self.api_key}"'''
        
        code, stdout, stderr = self.run_command(create_cmd)
        
        if code != 0:
            raise RuntimeError(f"Failed to create job: {stderr}")
        
        # Parse job ID from output
        for line in stdout.split("\n"):
            if "Job ID:" in line:
                return line.split(":")[-1].strip()
        
        raise RuntimeError(f"Could not parse job ID from: {stdout}")
    
    def get_job_status(self, job_id: str) -> Dict:
        """Get job status and details."""
        cmd = f'camber job get {job_id} --api-key "{self.api_key}"'
        code, stdout, stderr = self.run_command(cmd)
        
        status = {
            "job_id": job_id,
            "status": "UNKNOWN",
            "duration": None,
            "raw_output": stdout
        }
        
        for line in stdout.split("\n"):
            if "Status:" in line:
                status["status"] = line.split(":")[-1].strip()
            elif "Duration:" in line:
                dur_str = line.split(":")[-1].strip()
                # Parse duration like "25s" or "1m30s"
                if dur_str.endswith("s"):
                    if "m" in dur_str:
                        parts = dur_str.replace("s", "").split("m")
                        status["duration"] = int(parts[0]) * 60 + int(parts[1])
                    else:
                        status["duration"] = int(dur_str.replace("s", ""))
        
        return status
    
    def get_job_logs(self, job_id: str) -> str:
        """Get job logs."""
        cmd = f'camber job logs {job_id} --api-key "{self.api_key}"'
        code, stdout, stderr = self.run_command(cmd)
        return stdout
    
    def wait_for_job(self, job_id: str, timeout: int = 300, poll_interval: int = 5) -> Dict:
        """Wait for a job to complete."""
        start = time.time()
        
        while time.time() - start < timeout:
            status = self.get_job_status(job_id)
            
            if status["status"] in ["COMPLETED", "FAILED", "CANCELLED"]:
                return status
            
            time.sleep(poll_interval)
        
        raise TimeoutError(f"Job {job_id} did not complete within {timeout}s")
    
    def save_results(self, test_result: TestResult):
        """Save test results to JSON file."""
        filename = f"{test_result.test_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = self.results_dir / filename
        
        with open(filepath, "w") as f:
            json.dump(asdict(test_result), f, indent=2, default=str)
        
        print(f"Results saved to: {filepath}")
        return filepath


def create_timing_wrapper(inner_cmd: str) -> str:
    """Wrap a command with timing instrumentation."""
    return f'''
echo "===TIMING_START===$(date +%s.%N)==="
{inner_cmd}
EXIT_CODE=$?
echo "===TIMING_END===$(date +%s.%N)==="
echo "===EXIT_CODE===$EXIT_CODE==="
exit $EXIT_CODE
'''


def parse_timing_from_logs(logs: str) -> Dict:
    """Parse timing information from job logs."""
    result = {
        "start_time": None,
        "end_time": None,
        "duration": None,
        "exit_code": None
    }
    
    for line in logs.split("\n"):
        if "===TIMING_START===" in line:
            try:
                ts = line.split("===")[2]
                result["start_time"] = float(ts)
            except:
                pass
        elif "===TIMING_END===" in line:
            try:
                ts = line.split("===")[2]
                result["end_time"] = float(ts)
            except:
                pass
        elif "===EXIT_CODE===" in line:
            try:
                code = line.split("===")[2]
                result["exit_code"] = int(code)
            except:
                pass
    
    if result["start_time"] and result["end_time"]:
        result["duration"] = result["end_time"] - result["start_time"]
    
    return result


# Test implementations will be in separate files
# This harness provides the infrastructure

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Camber Platform Evaluation Harness")
    parser.add_argument("--test", choices=["cold_start", "warm_start", "concurrent", "all"],
                       help="Test to run")
    parser.add_argument("--api-key", default=os.environ.get("CAMBER_API_KEY"),
                       help="Camber API key")
    parser.add_argument("--stash-path", default="stash://abhinavprakash15151692/eval-test/worker",
                       help="Stash path for test files")
    
    args = parser.parse_args()
    
    if not args.api_key:
        print("Error: CAMBER_API_KEY not set")
        sys.exit(1)
    
    harness = CamberTestHarness(args.api_key, args.stash_path)
    print(f"Harness initialized. Results will be saved to: {harness.results_dir}")
    print("Run specific tests with: python test_runner.py")
