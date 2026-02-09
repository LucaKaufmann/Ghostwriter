"""Replace summarize_sh columns with whisper_provider and whisper_model.

Revision ID: 005
Revises: 004
Create Date: 2026-02-09

"""
from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add whisper_provider and whisper_model columns, copy existing model value."""
    if context.get_context().dialect.name == "sqlite":
        # Check which columns already exist (some may have been added by manual scripts)
        conn = op.get_bind()
        result = conn.execute(sa.text("PRAGMA table_info(client_config)"))
        existing = {row[1] for row in result}

        # Add new columns only if missing
        if "whisper_provider" not in existing:
            op.execute(
                "ALTER TABLE client_config "
                "ADD COLUMN whisper_provider VARCHAR(16) "
                "NOT NULL DEFAULT 'local'"
            )
        if "whisper_model" not in existing:
            op.execute(
                "ALTER TABLE client_config "
                "ADD COLUMN whisper_model VARCHAR(32) "
                "NOT NULL DEFAULT 'base.en'"
            )
        if "whisper_timeout_minutes" not in existing:
            op.execute(
                "ALTER TABLE client_config "
                "ADD COLUMN whisper_timeout_minutes INTEGER "
                "NOT NULL DEFAULT 30"
            )
        # Copy existing whisper model value from old column
        if "summarize_sh_whisper_model" in existing:
            op.execute(
                "UPDATE client_config "
                "SET whisper_model = summarize_sh_whisper_model "
                "WHERE summarize_sh_whisper_model IS NOT NULL "
                "AND summarize_sh_whisper_model != ''"
            )
        # SQLite: leave old columns as dead weight (established pattern)
    else:
        with op.batch_alter_table("client_config") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "whisper_provider",
                    sa.String(length=16),
                    nullable=False,
                    server_default="local",
                )
            )
            batch_op.add_column(
                sa.Column(
                    "whisper_model",
                    sa.String(length=32),
                    nullable=False,
                    server_default="base.en",
                )
            )
            batch_op.add_column(
                sa.Column(
                    "whisper_timeout_minutes",
                    sa.Integer(),
                    nullable=False,
                    server_default="30",
                )
            )
        # Copy existing model value
        op.execute(
            "UPDATE client_config "
            "SET whisper_model = summarize_sh_whisper_model "
            "WHERE summarize_sh_whisper_model IS NOT NULL "
            "AND summarize_sh_whisper_model != ''"
        )


def downgrade() -> None:
    """Remove whisper_provider and whisper_model columns."""
    if context.get_context().dialect.name == "sqlite":
        # SQLite does not support DROP COLUMN without table rebuild.
        # Keep columns to avoid destructive migrations in production.
        pass
    else:
        with op.batch_alter_table("client_config") as batch_op:
            batch_op.drop_column("whisper_model")
            batch_op.drop_column("whisper_provider")
