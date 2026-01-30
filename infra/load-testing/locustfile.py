"""
Locust load test for Rythmiq One document processing pipeline.

Test profile:
- 50 concurrent users (configurable)
- Each user uploads 5 documents in burst pattern
- 70% fast-path documents (high quality)
- 30% standard-path documents (medium quality)

Usage:
    # Basic run (web UI)
    locust -f locustfile.py --host http://localhost:8000
    
    # Headless run for CI/CD
    locust -f locustfile.py --host http://localhost:8000 \
        --headless -u 50 -r 10 -t 300s \
        --csv=results/load_test
    
    # With custom test data path
    TEST_DATA_PATH=/path/to/fixtures locust -f locustfile.py

Metrics collected:
- Response times (P50, P95, P99)
- Throughput (requests/sec)
- Error rate
- Custom: Job completion time, CPU seconds per job
"""

import json
import os
import random
import time
import uuid
from pathlib import Path
from typing import List, Optional

from locust import HttpUser, task, between, events
from locust.runners import MasterRunner, WorkerRunner


# =============================================================================
# Configuration
# =============================================================================

# Test data paths
TEST_DATA_PATH = Path(os.environ.get("TEST_DATA_PATH", "test-data/load-test"))
FAST_PATH_DIR = TEST_DATA_PATH / "fast-path"
STANDARD_PATH_DIR = TEST_DATA_PATH / "standard-path"

# Document mix (should sum to 100)
FAST_PATH_WEIGHT = 70
STANDARD_PATH_WEIGHT = 30

# API configuration
API_KEY = os.environ.get("RYTHMIQ_API_KEY", "test-api-key")
PORTAL_SCHEMA_NAME = os.environ.get("PORTAL_SCHEMA_NAME", "default")

# Timing configuration
JOB_POLL_INTERVAL = 0.5  # seconds between status checks
JOB_TIMEOUT = 120  # maximum wait for job completion
UPLOAD_TIMEOUT = 30  # timeout for signed URL operations


# =============================================================================
# Test Data Management
# =============================================================================

