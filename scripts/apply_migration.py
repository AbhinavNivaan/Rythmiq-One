"""
Apply a SQL migration file to Supabase via the management API.

Usage:
    python scripts/apply_migration.py db/migrations/20260305_add_master_path.sql
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

import httpx

def apply_migration(sql_file: Path) -> None:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

    if not url or not key:
        print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
        sys.exit(1)

    sql = sql_file.read_text()

    # Use Supabase's Management API endpoint for raw SQL execution
    # For hosted Supabase projects, we can use the pg-meta endpoint or the
    # standard PostgreSQL REST that supports raw queries via rpc.
    # The recommended approach for DDL is to use the SQL editor endpoint.

    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    # Try the rpc endpoint for raw SQL (available on some hosted projects)
    # Supabase exposes raw SQL via the /rest/v1/rpc/... endpoints only for
    # user-defined functions. For DDL, we use the pg-meta admin API.
    #
    # As a fallback, check for the local supabase CLI:
    print(f"Applying migration: {sql_file.name}")
    print(f"SQL preview:\n{'='*60}")
    print(sql[:500])
    print('='*60)

    # Try supabase CLI's db push if available
    import subprocess
    result = subprocess.run(
        ["supabase", "db", "push", "--file", str(sql_file)],
        cwd=str(project_root),
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        print("Migration applied via Supabase CLI.")
        print(result.stdout)
        return

    # Fall back to direct pg connection if DATABASE_URL is set
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        try:
            import psycopg2
            conn = psycopg2.connect(database_url)
            conn.autocommit = True
            cur = conn.cursor()
            cur.execute(sql)
            cur.close()
            conn.close()
            print("Migration applied via direct PostgreSQL connection.")
            return
        except ImportError:
            print("psycopg2 not installed, cannot use direct connection.")
        except Exception as e:
            print(f"Direct connection failed: {e}")

    print("""
========================================================
MANUAL ACTION REQUIRED
========================================================
The migration cannot be applied automatically.
Please run the following SQL in your Supabase SQL editor:

  https://supabase.com/dashboard/project/_/sql/new

SQL to execute:
""")
    print(sql)
    print("========================================================")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sql_path = project_root / "db/migrations/20260305_add_master_path.sql"
    else:
        sql_path = Path(sys.argv[1])

    if not sql_path.exists():
        print(f"ERROR: File not found: {sql_path}")
        sys.exit(1)

    apply_migration(sql_path)
