"""Add dedicated cover API key fields to client_config.

Revision ID: 009
Revises: 008
Create Date: 2026-02-14
"""

from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _get_existing_columns(table: str) -> set[str]:
    conn = op.get_bind()
    result = conn.execute(sa.text(f"PRAGMA table_info({table})"))
    return {row[1] for row in result}


def _add_column_if_missing(table: str, column: str, col_def: str) -> None:
    existing = _get_existing_columns(table)
    if column not in existing:
        op.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")


def upgrade() -> None:
    if context.get_context().dialect.name != "sqlite":
        return

    _add_column_if_missing(
        "client_config",
        "cover_openai_api_key",
        "TEXT NOT NULL DEFAULT ''",
    )
    _add_column_if_missing(
        "client_config",
        "cover_gemini_api_key",
        "TEXT NOT NULL DEFAULT ''",
    )


def downgrade() -> None:
    pass
