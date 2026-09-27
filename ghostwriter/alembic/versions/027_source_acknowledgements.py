"""Add durable source acknowledgement intents.

Revision ID: 027
Revises: 026
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import context, op

revision: str = "027"
down_revision: str | None = "026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if context.get_context().dialect.name != "sqlite":
        return
    conn = op.get_bind()
    objects = {
        (row[0], row[1]) for row in conn.execute(
            sa.text("SELECT type, name FROM sqlite_master WHERE type IN ('table','index')")
        )
    }
    if ("table", "source_acknowledgements") not in objects:
        op.create_table(
            "source_acknowledgements",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("digest_id", sa.Uuid(), nullable=False),
            sa.Column("provider", sa.String(), nullable=False),
            sa.Column("source_identity", sa.String(), nullable=False),
            sa.Column("source_config_fingerprint", sa.String(), nullable=False),
            sa.Column("external_item_id", sa.String(), nullable=False),
            sa.Column("action", sa.String(), nullable=False),
            sa.Column("state", sa.String(), nullable=False),
            sa.Column("attempt_count", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("last_attempt_at", sa.DateTime(), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("last_error_code", sa.String(), nullable=True),
            sa.UniqueConstraint(
                "digest_id", "provider", "source_identity", "source_config_fingerprint",
                "external_item_id", "action", name="uq_source_ack_item",
            ),
        )
    if ("index", "ix_source_acknowledgements_digest_id") not in objects:
        op.create_index(
            "ix_source_acknowledgements_digest_id", "source_acknowledgements",
            ["digest_id"],
        )
    if ("index", "ix_source_ack_state_created") not in objects:
        op.create_index(
            "ix_source_ack_state_created", "source_acknowledgements",
            ["state", "created_at"],
        )


def downgrade() -> None:
    pass
