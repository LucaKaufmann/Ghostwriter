#!/usr/bin/env python3
"""Migration script to create the client_config table for settings sync.

This migration creates:
- client_config table: Stores shared settings that sync across devices

The table is created with default values if it doesn't exist.
Note: The app will auto-create this table on startup via SQLModel.metadata.create_all(),
but this script can be used to create it manually without restarting.

Usage:
    python scripts/migrate_add_client_config.py
"""

import os
import sqlite3
import sys
from uuid import uuid4
from datetime import datetime, timezone

# Add the parent directory to the path so we can import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import get_settings


def migrate():
    """Create client_config table if it doesn't exist."""
    settings = get_settings()
    db_path = os.path.join(settings.data_dir, "ghostwriter.db")

    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        print("Run the application first to create the database.")
        return False

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if table already exists
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='client_config'"
    )
    if cursor.fetchone() is not None:
        print("Table 'client_config' already exists, skipping creation")
        conn.close()
        return True

    # Create the table
    create_sql = """
    CREATE TABLE client_config (
        id VARCHAR NOT NULL PRIMARY KEY,
        min_word_count INTEGER NOT NULL DEFAULT 0,
        morning_hour INTEGER NOT NULL DEFAULT 7,
        morning_minute INTEGER NOT NULL DEFAULT 0,
        noon_hour INTEGER NOT NULL DEFAULT 12,
        noon_minute INTEGER NOT NULL DEFAULT 0,
        evening_hour INTEGER NOT NULL DEFAULT 18,
        evening_minute INTEGER NOT NULL DEFAULT 0,
        timezone VARCHAR NOT NULL DEFAULT 'UTC',
        created_at TIMESTAMP NOT NULL,
        updated_at TIMESTAMP NOT NULL
    )
    """

    try:
        cursor.execute(create_sql)
        print("Created table 'client_config'")

        # Insert default row
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute(
            """
            INSERT INTO client_config (
                id, min_word_count, morning_hour, morning_minute,
                noon_hour, noon_minute, evening_hour, evening_minute,
                timezone, created_at, updated_at
            ) VALUES (?, 0, 7, 0, 12, 0, 18, 0, 'UTC', ?, ?)
            """,
            (str(uuid4()), now, now),
        )
        print("Inserted default configuration row")

    except sqlite3.OperationalError as e:
        if "already exists" in str(e).lower():
            print("Table 'client_config' already exists")
        else:
            raise

    conn.commit()
    conn.close()

    print("\nMigration complete: client_config table created")
    return True


if __name__ == "__main__":
    print("Running client_config migration...")
    success = migrate()
    sys.exit(0 if success else 1)
