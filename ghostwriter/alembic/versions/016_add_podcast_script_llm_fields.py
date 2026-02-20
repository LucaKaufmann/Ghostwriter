"""Add podcast script LLM model and timeout fields.

Revision ID: 016
Revises: 015
Create Date: 2026-02-19
"""

from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa

revision: str = "016"
down_revision: Union[str, None] = "015"
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

    if not _table_exists("podcast_preferences"):
        return

    existing = _existing_columns("podcast_preferences")

    if "script_model" not in existing:
        op.execute(
            "ALTER TABLE podcast_preferences "
            "ADD COLUMN script_model TEXT"
        )
    if "script_timeout_seconds" not in existing:
        op.execute(
            "ALTER TABLE podcast_preferences "
            "ADD COLUMN script_timeout_seconds INTEGER NOT NULL DEFAULT 60"
        )


def downgrade() -> None:
    pass
