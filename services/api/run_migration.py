#!/usr/bin/env python3
"""
Quick script to run migration 003 directly against the database.
Run this locally with your production DATABASE_URL.

Usage:
  1. Export your Supabase DATABASE_URL:
     export DATABASE_URL="postgresql://postgres:[PASSWORD]@db.[PROJECT].supabase.co:5432/postgres"

  2. Run this script:
     python run_migration.py
"""

import os
import sys
from sqlalchemy import create_engine, text

def run_migration():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL environment variable not set")
        print("\nSet it with:")
        print('  export DATABASE_URL="postgresql://postgres:[PASSWORD]@db.[PROJECT].supabase.co:5432/postgres"')
        sys.exit(1)

    print(f"Connecting to database...")
    # Set statement timeout to 5 minutes
    engine = create_engine(
        database_url,
        connect_args={"options": "-c statement_timeout=300000"}
    )

    statements = [
        "ALTER TABLE pages ADD COLUMN IF NOT EXISTS page_image_path TEXT",
        "ALTER TABLE pages ADD COLUMN IF NOT EXISTS page_image_ready BOOLEAN DEFAULT FALSE",
        "ALTER TABLE pages ADD COLUMN IF NOT EXISTS full_page_text TEXT",
        "ALTER TABLE pages ADD COLUMN IF NOT EXISTS ocr_data JSONB",
        "ALTER TABLE pages ADD COLUMN IF NOT EXISTS processed_ocr BOOLEAN DEFAULT FALSE",
    ]

    for stmt in statements:
        # Use a fresh connection for each statement to avoid transaction issues
        with engine.connect() as conn:
            try:
                print(f"Running: {stmt[:60]}...")
                conn.execute(text(stmt))
                conn.commit()
                print("  ✓ Success")
            except Exception as e:
                print(f"  ✗ Error: {e}")

    print("\nMigration complete!")

if __name__ == "__main__":
    run_migration()
