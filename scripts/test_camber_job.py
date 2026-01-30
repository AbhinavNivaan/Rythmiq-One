#!/usr/bin/env python3
"""
Test script to submit a job to the API and trigger Camber execution.
"""

import json
import time
import jwt
import httpx
import os
from datetime import datetime, timedelta
from uuid import uuid4

# Load from .env
from dotenv import load_dotenv
load_dotenv()

# Configuration
API_BASE = "http://localhost:8000"
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")

# Generate a test JWT token
def generate_test_token(user_id: str = None) -> str:
    if user_id is None:
        user_id = str(uuid4())
    
    payload = {
        "sub": user_id,
        "email": "test@example.com",
        "aud": "authenticated",
        "exp": datetime.utcnow() + timedelta(hours=1),
        "iat": datetime.utcnow(),
    }
    
    token = jwt.encode(payload, SUPABASE_JWT_SECRET, algorithm="HS256")
    return token, user_id


def test_health():
    """Test API health endpoint"""
    response = httpx.get(f"{API_BASE}/health")
    print(f"Health check: {response.status_code} - {response.json()}")
    return response.status_code == 200


def create_job(token: str, schema_name: str = "receipt"):
    """Create a new job"""
    headers = {"Authorization": f"Bearer {token}"}
    
    payload = {
        "portal_schema_name": schema_name,
        "filename": "test_document.jpg",
        "mime_type": "image/jpeg",
        "file_size_bytes": 1024000,  # 1MB estimate
    }
    
    response = httpx.post(
        f"{API_BASE}/jobs",
        json=payload,
        headers=headers,
        timeout=30.0,
    )
    
    print(f"Create job response: {response.status_code}")
    print(json.dumps(response.json(), indent=2))
    
    return response


def get_job_status(token: str, job_id: str):
    """Get job status"""
    headers = {"Authorization": f"Bearer {token}"}
    
    response = httpx.get(
        f"{API_BASE}/jobs/{job_id}",
        headers=headers,
        timeout=30.0,
    )
    
    print(f"Job status: {response.status_code}")
    print(json.dumps(response.json(), indent=2))
    
    return response


def main():
    print("=" * 60)
    print("Camber Integration Test")
    print("=" * 60)
    
    # 1. Health check
    print("\n1. Health check...")
    if not test_health():
        print("API not healthy, exiting")
        return
    
    # 2. Generate token
    print("\n2. Generating test JWT token...")
    token, user_id = generate_test_token()
    print(f"User ID: {user_id}")
    print(f"Token: {token[:50]}...")
    
    # 3. Create job
    print("\n3. Creating job...")
    response = create_job(token)
    
    if response.status_code != 200:
        print(f"Failed to create job: {response.text}")
        return
    
    job_data = response.json()
    job_id = job_data.get("job_id")
    upload_url = job_data.get("upload_url")
    
    print(f"\nJob ID: {job_id}")
    print(f"Upload URL: {upload_url[:80]}...")
    
    # 4. Poll for job status
    print("\n4. Polling job status...")
    for i in range(30):  # Poll for up to 5 minutes
        time.sleep(10)
        response = get_job_status(token, job_id)
        
        if response.status_code == 200:
            status = response.json().get("status")
            print(f"[{i*10}s] Status: {status}")
            
            if status in ("completed", "failed"):
                print("\nJob finished!")
                break
    
    print("\n" + "=" * 60)
    print("Test complete")
    print("=" * 60)


if __name__ == "__main__":
    main()
