#!/usr/bin/env python3
"""
Backfill Storage Encryption Keys for existing users.

Generates and stores a random SEK for every user that doesn't have one.
Safe to run multiple times (idempotent).

Usage:
    python scripts/backfill_user_sek.py
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from supabase import create_client
from app.api.crypto.encryption import generate_sek, sek_to_base64


def main():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

    if not url or not key:
        print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env")
        sys.exit(1)

    client = create_client(url, key)

    # Fetch all users without a SEK
    print("Fetching users without encryption keys...")

    try:
        result = (
            client.table("users")
            .select("id, email, storage_encryption_key")
            .is_("storage_encryption_key", "null")
            .execute()
        )
    except Exception as e:
        # If the column doesn't exist yet, try fetching all users
        print(f"Note: {e}")
        print("Trying to fetch all users (column may not exist yet)...")
        try:
            result = client.table("users").select("id, email").execute()
        except Exception as e2:
            print(f"ERROR: Cannot access users table: {e2}")
            print("Make sure the migration has been run first:")
            print("  db/migrations/004_add_encryption.sql")
            sys.exit(1)

    users = result.data or []

    if not users:
        print("No users found without encryption keys. Nothing to do.")
        return

    # Filter to only users without SEK (in case we fetched all)
    users_needing_sek = [
        u for u in users
        if not u.get("storage_encryption_key")
    ]

    if not users_needing_sek:
        print("All users already have encryption keys. Nothing to do.")
        return

    print(f"Found {len(users_needing_sek)} user(s) without encryption keys.")
    print()

    # Generate and store SEK for each user
    success_count = 0
    error_count = 0

    for user in users_needing_sek:
        user_id = user["id"]
        email = user.get("email", "unknown")

        try:
            sek = generate_sek()
            sek_b64 = sek_to_base64(sek)

            client.table("users").update({
                "storage_encryption_key": sek_b64,
            }).eq("id", user_id).execute()

            print(f"  ✓ {email} ({user_id})")
            success_count += 1

        except Exception as e:
            print(f"  ✗ {email} ({user_id}): {e}")
            error_count += 1

    print()
    print(f"Done: {success_count} succeeded, {error_count} failed")

    if error_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
