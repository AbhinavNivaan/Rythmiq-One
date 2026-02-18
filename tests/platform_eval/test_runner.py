#!/usr/bin/env python3
"""
Camber Platform Evaluation - Test Runner

Executes all platform evaluation tests and generates reports.

Processing Stack Under Test:
├─ PaddleOCR (OCR) - 44s init overhead
├─ Google Vision API (OCR for critical docs)
├─ OpenCV (auto-crop, enhancement)
├─ PyMuPDF (PDF processing)
├─ img2pdf (format conversion)
├─ rembg (background removal) - ML model
└─ Pillow (DPI, compression)

Usage:
    # Run component init baseline
    python test_runner.py --test components
    
    # Run specific path tests
    python test_runner.py --test fast_path
    python test_runner.py --test enhancement
    python test_runner.py --test background_removal
    python test_runner.py --test pdf_processing
    python test_runner.py --test ocr_paddle
    python test_runner.py --test ocr_google
    python test_runner.py --test full_pipeline
    
    # Run concurrency tests
    python test_runner.py --test concurrent_single
    python test_runner.py --test concurrent_multi
    
    # Run all tests
    python test_runner.py --test all
"""

import os
import sys
import json
import time
import argparse
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.platform_eval.harness import (
    CamberTestHarness, 
    TestResult, 
    JobResult,
    create_timing_wrapper,
    parse_timing_from_logs
)