class TestDocumentPool:
    """
    Manages pool of test documents for load testing.
    
    Documents are pre-loaded at startup to avoid disk I/O during tests.
    """
    
    def __init__(self):
        self.fast_path_docs: List[tuple[str, bytes]] = []
        self.standard_path_docs: List[tuple[str, bytes]] = []
        self._loaded = False
    
    def load(self) -> None:
        """Load test documents from disk."""
        if self._loaded:
            return
        
        # Load fast-path documents
        if FAST_PATH_DIR.exists():
            for f in FAST_PATH_DIR.glob("*.jpg"):
                self.fast_path_docs.append((f.name, f.read_bytes()))
            for f in FAST_PATH_DIR.glob("*.png"):
                self.fast_path_docs.append((f.name, f.read_bytes()))
        
        # Load standard-path documents
        if STANDARD_PATH_DIR.exists():
            for f in STANDARD_PATH_DIR.glob("*.jpg"):
                self.standard_path_docs.append((f.name, f.read_bytes()))
            for f in STANDARD_PATH_DIR.glob("*.png"):
                self.standard_path_docs.append((f.name, f.read_bytes()))
        
        # Generate synthetic documents if none found
        if not self.fast_path_docs:
            self.fast_path_docs = self._generate_synthetic_docs("fast", 10)
        if not self.standard_path_docs:
            self.standard_path_docs = self._generate_synthetic_docs("standard", 5)
        
        self._loaded = True
        print(f"Loaded {len(self.fast_path_docs)} fast-path and "
              f"{len(self.standard_path_docs)} standard-path documents")
    
    def _generate_synthetic_docs(
        self, 
        path_type: str, 
        count: int
    ) -> List[tuple[str, bytes]]:
        """Generate synthetic test documents (simple JPEG data)."""
        docs = []
        
        # Create minimal valid JPEG (1x1 white pixel)
        # This is a valid JPEG file, just very small
        minimal_jpeg = bytes([
            0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00,
            0x01, 0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB,
            0x00, 0x43, 0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07,
            0x07, 0x07, 0x09, 0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B,
            0x0B, 0x0C, 0x19, 0x12, 0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E,
            0x1D, 0x1A, 0x1C, 0x1C, 0x20, 0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C,
            0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29, 0x2C, 0x30, 0x31, 0x34, 0x34,
            0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32, 0x3C, 0x2E, 0x33, 0x34,
            0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01, 0x00, 0x01, 0x01,
            0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00, 0x01, 0x05,
            0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,
            0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
            0x09, 0x0A, 0x0B, 0xFF, 0xC4, 0x00, 0xB5, 0x10, 0x00, 0x02, 0x01,
            0x03, 0x03, 0x02, 0x04, 0x03, 0x05, 0x05, 0x04, 0x04, 0x00, 0x00,
            0x01, 0x7D, 0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12, 0x21,
            0x31, 0x41, 0x06, 0x13, 0x51, 0x61, 0x07, 0x22, 0x71, 0x14, 0x32,
            0x81, 0x91, 0xA1, 0x08, 0x23, 0x42, 0xB1, 0xC1, 0x15, 0x52, 0xD1,
            0xF0, 0x24, 0x33, 0x62, 0x72, 0x82, 0x09, 0x0A, 0x16, 0x17, 0x18,
            0x19, 0x1A, 0x25, 0x26, 0x27, 0x28, 0x29, 0x2A, 0x34, 0x35, 0x36,
            0x37, 0x38, 0x39, 0x3A, 0x43, 0x44, 0x45, 0x46, 0x47, 0x48, 0x49,
            0x4A, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59, 0x5A, 0x63, 0x64,
            0x65, 0x66, 0x67, 0x68, 0x69, 0x6A, 0x73, 0x74, 0x75, 0x76, 0x77,
            0x78, 0x79, 0x7A, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89, 0x8A,
            0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9A, 0xA2, 0xA3,
            0xA4, 0xA5, 0xA6, 0xA7, 0xA8, 0xA9, 0xAA, 0xB2, 0xB3, 0xB4, 0xB5,
            0xB6, 0xB7, 0xB8, 0xB9, 0xBA, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7,
            0xC8, 0xC9, 0xCA, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9,
            0xDA, 0xE1, 0xE2, 0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA,
            0xF1, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6, 0xF7, 0xF8, 0xF9, 0xFA, 0xFF,
            0xDA, 0x00, 0x08, 0x01, 0x01, 0x00, 0x00, 0x3F, 0x00, 0xFB, 0xD5,
            0xDB, 0x20, 0xA8, 0xBA, 0xAE, 0xEB, 0xFF, 0xD9
        ])
        
        # Pad to realistic sizes
        for i in range(count):
            # Fast path: 500KB-1MB, Standard: 1-3MB
            if path_type == "fast":
                target_size = random.randint(500_000, 1_000_000)
            else:
                target_size = random.randint(1_000_000, 3_000_000)
            
            # Pad with random bytes (won't be valid image, but size is realistic)
            padding = os.urandom(target_size - len(minimal_jpeg))
            doc_data = minimal_jpeg[:-2] + padding + minimal_jpeg[-2:]  # Keep JPEG EOF marker
            
            docs.append((f"synthetic_{path_type}_{i:03d}.jpg", doc_data))
        
        return docs
    
    def get_random_document(self) -> tuple[str, bytes, str]:
        """
        Get a random document based on path weight distribution.
        
        Returns:
            Tuple of (filename, data, path_type)
        """
        self.load()
        
        if random.randint(1, 100) <= FAST_PATH_WEIGHT:
            filename, data = random.choice(self.fast_path_docs)
            return filename, data, "fast"
        else:
            filename, data = random.choice(self.standard_path_docs)
            return filename, data, "standard"


# Global document pool
document_pool = TestDocumentPool()


# =============================================================================
# Custom Metrics
# =============================================================================

# Track job completion metrics
job_completion_times: List[float] = []
job_cpu_seconds: List[float] = []
jobs_by_path: dict = {"fast": 0, "standard": 0}
jobs_failed: int = 0


