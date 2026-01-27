#!/usr/bin/env python3
"""Migration script to add deleted_at column to feeds table for tombstone support.

This migration adds:
- deleted_at: Timestamp indicating when a feed was deleted (tombstone)

Semantics:
- is_active=False, deleted_at=None → Feed is paused
- is_active=False, deleted_at=<timestamp> → Feed is deleted (tombstone)

Run this script once after updating the codebase to enable bi-directional sync.

Usage:
    python scripts/migrate_add_feed_deleted_at.py
"""

import os
import sqlite3
import sys

# Add the parent directory to the path so we can import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import get_settings


def migrate():
    """Add deleted_at column to feeds table."""
    settings = get_settings()
    db_path = os.path.join(settings.data_dir, "ghostwriter.db")

    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        print("Run the application first to create the database.")
        return False

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check which columns already exist
    cursor.execute("PRAGMA table_info(feeds)")
    existing_columns = {row[1] for row in cursor.fetchall()}
    print(f"Existing columns: {existing_columns}")

    migrations = [
        ("deleted_at", "ALTER TABLE feeds ADD COLUMN deleted_at TIMESTAMP DEFAULT NULL"),
    ]

    applied = 0
    for column_name, sql in migrations:
        if column_name in existing_columns:
            print(f"Column '{column_name}' already exists, skipping")
            continue

        try:
            cursor.execute(sql)
            print(f"Added column '{column_name}'")
            applied += 1
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e).lower():
                print(f"Column '{column_name}' already exists")
            else:
                raise

    conn.commit()
    conn.close()

    if applied > 0:
        print(f"\nMigration complete: {applied} columns added")
    else:
        print("\nNo migration needed, all columns already exist")

    return True


if __name__ == "__main__":
    print("Running feed deleted_at migration...")
    success = migrate()
    sys.exit(0 if success else 1)
