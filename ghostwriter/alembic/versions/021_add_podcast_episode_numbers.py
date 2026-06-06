"""Add stable podcast episode numbers.

Revision ID: 021
Revises: 020
Create Date: 2026-06-06
"""

from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa

revision: str = "021"
down_revision: Union[str, None] = "020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(name: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name=:name LIMIT 1"
        ),
        {"name": name},
    )
    return result.fetchone() is not None


def _existing_columns(table_name: str) -> set[str]:
    conn = op.get_bind()
    result = conn.execute(sa.text(f"PRAGMA table_info({table_name})"))
    return {row[1] for row in result}


def upgrade() -> None:
    if context.get_context().dialect.name != "sqlite":
        return

    if not _table_exists("podcast_episodes"):
        return

    conn = op.get_bind()
    existing = _existing_columns("podcast_episodes")

    if "episode_number" not in existing:
        op.execute("ALTER TABLE podcast_episodes ADD COLUMN episode_number INTEGER")

    if not _table_exists("podcast_episode_counters"):
        op.execute(
            """
            CREATE TABLE podcast_episode_counters (
                owner_key VARCHAR NOT NULL PRIMARY KEY,
                next_episode_number INTEGER NOT NULL DEFAULT 1
            )
            """
        )

    rows = conn.execute(
        sa.text(
            """
            SELECT id, user_id
            FROM podcast_episodes
            WHERE status = 'ready'
              AND COALESCE(trigger, 'manual') != 'one_off'
              AND episode_number IS NULL
            ORDER BY
              CASE WHEN user_id IS NULL THEN '' ELSE user_id END,
              COALESCE(completed_at, created_at),
              created_at,
              id
            """
        )
    ).fetchall()

    next_numbers: dict[str, int] = {}
    for row in rows:
        owner_key = row[1] or ""
        if owner_key not in next_numbers:
            current_max = conn.execute(
                sa.text(
                    """
                    SELECT MAX(episode_number)
                    FROM podcast_episodes
                    WHERE status = 'ready'
                      AND COALESCE(trigger, 'manual') != 'one_off'
                      AND episode_number IS NOT NULL
                      AND (
                        (:user_id IS NULL AND user_id IS NULL)
                        OR user_id = :user_id
                      )
                    """
                ),
                {"user_id": row[1]},
            ).scalar()
            next_numbers[owner_key] = int(current_max or 0) + 1

        conn.execute(
            sa.text(
                "UPDATE podcast_episodes "
                "SET episode_number = :episode_number "
                "WHERE id = :episode_id"
            ),
            {"episode_number": next_numbers[owner_key], "episode_id": row[0]},
        )
        next_numbers[owner_key] += 1

    counter_rows = conn.execute(
        sa.text(
            """
            SELECT
              CASE WHEN user_id IS NULL THEN '__legacy__' ELSE user_id END AS owner_key,
              MAX(episode_number) + 1 AS next_episode_number
            FROM podcast_episodes
            WHERE status = 'ready'
              AND COALESCE(trigger, 'manual') != 'one_off'
              AND episode_number IS NOT NULL
            GROUP BY owner_key
            """
        )
    ).fetchall()

    for row in counter_rows:
        conn.execute(
            sa.text(
                """
                INSERT INTO podcast_episode_counters (
                    owner_key,
                    next_episode_number
                )
                VALUES (:owner_key, :next_episode_number)
                ON CONFLICT(owner_key) DO UPDATE SET
                    next_episode_number = MAX(
                        podcast_episode_counters.next_episode_number,
                        excluded.next_episode_number
                    )
                """
            ),
            {
                "owner_key": row[0],
                "next_episode_number": int(row[1] or 1),
            },
        )


def downgrade() -> None:
    pass
