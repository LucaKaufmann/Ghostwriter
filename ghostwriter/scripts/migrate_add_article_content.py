#!/usr/bin/env python3
"""Migration script to add article content columns to digest_articles table.

This migration adds the following columns:
- content: Full article content (HTML or Markdown)
- author: Article author
- feed_title: Title of the source feed
- sort_order: Order within the digest

Run this script once after updating the codebase to enable article content syncing.

Usage:
    python scripts/migrate_add_article_content.py
"""

import os
import sqlite3
import sys

# Add the parent directory to the path so we can import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import get_settings


def migrate():
    """Add article content columns to digest_articles table."""
    settings = get_settings()
    db_path = os.path.join(settings.data_dir, "ghostwriter.db")

    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        print("Run the application first to create the database.")
        return False

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check which columns already exist
    cursor.execute("PRAGMA table_info(digest_articles)")
    existing_columns = {row[1] for row in cursor.fetchall()}
    print(f"Existing columns: {existing_columns}")

    migrations = [
        ("content", "ALTER TABLE digest_articles ADD COLUMN content TEXT NOT NULL DEFAULT ''"),
        ("author", "ALTER TABLE digest_articles ADD COLUMN author TEXT"),
        ("feed_title", "ALTER TABLE digest_articles ADD COLUMN feed_title TEXT NOT NULL DEFAULT ''"),
        ("sort_order", "ALTER TABLE digest_articles ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0"),
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
    print("Running article content migration...")
    success = migrate()
    sys.exit(0 if success else 1)
