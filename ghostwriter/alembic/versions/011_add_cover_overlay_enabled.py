"""Add cover_overlay_enabled setting to client_config.

Revision ID: 011
Revises: 010
Create Date: 2026-02-14
"""

from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(sa.text(f"PRAGMA table_info({table})"))
    return any(row[1] == column for row in result)


def upgrade() -> None:
    if context.get_context().dialect.name != "sqlite":
        return

    if not _column_exists("client_config", "cover_overlay_enabled"):
        op.execute(
            "ALTER TABLE client_config ADD COLUMN cover_overlay_enabled BOOLEAN NOT NULL DEFAULT 1"
        )


def downgrade() -> None:
    pass
