"""Add media_feeds and media_items tables, and media config fields.

Creates decoupled storage for podcast and YouTube feeds/transcripts,
separate from the regular feed/digest pipeline.

Revision ID: 007
Revises: 006
Create Date: 2026-02-11

"""

from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table: str) -> bool:
    """Check if a table exists."""
    conn = op.get_bind()
    result = conn.execute(
        sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name=:name"),
        {"name": table},
    )
    return result.fetchone() is not None


def _get_existing_columns(table: str) -> set[str]:
    """Return the set of column names for a table."""
    conn = op.get_bind()
    result = conn.execute(sa.text(f"PRAGMA table_info({table})"))
    return {row[1] for row in result}


def _index_exists(index_name: str) -> bool:
    """Check if an index exists."""
    conn = op.get_bind()
    result = conn.execute(
        sa.text("SELECT name FROM sqlite_master WHERE type='index' AND name=:name"),
        {"name": index_name},
    )
    return result.fetchone() is not None


def _add_column_if_missing(table: str, column: str, col_def: str) -> None:
    """Add a column to a table if it doesn't already exist."""
    existing = _get_existing_columns(table)
    if column not in existing:
        op.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")


def upgrade() -> None:
    if context.get_context().dialect.name != "sqlite":
        return

    # --- media_feeds table ---
    if not _table_exists("media_feeds"):
        op.execute("""
            CREATE TABLE media_feeds (
                id VARCHAR(32) NOT NULL PRIMARY KEY,
                feed_type VARCHAR NOT NULL,
                url VARCHAR NOT NULL,
                resolved_feed_url VARCHAR,
                title VARCHAR NOT NULL,
                is_active BOOLEAN NOT NULL DEFAULT 1,
                mode VARCHAR NOT NULL DEFAULT 'raw',
                max_items INTEGER NOT NULL DEFAULT 5,
                deleted_at TIMESTAMP,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        if not _index_exists("ix_media_feeds_url"):
            op.execute("CREATE UNIQUE INDEX ix_media_feeds_url ON media_feeds (url)")

    # --- media_items table ---
    if not _table_exists("media_items"):
        op.execute("""
            CREATE TABLE media_items (
                id VARCHAR(32) NOT NULL PRIMARY KEY,
                media_feed_id VARCHAR(32) NOT NULL REFERENCES media_feeds(id),
                guid VARCHAR NOT NULL,
                url VARCHAR NOT NULL,
                content_url VARCHAR,
                title VARCHAR NOT NULL,
                author VARCHAR,
                content TEXT NOT NULL DEFAULT '',
                content_type VARCHAR NOT NULL DEFAULT 'podcast',
                mode VARCHAR NOT NULL DEFAULT 'raw',
                word_count INTEGER NOT NULL DEFAULT 0,
                is_summary BOOLEAN NOT NULL DEFAULT 0,
                ai_failed BOOLEAN NOT NULL DEFAULT 0,
                processing_ms INTEGER NOT NULL DEFAULT 0,
                status VARCHAR NOT NULL DEFAULT 'pending',
                error_message TEXT,
                consumed_at TIMESTAMP,
                consumed_digest_id VARCHAR(32),
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            )
        """)
        if not _index_exists("ix_media_items_feed_id"):
            op.execute("CREATE INDEX ix_media_items_feed_id ON media_items (media_feed_id)")
        if not _index_exists("ix_media_items_guid"):
            op.execute("CREATE INDEX ix_media_items_guid ON media_items (guid)")
        if not _index_exists("ix_media_items_status"):
            op.execute("CREATE INDEX ix_media_items_status ON media_items (status)")

    # --- client_config additions ---
    _add_column_if_missing(
        "client_config",
        "media_processing_interval_hours",
        "INTEGER NOT NULL DEFAULT 4",
    )
    _add_column_if_missing(
        "client_config",
        "include_podcasts_in_digest",
        "BOOLEAN NOT NULL DEFAULT 1",
    )
    _add_column_if_missing(
        "client_config",
        "include_youtube_in_digest",
        "BOOLEAN NOT NULL DEFAULT 1",
    )


def downgrade() -> None:
    """SQLite does not support DROP COLUMN without table rebuild.

    Keep columns to avoid destructive migrations in production.
    """
    pass