@events.request.add_listener
def on_request(request_type, name, response_time, response_length, exception, **kwargs):
    """Log additional metrics on each request."""
    pass  # Built-in metrics are sufficient


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Print summary statistics when test ends."""
    print("\n" + "=" * 60)
    print("LOAD TEST SUMMARY")
    print("=" * 60)
    
    if job_completion_times:
        completion_sorted = sorted(job_completion_times)
        n = len(completion_sorted)
        print(f"\nJob Completion Times (end-to-end):")
        print(f"  Count: {n}")
        print(f"  P50: {completion_sorted[int(n*0.5)]:.2f}s")
        print(f"  P95: {completion_sorted[int(n*0.95)]:.2f}s" if n > 20 else "  P95: N/A")
        print(f"  P99: {completion_sorted[int(n*0.99)]:.2f}s" if n > 100 else "  P99: N/A")
    
    if job_cpu_seconds:
        cpu_sorted = sorted(job_cpu_seconds)
        n = len(cpu_sorted)
        avg_cpu = sum(cpu_sorted) / n
        total_cpu_hours = sum(cpu_sorted) / 3600
        print(f"\nCPU Metrics:")
        print(f"  Average CPU/job: {avg_cpu:.3f}s")
        print(f"  Total CPU consumed: {total_cpu_hours:.4f} hours")
        print(f"  Projected monthly (1000/day): {avg_cpu * 1000 * 30 / 3600:.2f} CPU-hours")
    
    print(f"\nPath Distribution:")
    print(f"  Fast path: {jobs_by_path['fast']}")
    print(f"  Standard path: {jobs_by_path['standard']}")
    print(f"  Failed: {jobs_failed}")
    
    print("=" * 60)


# =============================================================================
# Load Test User
# =============================================================================

class RythmiqUser(HttpUser):
    """
    Simulates a user uploading documents to Rythmiq One.
    
    Each user:
    1. Creates a job
    2. Uploads document to signed URL
    3. Polls for completion
    4. Records metrics
    """
    
    # Wait between tasks (simulates user think time)
    wait_time = between(0.5, 2.0)
    
    # Number of documents per user session
    docs_per_session = 5
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.docs_uploaded = 0
        self.auth_token: Optional[str] = None
    
    def on_start(self):
        """Called when user starts. Get auth token."""
        # In production, this would authenticate
        # For now, use test token
        self.auth_token = API_KEY
    
    @task(1)
    def upload_document(self):
        """Upload a document through the full pipeline."""
        global jobs_by_path, jobs_failed, job_completion_times, job_cpu_seconds
        
        # Rate limit: stop after docs_per_session
        if self.docs_uploaded >= self.docs_per_session:
            return
        
        self.docs_uploaded += 1
        
        # Get random document
        filename, data, path_type = document_pool.get_random_document()
        jobs_by_path[path_type] += 1
        
        job_start_time = time.time()
        
        try:
            # Step 1: Create job
            create_response = self.client.post(
                "/jobs",
                json={
                    "filename": filename,
                    "mime_type": "image/jpeg",
                    "file_size_bytes": len(data),
                    "portal_schema_name": PORTAL_SCHEMA_NAME,
                },
                headers={"Authorization": f"Bearer {self.auth_token}"},
                name="1. Create Job",
            )
            
            if create_response.status_code != 200:
                jobs_failed += 1
                return
            
            job_data = create_response.json()
            job_id = job_data["job_id"]
            upload_url = job_data["upload_url"]
            
            # Step 2: Upload to signed URL
            upload_response = self.client.put(
                upload_url,
                data=data,
                headers={"Content-Type": "image/jpeg"},
                name="2. Upload Document",
                catch_response=True,
            )
            
            if upload_response.status_code not in (200, 204):
                upload_response.failure(f"Upload failed: {upload_response.status_code}")
                jobs_failed += 1
                return
            
            upload_response.success()
            
            # Step 3: Poll for completion
            start_poll = time.time()
            final_status = None
            cpu_seconds = None
            
            while time.time() - start_poll < JOB_TIMEOUT:
                status_response = self.client.get(
                    f"/jobs/{job_id}/status",
                    headers={"Authorization": f"Bearer {self.auth_token}"},
                    name="3. Poll Status",
                )
                
                if status_response.status_code == 200:
                    status_data = status_response.json()
                    final_status = status_data.get("status")
                    
                    if final_status in ("succeeded", "failed"):
                        # Extract CPU metrics if available
                        metrics = status_data.get("metrics", {})
                        cpu_seconds = metrics.get("total_cpu_seconds")
                        break
                
                time.sleep(JOB_POLL_INTERVAL)
            
            # Record completion time
            job_end_time = time.time()
            job_completion_times.append(job_end_time - job_start_time)
            
            if cpu_seconds is not None:
                job_cpu_seconds.append(cpu_seconds)
            
            if final_status == "failed":
                jobs_failed += 1
            
        except Exception as e:
            jobs_failed += 1
            print(f"Error in upload_document: {e}")


# =============================================================================
# Alternative: Burst Load User
# =============================================================================

class BurstUser(HttpUser):
    """
    User that uploads in rapid bursts without waiting.
    
    Use this for stress testing to find breaking points.
    """
    
    wait_time = between(0.1, 0.3)  # Minimal wait
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.docs_uploaded = 0
    
    def on_start(self):
        self.auth_token = API_KEY
    
    @task(1)
    def rapid_upload(self):
        """Upload documents as fast as possible."""
        global jobs_by_path, jobs_failed
        
        if self.docs_uploaded >= 10:  # 10 docs per burst user
            return
        
        self.docs_uploaded += 1
        filename, data, path_type = document_pool.get_random_document()
        jobs_by_path[path_type] += 1
        
        try:
            # Create job only (don't wait for completion)
            response = self.client.post(
                "/jobs",
                json={
                    "filename": filename,
                    "mime_type": "image/jpeg",
                    "file_size_bytes": len(data),
                    "portal_schema_name": PORTAL_SCHEMA_NAME,
                },
                headers={"Authorization": f"Bearer {self.auth_token}"},
                name="Burst: Create Job",
            )
            
            if response.status_code != 200:
                jobs_failed += 1
                
        except Exception:
            jobs_failed += 1


# =============================================================================
# Entry point for direct execution
# =============================================================================

if __name__ == "__main__":
    print("Run with: locust -f locustfile.py --host http://localhost:8000")
