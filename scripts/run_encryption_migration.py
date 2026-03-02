#!/usr/bin/env python3
"""
Run encryption migration against Supabase.

Uses the Supabase Management API to execute raw SQL, or falls back
to PostgREST rpc if a migration function exists.
"""

import os
import sys
import httpx

# Load env
from dotenv import load_dotenv
load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
    sys.exit(1)

# Extract project ref from URL
# https://qpixafvazayfjamgywbb.supabase.co -> qpixafvazayfjamgywbb
project_ref = SUPABASE_URL.replace("https://", "").split(".")[0]

MIGRATION_SQLS = [
    "ALTER TABLE public.users ADD COLUMN IF NOT EXISTS storage_encryption_key TEXT;",
    "ALTER TABLE public.documents ADD COLUMN IF NOT EXISTS encrypted BOOLEAN DEFAULT FALSE;",
    "ALTER TABLE public.documents ADD COLUMN IF NOT EXISTS encryption_nonce TEXT;",
    "CREATE INDEX IF NOT EXISTS idx_documents_encrypted ON public.documents(encrypted);",
]

def run_via_postgrest_rpc():
    """Try to run SQL via PostgREST RPC (requires a helper function in Supabase)."""
    # Supabase doesn't expose raw SQL via PostgREST by default.
    # We need to use the SQL Editor API or psql.
    print("PostgREST doesn't support raw SQL. Trying alternative...")
    return False

def run_via_supabase_management_api():
    """Run SQL via Supabase Management API."""
    # The management API requires a personal access token, not service role key
    # This won't work with service role key alone
    print("Management API requires personal access token.")
    return False

def run_via_supabase_client():
    """Run SQL by using supabase-py to check/create columns via postgrest."""
    from supabase import create_client
    
    client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    
    # Test if columns already exist by trying to select them
    print("\nChecking current schema state...")
    
    # Check users table
    try:
        result = client.table("users").select("id, storage_encryption_key").limit(1).execute()
        print("  ✓ users.storage_encryption_key column exists")
        users_ready = True
    except Exception as e:
        if "storage_encryption_key" in str(e):
            print("  ✗ users.storage_encryption_key column MISSING")
            users_ready = False
        else:
            print(f"  ? users table check: {e}")
            users_ready = False
    
    # Check documents table
    try:
        result = client.table("documents").select("id, encrypted, encryption_nonce").limit(1).execute()
        print("  ✓ documents.encrypted column exists")
        print("  ✓ documents.encryption_nonce column exists")
        docs_ready = True
    except Exception as e:
        err = str(e)
        if "encrypted" in err or "encryption_nonce" in err:
            print("  ✗ documents encryption columns MISSING")
            docs_ready = False
        else:
            print(f"  ? documents table check: {e}")
            docs_ready = False
    
    if users_ready and docs_ready:
        print("\n✓ All encryption columns already exist! Migration not needed.")
        return True
    else:
        print("\n✗ Some columns are missing. Please run the following SQL in Supabase SQL Editor:")
        print("  Dashboard → SQL Editor → New query\n")
        for sql in MIGRATION_SQLS:
            print(f"  {sql}")
        print()
        return False


if __name__ == "__main__":
    print(f"Supabase project: {project_ref}")
    print(f"URL: {SUPABASE_URL}")
    print()
    
    success = run_via_supabase_client()
    
    if not success:
        print("\n" + "="*60)
        print("MANUAL STEP REQUIRED")
        print("="*60)
        print(f"\n1. Open: {SUPABASE_URL.replace('.co', '.co')}")
        print("   Or go to: https://supabase.com/dashboard")
        print("2. Navigate to SQL Editor")
        print("3. Paste and run the SQL from: db/migrations/004_add_encryption.sql")
        print()
