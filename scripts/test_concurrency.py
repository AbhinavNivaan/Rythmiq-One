#!/usr/bin/env python3
"""Simple concurrency test for Camber"""

import subprocess
import time
import re

CAMBER_API_KEY = "7bb89413d6ee740e3fb0d480c6a0347e0a08db6a"
STASH_PATH = "stash://abhinavprakash15151692/rythmiq-worker-v2/"
WORKER_CMD = "export SPACES_KEY=DO801FCJYBTBKXZUX8MT && export SPACES_SECRET=qvtaYhOWs8FzCak56pUiEMDXKfN2ovqbnqAYw3rlMbE && pip install boto3 paddleocr paddlepaddle httpx opencv-python-headless numpy pillow && cat payload.json | python worker.py"

def submit_job():
    result = subprocess.run([
        "camber", "job", "create",
        "--engine", "base",
        "--path", STASH_PATH,
        "--cmd", WORKER_CMD,
        "--size", "small",
        "--api-key", CAMBER_API_KEY
    ], capture_output=True, text=True)
    output = result.stdout + result.stderr
    job_match = re.search(r'Job[:\s]+(\d+)', output)
    return job_match.group(1) if job_match else None

def get_job_status(job_id):
    result = subprocess.run([
        "camber", "job", "get", job_id,
        "--api-key", CAMBER_API_KEY
    ], capture_output=True, text=True)
    output = result.stdout + result.stderr
    status_match = re.search(r'Status:\s+(\w+)', output)
    duration_match = re.search(r'Duration:\s+([\d\w]+)', output)
    start_match = re.search(r'Start Time:\s+([\d\-T:Z]+)', output)
    finish_match = re.search(r'Finish Time:\s+([\d\-T:Z]+)', output)
    return {
        "status": status_match.group(1) if status_match else "unknown",
        "duration": duration_match.group(1) if duration_match else "N/A",
        "start": start_match.group(1) if start_match else None,
        "finish": finish_match.group(1) if finish_match else None,
    }

def main():
    print("=" * 60)
    print("CONCURRENCY TEST (5 simultaneous jobs)")
    print("=" * 60)
    
    # Submit 5 jobs rapidly
    job_ids = []
    batch_start = time.time()
    
    print("\nSubmitting 5 jobs...")
    for i in range(5):
        job_id = submit_job()
        if job_id:
            job_ids.append(job_id)
            submit_time = time.time() - batch_start
            print(f"  Job {i+1}: {job_id} submitted at +{submit_time:.1f}s")
    
    submit_end = time.time()
    print(f"\nAll jobs submitted in {submit_end - batch_start:.1f}s")
    
    # Wait and poll until all complete
    print("\nWaiting for completion...")
    while True:
        all_done = True
        for job_id in job_ids:
            info = get_job_status(job_id)
            if info["status"] not in ("COMPLETED", "FAILED", "CANCELLED"):
                all_done = False
                break
        
        if all_done:
            break
        
        elapsed = time.time() - batch_start
        print(f"  +{elapsed:.0f}s - Still running...")
        time.sleep(10)
    
    batch_end = time.time()
    
    # Final status
    print("\n" + "=" * 60)
    print("FINAL STATUS")
    print("=" * 60)
    
    results = []
    for job_id in job_ids:
        info = get_job_status(job_id)
        results.append(info)
        print(f"  Job {job_id}: {info['status']} ({info['duration']}) - Started: {info['start']}")
    
    # Analysis
    completed = [r for r in results if r["status"] == "COMPLETED"]
    total_wall = batch_end - batch_start
    
    print("\n" + "=" * 60)
    print("ANALYSIS")
    print("=" * 60)
    print(f"Jobs completed: {len(completed)}/5")
    print(f"Total wall time: {total_wall:.1f}s")
    
    # Check for overlap based on start times
    starts = [r["start"] for r in completed if r["start"]]
    if starts:
        print(f"\nStart times: {starts}")
        # If all started within 10s, likely parallel
        # If spread out, likely sequential

if __name__ == "__main__":
    main()
