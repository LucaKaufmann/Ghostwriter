"""Add durable feed versions, global clock, and replay receipts.

Revision ID: 026
Revises: 025
"""

from typing import Sequence, Union
from uuid import uuid4

from alembic import context, op
import sqlalchemy as sa

revision: str = "026"
down_revision: Union[str, None] = "025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if context.get_context().dialect.name != "sqlite":
        return
    conn = op.get_bind()
    tables = {row[0] for row in conn.execute(sa.text("SELECT name FROM sqlite_master WHERE type='table'"))}
    if "feeds" in tables:
        columns = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(feeds)"))}
        if "version" not in columns:
            op.execute("ALTER TABLE feeds ADD COLUMN version BIGINT NOT NULL DEFAULT 0")
    if "feed_sync_clock" not in tables:
        op.create_table(
            "feed_sync_clock",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("version", sa.BigInteger(), nullable=False),
            sa.Column("server_instance_id", sa.Text(), nullable=False),
            sa.CheckConstraint("id = 1"),
        )
    if "feed_mutation_receipts" not in tables:
        op.create_table(
            "feed_mutation_receipts",
            sa.Column("op_id", sa.Text(), primary_key=True),
            sa.Column("payload_hash", sa.Text(), nullable=False),
            sa.Column("result_json", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
    existing = conn.execute(sa.text("SELECT version FROM feed_sync_clock WHERE id=1")).scalar_one_or_none()
    high_water = existing or 0
    if "feeds" in tables:
        high_water = max(high_water, conn.execute(sa.text("SELECT COALESCE(MAX(version),0) FROM feeds")).scalar_one())
        rows = conn.execute(sa.text(
            "SELECT id FROM feeds WHERE url NOT LIKE 'synthetic://%' AND version=0 ORDER BY created_at, id"
        )).all()
        for feed_id, in rows:
            high_water += 1
            conn.execute(sa.text("UPDATE feeds SET version=:version WHERE id=:id"),
                         {"version": high_water, "id": feed_id})
    if existing is None:
        conn.execute(sa.text("INSERT INTO feed_sync_clock(id,version,server_instance_id) VALUES (1,:version,:identity)"),
                     {"version": high_water, "identity": str(uuid4())})
    elif existing < high_water:
        conn.execute(sa.text("UPDATE feed_sync_clock SET version=:version WHERE id=1"),
                     {"version": high_water})


def downgrade() -> None:
    pass
