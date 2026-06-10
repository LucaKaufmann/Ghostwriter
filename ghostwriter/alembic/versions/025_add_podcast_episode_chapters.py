"""Add chapters column to podcast_episodes.

Revision ID: 025
Revises: 024
Create Date: 2026-06-10
"""

from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa

revision: str = "025"
down_revision: Union[str, None] = "024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if context.get_context().dialect.name != "sqlite":
        return

    conn = op.get_bind()
    result = conn.execute(sa.text("PRAGMA table_info(podcast_episodes)"))
    existing = {row[1] for row in result}

    if "chapters" not in existing:
        op.execute("ALTER TABLE podcast_episodes ADD COLUMN chapters JSON")


def downgrade() -> None:
    pass
