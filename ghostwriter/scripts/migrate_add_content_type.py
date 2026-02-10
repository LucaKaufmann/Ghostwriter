"""Migration: Add content_type column to digest_articles table.

Adds:
- digest_articles.content_type (VARCHAR DEFAULT 'article')
"""

import os
import sqlite3
import sys


def migrate(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute(
            "ALTER TABLE digest_articles ADD COLUMN content_type VARCHAR NOT NULL DEFAULT 'article'"
        )
        print("Added digest_articles.content_type")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            print("Column digest_articles.content_type already exists, skipping")
        else:
            raise

    conn.commit()
    conn.close()
    print("Migration complete.")


if __name__ == "__main__":
    data_dir = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))
    db_path = os.path.join(data_dir, "ghostwriter.db")

    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        sys.exit(1)

    migrate(db_path)
