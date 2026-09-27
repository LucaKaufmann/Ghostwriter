"""Persist one-off digest ownership independently of podcast episodes.

Revision ID: 028
Revises: 027
"""

import json
from collections import defaultdict
from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa

from alembic import context, op

revision: str = "028"
down_revision: str | None = "027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid_hex(value: object) -> str | None:
    try:
        return UUID(str(value)).hex
    except (ValueError, TypeError, AttributeError):
        return None


def upgrade() -> None:
    if context.get_context().dialect.name != "sqlite":
        return
    conn = op.get_bind()
    columns = {
        row[1] for row in conn.execute(sa.text("PRAGMA table_info(digests)"))
    }
    if "one_off_owner_id" not in columns:
        op.execute(
            "ALTER TABLE digests ADD COLUMN one_off_owner_id CHAR(32) REFERENCES users(id)"
        )

    valid_users = {
        parsed for (raw,) in conn.execute(sa.text("SELECT id FROM users"))
        if (parsed := _uuid_hex(raw)) is not None
    }
    existing_digests = {
        parsed for (raw,) in conn.execute(sa.text("SELECT id FROM digests"))
        if (parsed := _uuid_hex(raw)) is not None
    }
    owners: dict[str, set[str | None]] = defaultdict(set)
    rows = conn.execute(sa.text(
        "SELECT digest_ids, user_id FROM podcast_episodes WHERE trigger = 'one_off'"
    ))
    for raw_ids, raw_owner in rows:
        try:
            digest_ids = json.loads(raw_ids) if isinstance(raw_ids, str) else raw_ids
        except (TypeError, ValueError):
            continue
        if not isinstance(digest_ids, list):
            continue
        owner = _uuid_hex(raw_owner)
        if owner not in valid_users:
            owner = None
        for raw_digest in digest_ids:
            digest_id = _uuid_hex(raw_digest)
            if digest_id in existing_digests:
                owners[digest_id].add(owner)

    for digest_id, claimed_owners in owners.items():
        if len(claimed_owners) != 1 or None in claimed_owners:
            continue
        conn.execute(
            sa.text(
                "UPDATE digests SET one_off_owner_id = :owner "
                "WHERE id = :digest AND one_off_owner_id IS NULL"
            ),
            {"owner": next(iter(claimed_owners)), "digest": digest_id},
        )


def downgrade() -> None:
    pass
