"""Add media_processing_runs table.

Revision ID: 012
Revises: 011
Create Date: 2026-02-16
"""

from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(
        sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name=:name"),
        {"name": table},
    )
    return result.fetchone() is not None


def upgrade() -> None:
    if context.get_context().dialect.name != "sqlite":
        return

    if _table_exists("media_processing_runs"):
        return

    op.execute("""
        CREATE TABLE media_processing_runs (
            id CHAR(32) NOT NULL PRIMARY KEY,
            started_at DATETIME NOT NULL,
            completed_at DATETIME,
            duration_ms INTEGER NOT NULL DEFAULT 0,
            status VARCHAR NOT NULL DEFAULT 'running',
            items_discovered INTEGER NOT NULL DEFAULT 0,
            items_processed INTEGER NOT NULL DEFAULT 0,
            items_failed INTEGER NOT NULL DEFAULT 0,
            error_message TEXT
        )
    """)


def downgrade() -> None:
    pass
