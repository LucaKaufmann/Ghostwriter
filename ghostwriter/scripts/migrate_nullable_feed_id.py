#!/usr/bin/env python3
"""Migration script to make feed_id nullable on digest_articles and seen_articles.

Wallabag articles don't belong to a feed, so feed_id must be optional.
SQLite doesn't support ALTER COLUMN, so we use the rename-recreate-copy pattern.

Usage:
    python scripts/migrate_nullable_feed_id.py
"""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import get_settings


def migrate():
    """Make feed_id nullable on digest_articles and seen_articles."""
    settings = get_settings()
    db_path = os.path.join(settings.data_dir, "ghostwriter.db")

    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        print("Run the application first to create the database.")
        return False

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = OFF")
    cursor = conn.cursor()

    # Check if migration is needed by inspecting column info
    def is_feed_id_nullable(table: str) -> bool:
        cursor.execute(f"PRAGMA table_info({table})")
        for row in cursor.fetchall():
            # row: (cid, name, type, notnull, default, pk)
            if row[1] == "feed_id":
                return row[3] == 0  # notnull == 0 means nullable
        return True  # column doesn't exist, nothing to do

    tables_to_migrate = []
    for table in ("digest_articles", "seen_articles"):
        if not is_feed_id_nullable(table):
            tables_to_migrate.append(table)

    if not tables_to_migrate:
        print("No migration needed, feed_id is already nullable.")
        conn.close()
        return True

    for table in tables_to_migrate:
        print(f"Migrating {table}...")

        # Drop leftover temp table from any previous failed attempt
        cursor.execute(f"DROP TABLE IF EXISTS {table}_new")

        # Get current CREATE TABLE statement
        cursor.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
        )
        create_sql = cursor.fetchone()[0]

        # Replace NOT NULL constraint on feed_id
        # The column is defined as: feed_id CHAR(32) NOT NULL
        new_create_sql = create_sql.replace(
            f"CREATE TABLE {table}", f"CREATE TABLE {table}_new"
        )
        # Remove NOT NULL from feed_id column definition
        # SQLModel generates: "feed_id" CHAR(32) NOT NULL,
        new_create_sql = new_create_sql.replace(
            '"feed_id" CHAR(32) NOT NULL', '"feed_id" CHAR(32)'
        )

        cursor.execute(new_create_sql)

        # Copy data
        cursor.execute(f"INSERT INTO {table}_new SELECT * FROM {table}")

        # Swap tables
        cursor.execute(f"DROP TABLE {table}")
        cursor.execute(f"ALTER TABLE {table}_new RENAME TO {table}")

        # Recreate indexes
        if table == "seen_articles":
            cursor.execute(
                f"CREATE INDEX IF NOT EXISTS ix_seen_articles_feed_guid ON {table} (feed_id, guid)"
            )
            cursor.execute(
                f"CREATE INDEX IF NOT EXISTS ix_seen_articles_feed_id ON {table} (feed_id)"
            )
        elif table == "digest_articles":
            cursor.execute(
                f"CREATE INDEX IF NOT EXISTS ix_digest_articles_feed_id ON {table} (feed_id)"
            )
            cursor.execute(
                f"CREATE INDEX IF NOT EXISTS ix_digest_articles_digest_id ON {table} (digest_id)"
            )

        print(f"  {table}: feed_id is now nullable")

    conn.execute("PRAGMA foreign_keys = ON")
    conn.commit()
    conn.close()

    print(f"\nMigration complete: {len(tables_to_migrate)} tables updated")
    return True


if __name__ == "__main__":
    print("Running nullable feed_id migration...")
    success = migrate()
    sys.exit(0 if success else 1)
