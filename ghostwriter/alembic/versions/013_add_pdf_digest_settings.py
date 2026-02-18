"""Add PDF digest settings to client_config.

Revision ID: 013
Revises: 012
Create Date: 2026-02-18
"""

from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(sa.text(f"PRAGMA table_info({table})"))
    return any(row[1] == column for row in result)


def upgrade() -> None:
    if context.get_context().dialect.name != "sqlite":
        return

    if not _column_exists("client_config", "pdf_enabled"):
        op.execute(
            "ALTER TABLE client_config ADD COLUMN pdf_enabled BOOLEAN NOT NULL DEFAULT 0"
        )

    if not _column_exists("client_config", "pdf_page_size"):
        op.execute(
            "ALTER TABLE client_config ADD COLUMN pdf_page_size VARCHAR NOT NULL DEFAULT 'A4'"
        )


def downgrade() -> None:
    pass
