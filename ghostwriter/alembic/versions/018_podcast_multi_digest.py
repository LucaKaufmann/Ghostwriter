"""Replace podcast_episodes.digest_id FK with digest_ids JSON, add trigger column.

Revision ID: 018
Revises: 017
Create Date: 2026-02-20
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import context, op

revision: str = "018"
down_revision: str | None = "017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


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

    # Drop old digest_id column via table rebuild. SQLite batch alter tries to
    # recreate existing constraints and indexes on the rebuilt table, which
    # fails if they still reference the removed column.
    if "digest_id" in existing:
        naming_convention = {
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        }
        with op.batch_alter_table(
            "podcast_episodes",
            naming_convention=naming_convention,
        ) as batch_op:
            batch_op.drop_index("ix_podcast_episodes_digest_id")
            batch_op.drop_constraint(
                "uq_podcast_episodes_digest_id",
                type_="unique",
            )
            batch_op.drop_constraint(
                "fk_podcast_episodes_digest_id_digests",
                type_="foreignkey",
            )
            batch_op.drop_column("digest_id")


def downgrade() -> None:
    pass
