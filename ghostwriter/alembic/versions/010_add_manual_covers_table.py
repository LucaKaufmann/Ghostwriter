"""Add manual_covers table for uploaded digest covers.

Revision ID: 010
Revises: 009
Create Date: 2026-02-14
"""

from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(
        sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name=:name"),
        {"name": table},
    ).first()
    return result is not None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(sa.text(f"PRAGMA table_info({table})"))
    return any(row[1] == column for row in result)


def upgrade() -> None:
    if context.get_context().dialect.name != "sqlite":
        return

    if not _table_exists("manual_covers"):
        op.execute(
            """
            CREATE TABLE manual_covers (
                id CHAR(32) NOT NULL PRIMARY KEY,
                name VARCHAR NOT NULL DEFAULT '',
                file_name VARCHAR NOT NULL DEFAULT '',
                media_type VARCHAR NOT NULL DEFAULT 'image/jpeg',
                size_bytes INTEGER NOT NULL DEFAULT 0,
                is_active BOOLEAN NOT NULL DEFAULT 0,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
            """
        )

    if not _column_exists("manual_covers", "is_active"):
        op.execute(
            "ALTER TABLE manual_covers ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 0"
        )


def downgrade() -> None:
    pass
