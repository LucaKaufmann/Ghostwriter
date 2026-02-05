"""Add summarize_sh_whisper_model to client_config.

Revision ID: 004
Revises: 003
Create Date: 2026-02-05

"""
from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add summarize_sh_whisper_model column."""
    if context.get_context().dialect.name == "sqlite":
        op.execute(
            "ALTER TABLE client_config "
            "ADD COLUMN summarize_sh_whisper_model VARCHAR(32) "
            "NOT NULL DEFAULT 'base.en'"
        )
    else:
        with op.batch_alter_table("client_config") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "summarize_sh_whisper_model",
                    sa.String(length=32),
                    nullable=False,
                    server_default="base.en",
                )
            )


def downgrade() -> None:
    """Remove summarize_sh_whisper_model column."""
    if context.get_context().dialect.name == "sqlite":
        # SQLite does not support DROP COLUMN without table rebuild.
        # Keep column to avoid destructive migrations in production.
        pass
    else:
        with op.batch_alter_table("client_config") as batch_op:
            batch_op.drop_column("summarize_sh_whisper_model")
