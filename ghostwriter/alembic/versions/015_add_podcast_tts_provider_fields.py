"""Add podcast TTS provider and API credential fields.

Revision ID: 015
Revises: 014
Create Date: 2026-02-19
"""

from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa

revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(name: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = :name LIMIT 1"
        ),
        {"name": name},
    ).first()
    return result is not None


def _existing_columns(table_name: str) -> set[str]:
    conn = op.get_bind()
    rows = conn.execute(sa.text(f"PRAGMA table_info({table_name})")).fetchall()
    return {row[1] for row in rows}


def upgrade() -> None:
    if context.get_context().dialect.name != "sqlite":
        return

    if not _table_exists("podcast_preferences"):
        return

    existing = _existing_columns("podcast_preferences")

    if "tts_provider" not in existing:
        op.execute(
            "ALTER TABLE podcast_preferences "
            "ADD COLUMN tts_provider TEXT NOT NULL DEFAULT 'openai'"
        )
    if "openai_tts_model" not in existing:
        op.execute(
            "ALTER TABLE podcast_preferences "
            "ADD COLUMN openai_tts_model TEXT NOT NULL DEFAULT 'tts-1'"
        )
    if "openai_api_key" not in existing:
        op.execute(
            "ALTER TABLE podcast_preferences "
            "ADD COLUMN openai_api_key TEXT"
        )
    if "elevenlabs_model_id" not in existing:
        op.execute(
            "ALTER TABLE podcast_preferences "
            "ADD COLUMN elevenlabs_model_id TEXT NOT NULL DEFAULT 'eleven_turbo_v2_5'"
        )
    if "elevenlabs_api_key" not in existing:
        op.execute(
            "ALTER TABLE podcast_preferences "
            "ADD COLUMN elevenlabs_api_key TEXT"
        )
    if "elevenlabs_output_format" not in existing:
        op.execute(
            "ALTER TABLE podcast_preferences "
            "ADD COLUMN elevenlabs_output_format TEXT NOT NULL DEFAULT 'mp3_44100_128'"
        )


def downgrade() -> None:
    pass
