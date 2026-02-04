"""Add summarize_sh_on_fail to client_config.

Revision ID: 003
Revises: 002
Create Date: 2026-02-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add summarize_sh_on_fail column."""
    with op.batch_alter_table("client_config") as batch_op:
        batch_op.add_column(
            sa.Column(
                "summarize_sh_on_fail",
                sa.String(length=32),
                nullable=False,
                server_default="raw",
            )
        )


def downgrade() -> None:
    """Remove summarize_sh_on_fail column."""
    with op.batch_alter_table("client_config") as batch_op:
        batch_op.drop_column("summarize_sh_on_fail")
