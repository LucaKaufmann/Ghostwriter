"""Migration: Add newsletter_mode column to client_config.

Adds:
- client_config.newsletter_mode (TEXT DEFAULT 'summarize')
"""

import os
import sqlite3
import sys


def migrate(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    migrations = [
        ("client_config", "newsletter_mode", "TEXT DEFAULT 'summarize'"),
    ]

    for table, column, col_type in migrations:
        try:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
            print(f"Added {table}.{column}")
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e).lower():
                print(f"Column {table}.{column} already exists, skipping")
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