class PlatformEvaluator:
    """Runs platform evaluation tests."""
    
    def __init__(self, api_key: str, stash_base: str):
        self.harness = CamberTestHarness(api_key, stash_base)
        self.stash_base = stash_base
        
    def test_cold_start_fast_path(self) -> TestResult:
        """
        Test 1A: Cold start baseline for fast path (no OCR).
        
        Clears cache and measures worst-case latency.
        """
        print("\n" + "="*60)
        print("TEST 1A: Cold Start - Fast Path (No OCR)")
        print("="*60)
        
        test_name = "cold_start_fast_path"
        started_at = datetime.now().isoformat()
        jobs = []
        
        # Fast path command - just schema compliance, no OCR
        inner_cmd = '''
export PYTHONPATH=/home/camber/workdir:$PYTHONPATH
python3 -c "
import time
t0 = time.time()

# Simulate fast path - quality check + schema compliance
from PIL import Image
import io

# Create test image
img = Image.new('RGB', (4000, 3000), 'white')
buf = io.BytesIO()
img.save(buf, format='JPEG', quality=95)
original_size = len(buf.getvalue())

# Schema compliance: resize to 1920x1080
img_resized = img.resize((1920, 1080), Image.LANCZOS)
buf2 = io.BytesIO()
img_resized.save(buf2, format='JPEG', quality=85)
final_size = len(buf2.getvalue())

t1 = time.time()
print(f'FAST_PATH_TIME={t1-t0:.3f}')
print(f'ORIGINAL_SIZE={original_size}')
print(f'FINAL_SIZE={final_size}')
print('FAST_PATH_SUCCESS')
"
'''
        cmd = create_timing_wrapper(inner_cmd)
        
        print("Submitting job...")
        submit_time = time.time()
        job_id = self.harness.create_job(cmd)
        print(f"Job ID: {job_id}")
        
        print("Waiting for completion...")
        status = self.harness.wait_for_job(job_id, timeout=300)
        end_time = time.time()
        
        logs = self.harness.get_job_logs(job_id)
        timing = parse_timing_from_logs(logs)
        
        job_result = JobResult(
            job_id=job_id,
            test_name=test_name,
            status=status["status"],
            submit_time=submit_time,
            start_time=timing.get("start_time"),
            end_time=timing.get("end_time"),
            duration_seconds=status.get("duration"),
            queue_time_seconds=None,  # Would need start_time from Camber
            logs=logs,
            metadata={
                "path": "fast_path",
                "timing": timing
            }
        )
        jobs.append(job_result)
        
        # Print results
        print(f"\nResults:")
        print(f"  Status: {status['status']}")
        print(f"  Total Duration: {status.get('duration')}s")
        print(f"  Wall Clock: {end_time - submit_time:.1f}s")
        
        summary = {
            "total_jobs": 1,
            "successful": 1 if status["status"] == "COMPLETED" else 0,
            "avg_duration": status.get("duration"),
            "wall_clock_time": end_time - submit_time
        }
        
        result = TestResult(
            test_name=test_name,
            started_at=started_at,
            completed_at=datetime.now().isoformat(),
            jobs=jobs,
            summary=summary
        )
        
        self.harness.save_results(result)
        return result

    def test_sequential_fast_path(self, num_jobs: int = 5) -> TestResult:
        """
        Test 2: Sequential jobs - Fast path (warm start measurement).
        
        Runs multiple jobs sequentially to measure cache benefits.
        """
        print("\n" + "="*60)
        print(f"TEST 2: Sequential Fast Path ({num_jobs} jobs)")
        print("="*60)
        
        test_name = "sequential_fast_path"
        started_at = datetime.now().isoformat()
        jobs = []
        
        inner_cmd = '''
export PYTHONPATH=/home/camber/workdir:$PYTHONPATH
python3 -c "
import time
t0 = time.time()
from PIL import Image
import io

img = Image.new('RGB', (4000, 3000), 'white')
img_resized = img.resize((1920, 1080), Image.LANCZOS)
buf = io.BytesIO()
img_resized.save(buf, format='JPEG', quality=85)

t1 = time.time()
print(f'PROCESSING_TIME={t1-t0:.3f}')
print('SUCCESS')
"
'''
        cmd = create_timing_wrapper(inner_cmd)
        
        for i in range(num_jobs):
            print(f"\nJob {i+1}/{num_jobs}...")
            submit_time = time.time()
            job_id = self.harness.create_job(cmd)
            print(f"  Job ID: {job_id}")
            
            status = self.harness.wait_for_job(job_id)
            end_time = time.time()
            logs = self.harness.get_job_logs(job_id)
            timing = parse_timing_from_logs(logs)
            
            job_result = JobResult(
                job_id=job_id,
                test_name=test_name,
                status=status["status"],
                submit_time=submit_time,
                start_time=timing.get("start_time"),
                end_time=timing.get("end_time"),
                duration_seconds=status.get("duration"),
                queue_time_seconds=None,
                logs=logs,
                metadata={"job_number": i+1, "timing": timing}
            )
            jobs.append(job_result)
            
            print(f"  Duration: {status.get('duration')}s")
        
        # Calculate summary
        durations = [j.duration_seconds for j in jobs if j.duration_seconds]
        summary = {
            "total_jobs": num_jobs,
            "successful": sum(1 for j in jobs if j.status == "COMPLETED"),
            "avg_duration": sum(durations) / len(durations) if durations else None,
            "min_duration": min(durations) if durations else None,
            "max_duration": max(durations) if durations else None,
            "first_job": durations[0] if durations else None,
            "subsequent_avg": sum(durations[1:]) / len(durations[1:]) if len(durations) > 1 else None
        }
        
        print(f"\nSummary:")
        print(f"  First job: {summary['first_job']}s")
        print(f"  Subsequent avg: {summary['subsequent_avg']:.1f}s" if summary['subsequent_avg'] else "")
        print(f"  Overall avg: {summary['avg_duration']:.1f}s" if summary['avg_duration'] else "")
        
        result = TestResult(
            test_name=test_name,
            started_at=started_at,
            completed_at=datetime.now().isoformat(),
            jobs=jobs,
            summary=summary
        )
        
        self.harness.save_results(result)
        return result

    def test_sequential_schema_compliance(self, num_jobs: int = 5) -> TestResult:
        """
        Test 3: Sequential jobs - Schema compliance processing.
        
        Tests resize, DPI adjustment, compression.
        """
        print("\n" + "="*60)
        print(f"TEST 3: Sequential Schema Compliance ({num_jobs} jobs)")
        print("="*60)
        
        test_name = "sequential_schema_compliance"
        started_at = datetime.now().isoformat()
        jobs = []
        
        inner_cmd = '''
export PYTHONPATH=/home/camber/workdir:$PYTHONPATH
python3 -c "
import time
t0 = time.time()
from PIL import Image
import io

# Create larger test image with some content
img = Image.new('RGB', (4000, 3000), 'white')
from PIL import ImageDraw
draw = ImageDraw.Draw(img)
for i in range(0, 4000, 100):
    draw.line([(i, 0), (i, 3000)], fill='gray')
for i in range(0, 3000, 100):
    draw.line([(0, i), (4000, i)], fill='gray')
draw.text((100, 100), 'Test Document', fill='black')

t_create = time.time()

# Schema compliance operations
# 1. Resize
img_resized = img.resize((1920, 1080), Image.LANCZOS)
t_resize = time.time()

# 2. DPI adjustment (metadata)
img_resized.info['dpi'] = (300, 300)
t_dpi = time.time()

# 3. Compression
buf = io.BytesIO()
img_resized.save(buf, format='JPEG', quality=85, optimize=True)
final_bytes = buf.getvalue()
t_compress = time.time()

print(f'CREATE_TIME={t_create-t0:.3f}')
print(f'RESIZE_TIME={t_resize-t_create:.3f}')
print(f'DPI_TIME={t_dpi-t_resize:.3f}')
print(f'COMPRESS_TIME={t_compress-t_dpi:.3f}')
print(f'TOTAL_TIME={t_compress-t0:.3f}')
print(f'OUTPUT_SIZE={len(final_bytes)}')
print('SUCCESS')
"
'''
        cmd = create_timing_wrapper(inner_cmd)
        
        for i in range(num_jobs):
            print(f"\nJob {i+1}/{num_jobs}...")
            submit_time = time.time()
            job_id = self.harness.create_job(cmd)
            
            status = self.harness.wait_for_job(job_id)
            logs = self.harness.get_job_logs(job_id)
            timing = parse_timing_from_logs(logs)
            
            job_result = JobResult(
                job_id=job_id,
                test_name=test_name,
                status=status["status"],
                submit_time=submit_time,
                start_time=timing.get("start_time"),
                end_time=timing.get("end_time"),
                duration_seconds=status.get("duration"),
                queue_time_seconds=None,
                logs=logs,
                metadata={"job_number": i+1}
            )
            jobs.append(job_result)
            print(f"  Duration: {status.get('duration')}s")
        
        durations = [j.duration_seconds for j in jobs if j.duration_seconds]
        summary = {
            "total_jobs": num_jobs,
            "successful": sum(1 for j in jobs if j.status == "COMPLETED"),
            "avg_duration": sum(durations) / len(durations) if durations else None,
            "min_duration": min(durations) if durations else None,
            "max_duration": max(durations) if durations else None
        }
        
        result = TestResult(
            test_name=test_name,
            started_at=started_at,
            completed_at=datetime.now().isoformat(),
            jobs=jobs,
            summary=summary
        )
        
        self.harness.save_results(result)
        return result

    def test_concurrent_single_user(self, num_jobs: int = 5) -> TestResult:
        """
        Test 5: Concurrent jobs from single user.
        
        Simulates user uploading multiple documents at once.
        """
        print("\n" + "="*60)
        print(f"TEST 5: Concurrent Jobs - Single User ({num_jobs} jobs)")
        print("="*60)
        
        test_name = "concurrent_single_user"
        started_at = datetime.now().isoformat()
        
        inner_cmd = '''
export PYTHONPATH=/home/camber/workdir:$PYTHONPATH
python3 -c "
import time
t0 = time.time()
from PIL import Image
import io

img = Image.new('RGB', (2000, 1500), 'white')
img_resized = img.resize((1920, 1080), Image.LANCZOS)
buf = io.BytesIO()
img_resized.save(buf, format='JPEG', quality=85)

t1 = time.time()
print(f'PROCESSING_TIME={t1-t0:.3f}')
print('SUCCESS')
"
'''
        cmd = create_timing_wrapper(inner_cmd)
        
        # Submit all jobs in parallel
        print(f"Submitting {num_jobs} jobs simultaneously...")
        submit_time = time.time()
        
        job_ids = []
        for i in range(num_jobs):
            job_id = self.harness.create_job(cmd)
            job_ids.append(job_id)
            print(f"  Job {i+1}: {job_id}")
        
        submit_complete_time = time.time()
        print(f"All jobs submitted in {submit_complete_time - submit_time:.1f}s")
        
        # Wait for all jobs
        print("\nWaiting for completion...")
        jobs = []
        
        for i, job_id in enumerate(job_ids):
            status = self.harness.wait_for_job(job_id)
            logs = self.harness.get_job_logs(job_id)
            timing = parse_timing_from_logs(logs)
            
            job_result = JobResult(
                job_id=job_id,
                test_name=test_name,
                status=status["status"],
                submit_time=submit_time,
                start_time=timing.get("start_time"),
                end_time=timing.get("end_time"),
                duration_seconds=status.get("duration"),
                queue_time_seconds=None,
                logs=logs,
                metadata={"job_number": i+1}
            )
            jobs.append(job_result)
            print(f"  Job {i+1} ({job_id}): {status['status']} - {status.get('duration')}s")
        
        all_complete_time = time.time()
        
        # Calculate summary
        durations = [j.duration_seconds for j in jobs if j.duration_seconds]
        summary = {
            "total_jobs": num_jobs,
            "successful": sum(1 for j in jobs if j.status == "COMPLETED"),
            "avg_duration": sum(durations) / len(durations) if durations else None,
            "min_duration": min(durations) if durations else None,
            "max_duration": max(durations) if durations else None,
            "wall_clock_total": all_complete_time - submit_time,
            "parallelization_efficiency": (sum(durations) / (all_complete_time - submit_time)) if durations else None
        }
        
        print(f"\nSummary:")
        print(f"  Total wall clock: {summary['wall_clock_total']:.1f}s")
        print(f"  Avg job duration: {summary['avg_duration']:.1f}s" if summary['avg_duration'] else "")
        print(f"  Parallelization efficiency: {summary['parallelization_efficiency']:.2f}x" if summary['parallelization_efficiency'] else "")
        
        result = TestResult(
            test_name=test_name,
            started_at=started_at,
            completed_at=datetime.now().isoformat(),
            jobs=jobs,
            summary=summary
        )
        
        self.harness.save_results(result)
        return result

    def test_concurrent_multi_user(self, num_users: int = 3, jobs_per_user: int = 3) -> TestResult:
        """
        Test 6: Concurrent jobs from multiple users.
        
        Simulates production load with multiple users.
        """
        print("\n" + "="*60)
        print(f"TEST 6: Concurrent Jobs - {num_users} Users x {jobs_per_user} Jobs")
        print("="*60)
        
        test_name = "concurrent_multi_user"
        started_at = datetime.now().isoformat()
        total_jobs = num_users * jobs_per_user
        
        inner_cmd = '''
export PYTHONPATH=/home/camber/workdir:$PYTHONPATH
python3 -c "
import time
t0 = time.time()
from PIL import Image
import io

img = Image.new('RGB', (2000, 1500), 'white')
img_resized = img.resize((1920, 1080), Image.LANCZOS)
buf = io.BytesIO()
img_resized.save(buf, format='JPEG', quality=85)

t1 = time.time()
print(f'PROCESSING_TIME={t1-t0:.3f}')
print('SUCCESS')
"
'''
        cmd = create_timing_wrapper(inner_cmd)
        
        # Submit all jobs
        print(f"Submitting {total_jobs} jobs...")
        submit_time = time.time()
        
        job_metadata = []  # (job_id, user_id, job_num)
        for user in range(num_users):
            for job_num in range(jobs_per_user):
                job_id = self.harness.create_job(cmd)
                job_metadata.append((job_id, f"user_{user+1}", job_num+1))
                print(f"  User {user+1}, Job {job_num+1}: {job_id}")
        
        submit_complete = time.time()
        print(f"All jobs submitted in {submit_complete - submit_time:.1f}s")
        
        # Wait for all
        print("\nWaiting for completion...")
        jobs = []
        
        for job_id, user_id, job_num in job_metadata:
            status = self.harness.wait_for_job(job_id)
            logs = self.harness.get_job_logs(job_id)
            timing = parse_timing_from_logs(logs)
            
            job_result = JobResult(
                job_id=job_id,
                test_name=test_name,
                status=status["status"],
                submit_time=submit_time,
                start_time=timing.get("start_time"),
                end_time=timing.get("end_time"),
                duration_seconds=status.get("duration"),
                queue_time_seconds=None,
                logs=logs,
                metadata={"user_id": user_id, "job_number": job_num}
            )
            jobs.append(job_result)
        
        all_complete = time.time()
        
        # Per-user stats
        user_stats = {}
        for user in range(num_users):
            user_id = f"user_{user+1}"
            user_jobs = [j for j in jobs if j.metadata.get("user_id") == user_id]
            user_durations = [j.duration_seconds for j in user_jobs if j.duration_seconds]
            user_stats[user_id] = {
                "avg_duration": sum(user_durations) / len(user_durations) if user_durations else None,
                "jobs_successful": sum(1 for j in user_jobs if j.status == "COMPLETED")
            }
        
        durations = [j.duration_seconds for j in jobs if j.duration_seconds]
        summary = {
            "total_jobs": total_jobs,
            "num_users": num_users,
            "jobs_per_user": jobs_per_user,
            "successful": sum(1 for j in jobs if j.status == "COMPLETED"),
            "avg_duration": sum(durations) / len(durations) if durations else None,
            "wall_clock_total": all_complete - submit_time,
            "user_stats": user_stats
        }
        
        print(f"\nSummary:")
        print(f"  Total wall clock: {summary['wall_clock_total']:.1f}s")
        print(f"  Avg duration: {summary['avg_duration']:.1f}s" if summary['avg_duration'] else "")
        for user_id, stats in user_stats.items():
            print(f"  {user_id}: avg={stats['avg_duration']:.1f}s" if stats['avg_duration'] else f"  {user_id}: no data")
        
        result = TestResult(
            test_name=test_name,
            started_at=started_at,
            completed_at=datetime.now().isoformat(),
            jobs=jobs,
            summary=summary
        )
        
        self.harness.save_results(result)
        return result

    def test_enhancement_path(self, num_jobs: int = 5) -> TestResult:
        """
        Test 3: Enhancement Path using OpenCV.
        
        Tests auto-crop, denoise, sharpen operations.
        """
        print("\n" + "="*60)
        print(f"TEST: Enhancement Path - OpenCV ({num_jobs} jobs)")
        print("="*60)
        
        test_name = "enhancement_path_opencv"
        started_at = datetime.now().isoformat()
        jobs = []
        
        inner_cmd = '''
pip install opencv-python-headless numpy Pillow --quiet
python3 -c "
import time
import cv2
import numpy as np
from PIL import Image
import io

t0 = time.time()

# Create test image with some noise
img = np.zeros((3000, 4000, 3), dtype=np.uint8)
img[:] = (240, 240, 240)
cv2.rectangle(img, (200, 200), (3800, 2800), (0, 0, 0), 3)
cv2.putText(img, 'Test Document', (500, 500), cv2.FONT_HERSHEY_SIMPLEX, 3, (0, 0, 0), 5)
# Add noise
noise = np.random.randint(0, 30, img.shape, dtype=np.uint8)
img = cv2.add(img, noise)

t_create = time.time()

# Auto-crop detection
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
edges = cv2.Canny(gray, 50, 150)
contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
if contours:
    largest = max(contours, key=cv2.contourArea)
    x, y, w, h = cv2.boundingRect(largest)
    # Crop with padding
    pad = 50
    img = img[max(0,y-pad):min(img.shape[0],y+h+pad), max(0,x-pad):min(img.shape[1],x+w+pad)]

t_crop = time.time()

# Denoise
denoised = cv2.fastNlMeansDenoisingColored(img, None, 10, 10, 7, 21)
t_denoise = time.time()

# Sharpen
kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
sharpened = cv2.filter2D(denoised, -1, kernel)
t_sharpen = time.time()

# Resize
resized = cv2.resize(sharpened, (1920, 1080), interpolation=cv2.INTER_LANCZOS4)
t_resize = time.time()

# Encode
_, encoded = cv2.imencode('.jpg', resized, [cv2.IMWRITE_JPEG_QUALITY, 85])
t_encode = time.time()

print(f'CREATE_TIME={t_create-t0:.3f}')
print(f'CROP_TIME={t_crop-t_create:.3f}')
print(f'DENOISE_TIME={t_denoise-t_crop:.3f}')
print(f'SHARPEN_TIME={t_sharpen-t_denoise:.3f}')
print(f'RESIZE_TIME={t_resize-t_sharpen:.3f}')
print(f'ENCODE_TIME={t_encode-t_resize:.3f}')
print(f'TOTAL_TIME={t_encode-t0:.3f}')
print(f'OUTPUT_SIZE={len(encoded)}')
print('ENHANCEMENT_SUCCESS')
"
'''
        cmd = create_timing_wrapper(inner_cmd)
        
        for i in range(num_jobs):
            print(f"\nJob {i+1}/{num_jobs}...")
            submit_time = time.time()
            job_id = self.harness.create_job(cmd)
            
            status = self.harness.wait_for_job(job_id)
            logs = self.harness.get_job_logs(job_id)
            timing = parse_timing_from_logs(logs)
            
            job_result = JobResult(
                job_id=job_id,
                test_name=test_name,
                status=status["status"],
                submit_time=submit_time,
                start_time=timing.get("start_time"),
                end_time=timing.get("end_time"),
                duration_seconds=status.get("duration"),
                queue_time_seconds=None,
                logs=logs,
                metadata={"job_number": i+1}
            )
            jobs.append(job_result)
            print(f"  Duration: {status.get('duration')}s")
        
        durations = [j.duration_seconds for j in jobs if j.duration_seconds]
        summary = {
            "total_jobs": num_jobs,
            "successful": sum(1 for j in jobs if j.status == "COMPLETED"),
            "avg_duration": sum(durations) / len(durations) if durations else None,
            "min_duration": min(durations) if durations else None,
            "max_duration": max(durations) if durations else None,
            "first_job": durations[0] if durations else None,
            "subsequent_avg": sum(durations[1:]) / len(durations[1:]) if len(durations) > 1 else None
        }
        
        result = TestResult(
            test_name=test_name,
            started_at=started_at,
            completed_at=datetime.now().isoformat(),
            jobs=jobs,
            summary=summary
        )
        
        self.harness.save_results(result)
        return result

    def test_background_removal(self, num_jobs: int = 3) -> TestResult:
        """
        Test 4: Background Removal using rembg.
        
        Tests U2Net model initialization overhead.
        """
        print("\n" + "="*60)
        print(f"TEST: Background Removal - rembg ({num_jobs} jobs)")
        print("="*60)
        print("NOTE: First job will download ~170MB U2Net model")
        
        test_name = "background_removal_rembg"
        started_at = datetime.now().isoformat()
        jobs = []
        
        inner_cmd = '''
pip install rembg Pillow --quiet
python3 -c "
import time
from rembg import remove
from PIL import Image, ImageDraw
import io

t0 = time.time()

# Create test image with distinct foreground/background
img = Image.new('RGB', (1000, 800), (200, 200, 200))
draw = ImageDraw.Draw(img)
# Draw a 'document' as foreground
draw.rectangle([100, 50, 900, 750], fill=(255, 255, 255), outline=(0, 0, 0), width=3)
draw.text((150, 100), 'Test Document', fill=(0, 0, 0))
draw.text((150, 200), 'With Background', fill=(0, 0, 0))

t_create = time.time()

# Convert to bytes
buf = io.BytesIO()
img.save(buf, format='PNG')
img_bytes = buf.getvalue()

t_encode = time.time()

# Remove background (triggers model load)
result = remove(img_bytes)
t_remove = time.time()

print(f'CREATE_TIME={t_create-t0:.3f}')
print(f'ENCODE_TIME={t_encode-t_create:.3f}')
print(f'REMOVE_TIME={t_remove-t_encode:.3f}')
print(f'TOTAL_TIME={t_remove-t0:.3f}')
print(f'INPUT_SIZE={len(img_bytes)}')
print(f'OUTPUT_SIZE={len(result)}')
print('REMBG_SUCCESS')
"
'''
        cmd = create_timing_wrapper(inner_cmd)
        
        for i in range(num_jobs):
            print(f"\nJob {i+1}/{num_jobs}...")
            submit_time = time.time()
            job_id = self.harness.create_job(cmd)
            
            # Longer timeout for model download
            status = self.harness.wait_for_job(job_id, timeout=600)
            logs = self.harness.get_job_logs(job_id)
            timing = parse_timing_from_logs(logs)
            
            job_result = JobResult(
                job_id=job_id,
                test_name=test_name,
                status=status["status"],
                submit_time=submit_time,
                start_time=timing.get("start_time"),
                end_time=timing.get("end_time"),
                duration_seconds=status.get("duration"),
                queue_time_seconds=None,
                logs=logs,
                metadata={"job_number": i+1}
            )
            jobs.append(job_result)
            print(f"  Duration: {status.get('duration')}s")
        
        durations = [j.duration_seconds for j in jobs if j.duration_seconds]
        summary = {
            "total_jobs": num_jobs,
            "successful": sum(1 for j in jobs if j.status == "COMPLETED"),
            "avg_duration": sum(durations) / len(durations) if durations else None,
            "first_job_duration": durations[0] if durations else None,
            "subsequent_avg": sum(durations[1:]) / len(durations[1:]) if len(durations) > 1 else None
        }
        
        print(f"\nSummary:")
        print(f"  First job (model download): {summary['first_job_duration']}s")
        print(f"  Subsequent avg: {summary['subsequent_avg']:.1f}s" if summary['subsequent_avg'] else "")
        
        result = TestResult(
            test_name=test_name,
            started_at=started_at,
            completed_at=datetime.now().isoformat(),
            jobs=jobs,
            summary=summary
        )
        
        self.harness.save_results(result)
        return result

    def test_pdf_processing(self, num_jobs: int = 5) -> TestResult:
        """
        Test 5: PDF Processing using PyMuPDF.
        """
        print("\n" + "="*60)
        print(f"TEST: PDF Processing - PyMuPDF ({num_jobs} jobs)")
        print("="*60)
        
        test_name = "pdf_processing_pymupdf"
        started_at = datetime.now().isoformat()
        jobs = []
        
        inner_cmd = '''
pip install PyMuPDF Pillow --quiet
python3 -c "
import time
import fitz
from PIL import Image
import io

t0 = time.time()

# Create a multi-page PDF
doc = fitz.open()
for i in range(5):
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), f'Page {i+1}', fontsize=24)
    page.insert_text((72, 150), 'Lorem ipsum dolor sit amet, consectetur adipiscing elit.', fontsize=12)
    page.draw_rect(fitz.Rect(50, 50, 562, 742), width=2)

t_create = time.time()

# Save to bytes
pdf_bytes = doc.tobytes()
t_save = time.time()

# Process each page
doc2 = fitz.open(stream=pdf_bytes, filetype='pdf')
images = []
for page_num in range(len(doc2)):
    page = doc2[page_num]
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
    img_bytes = pix.tobytes('png')
    images.append(img_bytes)

t_extract = time.time()

# Reassemble (simulate processing)
output_doc = fitz.open()
for img_bytes in images:
    img = fitz.open(stream=img_bytes, filetype='png')
    rect = img[0].rect
    pdf_bytes_single = img.convert_to_pdf()
    img_pdf = fitz.open('pdf', pdf_bytes_single)
    output_doc.insert_pdf(img_pdf)

t_reassemble = time.time()

final_bytes = output_doc.tobytes()
t_final = time.time()

doc.close()
doc2.close()
output_doc.close()

print(f'CREATE_TIME={t_create-t0:.3f}')
print(f'SAVE_TIME={t_save-t_create:.3f}')
print(f'EXTRACT_TIME={t_extract-t_save:.3f}')
print(f'REASSEMBLE_TIME={t_reassemble-t_extract:.3f}')
print(f'FINAL_TIME={t_final-t_reassemble:.3f}')
print(f'TOTAL_TIME={t_final-t0:.3f}')
print(f'PAGES={len(images)}')
print(f'OUTPUT_SIZE={len(final_bytes)}')
print('PYMUPDF_SUCCESS')
"
'''
        cmd = create_timing_wrapper(inner_cmd)
        
        for i in range(num_jobs):
            print(f"\nJob {i+1}/{num_jobs}...")
            submit_time = time.time()
            job_id = self.harness.create_job(cmd)
            
            status = self.harness.wait_for_job(job_id)
            logs = self.harness.get_job_logs(job_id)
            timing = parse_timing_from_logs(logs)
            
            job_result = JobResult(
                job_id=job_id,
                test_name=test_name,
                status=status["status"],
                submit_time=submit_time,
                start_time=timing.get("start_time"),
                end_time=timing.get("end_time"),
                duration_seconds=status.get("duration"),
                queue_time_seconds=None,
                logs=logs,
                metadata={"job_number": i+1}
            )
            jobs.append(job_result)
            print(f"  Duration: {status.get('duration')}s")
        
        durations = [j.duration_seconds for j in jobs if j.duration_seconds]
        summary = {
            "total_jobs": num_jobs,
            "successful": sum(1 for j in jobs if j.status == "COMPLETED"),
            "avg_duration": sum(durations) / len(durations) if durations else None,
            "min_duration": min(durations) if durations else None,
            "max_duration": max(durations) if durations else None
        }
        
        result = TestResult(
            test_name=test_name,
            started_at=started_at,
            completed_at=datetime.now().isoformat(),
            jobs=jobs,
            summary=summary
        )
        
        self.harness.save_results(result)
        return result

    def test_ocr_paddleocr(self, num_jobs: int = 3) -> TestResult:
        """
        Test 6: OCR using PaddleOCR.
        
        Confirms 44s init overhead.
        """
        print("\n" + "="*60)
        print(f"TEST: OCR - PaddleOCR ({num_jobs} jobs)")
        print("="*60)
        print("NOTE: ~44s init overhead expected per job")
        
        test_name = "ocr_paddleocr"
        started_at = datetime.now().isoformat()
        jobs = []
        
        inner_cmd = '''
pip install paddlepaddle paddleocr Pillow numpy --quiet
python3 -c "
import time
import numpy as np
from PIL import Image, ImageDraw

t0 = time.time()

from paddleocr import PaddleOCR
t_import = time.time()
print(f'IMPORT_TIME={t_import-t0:.3f}')

ocr = PaddleOCR(use_angle_cls=True, lang='en', show_log=False)
t_init = time.time()
print(f'INIT_TIME={t_init-t_import:.3f}')

# Create test image
img = Image.new('RGB', (800, 200), 'white')
draw = ImageDraw.Draw(img)
draw.text((50, 80), 'Hello World 12345 Invoice Total: 1234.56', fill='black')
img_array = np.array(img)
t_create = time.time()

# OCR
result = ocr.ocr(img_array, cls=True)
t_ocr = time.time()
print(f'OCR_TIME={t_ocr-t_create:.3f}')

# Extract text
text = ''
if result and result[0]:
    for line in result[0]:
        text += line[1][0] + ' '

print(f'TOTAL_TIME={t_ocr-t0:.3f}')
print(f'EXTRACTED_TEXT={text.strip()}')
print('PADDLEOCR_SUCCESS')
"
'''
        cmd = create_timing_wrapper(inner_cmd)
        
        for i in range(num_jobs):
            print(f"\nJob {i+1}/{num_jobs}...")
            submit_time = time.time()
            job_id = self.harness.create_job(cmd)
            
            status = self.harness.wait_for_job(job_id, timeout=300)
            logs = self.harness.get_job_logs(job_id)
            timing = parse_timing_from_logs(logs)
            
            job_result = JobResult(
                job_id=job_id,
                test_name=test_name,
                status=status["status"],
                submit_time=submit_time,
                start_time=timing.get("start_time"),
                end_time=timing.get("end_time"),
                duration_seconds=status.get("duration"),
                queue_time_seconds=None,
                logs=logs,
                metadata={"job_number": i+1}
            )
            jobs.append(job_result)
            print(f"  Duration: {status.get('duration')}s")
        
        durations = [j.duration_seconds for j in jobs if j.duration_seconds]
        summary = {
            "total_jobs": num_jobs,
            "successful": sum(1 for j in jobs if j.status == "COMPLETED"),
            "avg_duration": sum(durations) / len(durations) if durations else None
        }
        
        result = TestResult(
            test_name=test_name,
            started_at=started_at,
            completed_at=datetime.now().isoformat(),
            jobs=jobs,
            summary=summary
        )
        
        self.harness.save_results(result)
        return result


