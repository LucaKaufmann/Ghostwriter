"""Replace podcast_episodes.digest_id FK with digest_ids JSON, add trigger column.

Revision ID: 018
Revises: 017
Create Date: 2026-02-20
"""

from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa

revision: str = "018"
down_revision: Union[str, None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(name: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = :name LIMIT 1"
        ),
        {"name": name},
    ).first()
    return result is not None


def _existing_columns(table_name: str) -> set[str]:
    conn = op.get_bind()
    rows = conn.execute(sa.text(f"PRAGMA table_info({table_name})")).fetchall()
    return {row[1] for row in rows}


def upgrade() -> None:
    if context.get_context().dialect.name != "sqlite":
        return

    if not _table_exists("podcast_episodes"):
        return

    existing = _existing_columns("podcast_episodes")

    # Add new columns first
    if "digest_ids" not in existing:
        op.execute(
            "ALTER TABLE podcast_episodes "
            "ADD COLUMN digest_ids TEXT NOT NULL DEFAULT '[]'"
        )

    if "trigger" not in existing:
        op.execute(
            "ALTER TABLE podcast_episodes "
            "ADD COLUMN trigger TEXT NOT NULL DEFAULT 'manual'"
        )

    # Migrate data: copy digest_id into digest_ids as a JSON array
    if "digest_id" in existing:
        op.execute(
            "UPDATE podcast_episodes "
            "SET digest_ids = json_array(digest_id) "
            "WHERE digest_id IS NOT NULL AND digest_ids = '[]'"
        )

    # Drop old digest_id column via table rebuild
    if "digest_id" in existing:
        with op.batch_alter_table("podcast_episodes") as batch_op:
            batch_op.drop_column("digest_id")


def downgrade() -> None:
    pass
