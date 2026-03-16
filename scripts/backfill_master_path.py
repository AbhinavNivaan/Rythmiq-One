"""
Backfill master_path for completed jobs that have it NULL.

The worker always uploads the processed file to a deterministic path:
    master/{user_id}/{job_id}/{job_id}.enc

But the API code that persists this path to the jobs.master_path column was
added later. This script populates master_path for all existing completed jobs.

Usage:
    python scripts/backfill_master_path.py [--dry-run]
"""

import os
import sys
from pathlib import Path

# Load .env
project_root = Path(__file__).parent.parent
env_file = project_root / ".env"
if env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(env_file)

from supabase import create_client


def backfill(dry_run: bool = False) -> None:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

    if not url or not key:
        print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
        sys.exit(1)

    db = create_client(url, key)

    # Fetch all completed jobs where master_path is NULL
    result = (
        db.table("jobs")
        .select("id, user_id")
        .eq("status", "completed")
        .is_("master_path", "null")
        .execute()
    )

    jobs = result.data or []
    print(f"Found {len(jobs)} completed jobs with master_path = NULL")

    if not jobs:
        print("Nothing to backfill.")
        return

    updated = 0
    for job in jobs:
        job_id = job["id"]
        user_id = job["user_id"]
        master_path = f"master/{user_id}/{job_id}/{job_id}.enc"

        if dry_run:
            print(f"  [DRY RUN] {job_id} -> {master_path}")
        else:
            try:
                db.table("jobs").update({"master_path": master_path}).eq("id", job_id).execute()
                print(f"  Updated {job_id} -> {master_path}")
                updated += 1
            except Exception as e:
                print(f"  FAILED {job_id}: {e}")

    if dry_run:
        print(f"\nDry run complete. {len(jobs)} jobs would be updated.")
    else:
        print(f"\nBackfill complete. Updated {updated}/{len(jobs)} jobs.")


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    backfill(dry_run=dry)