def main():
    parser = argparse.ArgumentParser(description="Camber Platform Evaluation Test Runner")
    parser.add_argument("--test", choices=[
        "fast_path", "enhancement", "background_removal", "pdf_processing",
        "ocr_paddle", "concurrent_single", "concurrent_multi", 
        "components", "all"
    ], help="Test to run")
    parser.add_argument("--api-key", default=os.environ.get("CAMBER_API_KEY"))
    parser.add_argument("--stash-path", default="stash://abhinavprakash15151692/eval-test/worker")
    parser.add_argument("--num-jobs", type=int, default=5, help="Number of jobs for sequential/concurrent tests")
    
    args = parser.parse_args()
    
    if not args.api_key:
        print("Error: CAMBER_API_KEY not set")
        print("Set it with: export CAMBER_API_KEY=your_key")
        sys.exit(1)
    
    evaluator = PlatformEvaluator(args.api_key, args.stash_path)
    
    tests = {
        "fast_path": lambda: evaluator.test_sequential_fast_path(args.num_jobs),
        "enhancement": lambda: evaluator.test_enhancement_path(args.num_jobs),
        "background_removal": lambda: evaluator.test_background_removal(3),  # Fewer due to model download
        "pdf_processing": lambda: evaluator.test_pdf_processing(args.num_jobs),
        "ocr_paddle": lambda: evaluator.test_ocr_paddleocr(3),  # Fewer due to 44s overhead
        "concurrent_single": lambda: evaluator.test_concurrent_single_user(args.num_jobs),
        "concurrent_multi": lambda: evaluator.test_concurrent_multi_user(3, 3),
    }
    
    if args.test == "components":
        # Run component baseline test
        from tests.platform_eval.test_components import ComponentEvaluator
        comp_eval = ComponentEvaluator(args.api_key, args.stash_path)
        comp_eval.test_all_components()
    elif args.test == "all":
        print("Running all platform evaluation tests...")
        print("This will take several hours.\n")
        
        # Run component baseline first
        try:
            from tests.platform_eval.test_components import ComponentEvaluator
            comp_eval = ComponentEvaluator(args.api_key, args.stash_path)
            comp_eval.test_all_components()
        except Exception as e:
            print(f"Component test failed: {e}")
        
        # Then run path tests
        for name, test_func in tests.items():
            try:
                print(f"\n{'='*60}")
                print(f"Starting test: {name}")
                print('='*60)
                test_func()
            except Exception as e:
                print(f"Test {name} failed: {e}")
    elif args.test:
        tests[args.test]()
    else:
        parser.print_help()
        print("\nAvailable tests:")
        print("  fast_path         - Pillow + img2pdf (schema compliance)")
        print("  enhancement       - OpenCV (auto-crop, denoise)")
        print("  background_removal - rembg (ML model, ~170MB)")
        print("  pdf_processing    - PyMuPDF")
        print("  ocr_paddle        - PaddleOCR (44s init)")
        print("  concurrent_single - 5 parallel jobs (single user)")
        print("  concurrent_multi  - 9 parallel jobs (3 users)")
        print("  components        - All component init baselines")
        print("  all               - Run everything")


if __name__ == "__main__":
    main()
