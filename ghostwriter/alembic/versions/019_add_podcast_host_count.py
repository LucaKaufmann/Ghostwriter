"""Add host_count column to podcast_preferences.

Revision ID: 019
Revises: 018
Create Date: 2026-02-21
"""

from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa

revision: str = "019"
down_revision: Union[str, None] = "018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if context.get_context().dialect.name != "sqlite":
        return

    conn = op.get_bind()
    result = conn.execute(sa.text("PRAGMA table_info(podcast_preferences)"))
    existing = {row[1] for row in result}

    if "host_count" not in existing:
        op.execute(
            "ALTER TABLE podcast_preferences "
            "ADD COLUMN host_count INTEGER NOT NULL DEFAULT 2"
        )


def downgrade() -> None:
    pass
