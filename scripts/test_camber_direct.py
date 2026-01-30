#!/usr/bin/env python3
"""
Direct Camber job submission test.
Bypasses the API to test Camber integration directly.
"""

import asyncio
import os
import sys
from uuid import uuid4

# Ensure we're using the right settings
sys.path.insert(0, "/Users/abhinav/Rythmiq One")

async def test_camber_direct():
    from app.api.config import get_settings
    from app.api.services.camber import CamberService
    
    settings = get_settings()
    print(f"Camber API URL: {settings.camber_api_url}")
    print(f"Camber App Name: {settings.camber_app_name}")
    print(f"Webhook Base URL: {settings.webhook_base_url}")
    
    camber = CamberService(settings)
    
    job_id = uuid4()
    print(f"\nSubmitting test job: {job_id}")
    
    payload = {
        "job_id": str(job_id),
        "artifact_url": "https://rythmiq-one-artifacts.sgp1.digitaloceanspaces.com/blobs/ca860aa8-d31a-4a15-a6ee-9de5c7ae2671",
        "schema": {"type": "receipt"},
        "storage": {
            "endpoint": "https://sgp1.digitaloceanspaces.com",
            "region": "sgp1",
            "bucket": "rythmiq-one-artifacts",
        }
    }
    
    try:
        camber_job_id = await camber.submit_job(job_id, payload)
        print(f"\n✅ SUCCESS! Camber job ID: {camber_job_id}")
        print(f"\nNow monitor:")
        print(f"  - ngrok inspector: http://127.0.0.1:4040")
        print(f"  - API logs: tail -f /tmp/api.log")
        print(f"  - Camber dashboard for job status")
        return camber_job_id
    except Exception as e:
        print(f"\n❌ ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    asyncio.run(test_camber_direct())
