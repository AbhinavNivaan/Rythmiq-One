"""
Seed portal schemas into the database.

Reads schemas from /schemas/portal_schemas.json and upserts them
into the Supabase portal_schemas table.

Usage:
    python -m scripts.seed_schemas
"""

import json
import os
import sys
from pathlib import Path
from uuid import uuid4

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from supabase import create_client


def load_schemas():
    """Load schemas from JSON file."""
    schemas_file = project_root / "schemas" / "portal_schemas.json"
    
    if not schemas_file.exists():
        print(f"Error: {schemas_file} not found")
        sys.exit(1)
    
    with open(schemas_file) as f:
        data = json.load(f)
    
    return data.get("schemas", [])


def seed_schemas():
    """Seed schemas into database."""
    # Get Supabase credentials from environment
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    
    if not supabase_url or not supabase_key:
        print("Error: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY required")
        print("Set these in your environment or .env file")
        sys.exit(1)
    
    # Connect to Supabase
    client = create_client(supabase_url, supabase_key)
    
    # Load schemas
    schemas = load_schemas()
    print(f"Found {len(schemas)} schemas to seed")
    
    # Upsert each schema
    for schema in schemas:
        schema_id = schema.get("id")
        name = schema.get("name")
        portal = schema.get("portal")
        document_type = schema.get("document_type")
        is_active = schema.get("is_active", True)
        requirements = schema.get("requirements", {})
        constraints = schema.get("constraints", {})
        
        # Build schema definition
        schema_definition = {
            "requirements": requirements,
            "constraints": constraints,
        }
        
        # Check if schema exists
        existing = (
            client.table("portal_schemas")
            .select("id")
            .eq("name", name)
            .limit(1)
            .execute()
        )
        
        if existing.data and len(existing.data) > 0:
            # Update existing
            db_id = existing.data[0]["id"]
            result = (
                client.table("portal_schemas")
                .update({
                    "version": 1,
                    "is_active": is_active,
                    "schema_definition": schema_definition,
                })
                .eq("id", db_id)
                .execute()
            )
            print(f"  Updated: {name}")
        else:
            # Insert new
            result = (
                client.table("portal_schemas")
                .insert({
                    "name": name,
                    "version": 1,
                    "is_active": is_active,
                    "schema_definition": schema_definition,
                })
                .execute()
            )
            print(f"  Created: {name}")
    
    print(f"\nSeeded {len(schemas)} portal schemas")


if __name__ == "__main__":
    # Load .env if available
    env_file = project_root / ".env"
    if env_file.exists():
        from dotenv import load_dotenv
        load_dotenv(env_file)
    
    seed_schemas()
