"""Add podcast_schedules table for flexible recurring podcast scheduling.

Revision ID: 020
Revises: 019
Create Date: 2026-02-28
"""

from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa

revision: str = "020"
down_revision: Union[str, None] = "019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if context.get_context().dialect.name != "sqlite":
        return

    conn = op.get_bind()

    # Check if table already exists
    result = conn.execute(
        sa.text(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='podcast_schedules'"
        )
    )
    if result.fetchone() is not None:
        return

    op.execute(
        """
        CREATE TABLE podcast_schedules (
            id CHAR(32) NOT NULL PRIMARY KEY,
            user_id CHAR(32) REFERENCES users(id),
            name VARCHAR(100) NOT NULL DEFAULT '',
            days JSON NOT NULL DEFAULT '[]',
            time VARCHAR(5) NOT NULL DEFAULT '08:00',
            timezone VARCHAR(64) NOT NULL DEFAULT 'UTC',
            enabled BOOLEAN NOT NULL DEFAULT 1,
            last_run_at TIMESTAMP,
            last_episode_id CHAR(32),
            created_at TIMESTAMP NOT NULL DEFAULT (CURRENT_TIMESTAMP),
            updated_at TIMESTAMP NOT NULL DEFAULT (CURRENT_TIMESTAMP)
        )
        """
    )

    op.execute(
        "CREATE INDEX ix_podcast_schedules_user_id ON podcast_schedules (user_id)"
    )


def downgrade() -> None:
    pass
