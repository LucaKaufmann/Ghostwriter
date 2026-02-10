"""Consolidate all legacy manual migration scripts into Alembic.

Absorbs the following manual scripts (ghostwriter/scripts/migrate_*.py):
- migrate_add_article_content.py    -> digest_articles columns
- migrate_add_content_type.py       -> digest_articles.content_type
- migrate_add_feed_deleted_at.py    -> feeds.deleted_at
- migrate_nullable_feed_id.py       -> nullable feed_id on digest_articles/seen_articles
- migrate_add_digest_indexes.py     -> ix_digests_status index
- migrate_add_integration_enabled.py -> wallabag_config.enabled, client_config.newsletters_enabled
- migrate_add_newsletter_mode.py    -> client_config.newsletter_mode
- migrate_add_client_config.py      -> client_config table (handled by create_all)

Every operation is idempotent: checks before acting so this migration
is safe to run on databases at any state (fresh, partially migrated, or
fully migrated via the old manual scripts).

Revision ID: 006
Revises: 005
Create Date: 2026-02-10

"""

from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _get_existing_columns(table: str) -> set[str]:
    """Return the set of column names for a table."""
    conn = op.get_bind()
    result = conn.execute(sa.text(f"PRAGMA table_info({table})"))
    return {row[1] for row in result}


def _column_is_nullable(table: str, column: str) -> bool:
    """Check if a column is nullable (notnull == 0)."""
    conn = op.get_bind()
    result = conn.execute(sa.text(f"PRAGMA table_info({table})"))
    for row in result:
        if row[1] == column:
            return row[3] == 0  # notnull == 0 means nullable
    return True  # column doesn't exist


def _index_exists(index_name: str) -> bool:
    """Check if an index exists."""
    conn = op.get_bind()
    result = conn.execute(
        sa.text("SELECT name FROM sqlite_master WHERE type='index' AND name=:name"),
        {"name": index_name},
    )
    return result.fetchone() is not None


def _table_exists(table: str) -> bool:
    """Check if a table exists."""
    conn = op.get_bind()
    result = conn.execute(
        sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name=:name"),
        {"name": table},
    )
    return result.fetchone() is not None


def _add_column_if_missing(table: str, column: str, col_def: str) -> None:
    """Add a column to a table if it doesn't already exist."""
    existing = _get_existing_columns(table)
    if column not in existing:
        op.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")


def upgrade() -> None:
    """Consolidate all legacy migrations into the Alembic chain."""
    if context.get_context().dialect.name != "sqlite":
        return

    # --- digest_articles columns (from migrate_add_article_content.py) ---
    _add_column_if_missing("digest_articles", "content", "TEXT NOT NULL DEFAULT ''")
    _add_column_if_missing("digest_articles", "author", "TEXT")
    _add_column_if_missing("digest_articles", "feed_title", "TEXT NOT NULL DEFAULT ''")
    _add_column_if_missing("digest_articles", "sort_order", "INTEGER NOT NULL DEFAULT 0")

    # --- digest_articles.content_type (from migrate_add_content_type.py) ---
    _add_column_if_missing(
        "digest_articles", "content_type", "VARCHAR NOT NULL DEFAULT 'article'"
    )

    # --- feeds.deleted_at (from migrate_add_feed_deleted_at.py) ---
    _add_column_if_missing("feeds", "deleted_at", "TIMESTAMP DEFAULT NULL")

    # --- nullable feed_id (from migrate_nullable_feed_id.py) ---
    # Use Alembic's batch_alter_table for proper SQLite table rebuild.
    for table in ("digest_articles", "seen_articles"):
        if not _table_exists(table):
            continue
        if _column_is_nullable(table, "feed_id"):
            continue

        with op.batch_alter_table(table) as batch_op:
            batch_op.alter_column(
                "feed_id",
                existing_type=sa.String(32),
                nullable=True,
            )

    # --- ix_digests_status index (from migrate_add_digest_indexes.py) ---
    if not _index_exists("ix_digests_status"):
        op.execute("CREATE INDEX ix_digests_status ON digests (status)")

    # --- wallabag_config.enabled (from migrate_add_integration_enabled.py) ---
    if _table_exists("wallabag_config"):
        _add_column_if_missing("wallabag_config", "enabled", "BOOLEAN DEFAULT 1")

    # --- client_config columns (from migrate_add_integration_enabled.py
    #     and migrate_add_newsletter_mode.py) ---
    _add_column_if_missing(
        "client_config", "newsletters_enabled", "BOOLEAN DEFAULT 1"
    )
    _add_column_if_missing(
        "client_config", "newsletter_mode", "TEXT DEFAULT 'summarize'"
    )


def downgrade() -> None:
    """SQLite does not support DROP COLUMN without table rebuild.

    Keep columns to avoid destructive migrations in production.
    This matches the established pattern from migration 005.
    """
    pass
