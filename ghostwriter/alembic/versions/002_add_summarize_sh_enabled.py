"""Add summarize_sh_enabled to client_config.

Revision ID: 002
Revises: 001
Create Date: 2026-02-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add summarize_sh_enabled column."""
    with op.batch_alter_table("client_config") as batch_op:
        batch_op.add_column(
            sa.Column(
                "summarize_sh_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )


def downgrade() -> None:
    """Remove summarize_sh_enabled column."""
    with op.batch_alter_table("client_config") as batch_op:
        batch_op.drop_column("summarize_sh_enabled")
