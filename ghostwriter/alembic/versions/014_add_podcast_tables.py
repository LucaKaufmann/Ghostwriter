"""Add podcast preferences, feedback, and episode tables.

Revision ID: 014
Revises: 013
Create Date: 2026-02-19
"""

from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa

revision: str = "014"
down_revision: Union[str, None] = "013"
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


def _index_exists(name: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM sqlite_master WHERE type = 'index' AND name = :name LIMIT 1"
        ),
        {"name": name},
    ).first()
    return result is not None


def upgrade() -> None:
    if context.get_context().dialect.name != "sqlite":
        return

    if not _table_exists("podcast_preferences"):
        op.create_table(
            "podcast_preferences",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=True),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column(
                "schedule",
                sa.String(),
                nullable=False,
                server_default=sa.text("'manual'"),
            ),
            sa.Column(
                "schedule_time",
                sa.String(),
                nullable=False,
                server_default=sa.text("'08:00'"),
            ),
            sa.Column(
                "schedule_day",
                sa.String(),
                nullable=False,
                server_default=sa.text("'monday'"),
            ),
            sa.Column(
                "topic_weights",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
            sa.Column(
                "boost_sources",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            ),
            sa.Column(
                "boost_keywords",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            ),
            sa.Column(
                "filter_keywords",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            ),
            sa.Column(
                "preferred_length_minutes",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("15"),
            ),
            sa.Column(
                "style",
                sa.String(),
                nullable=False,
                server_default=sa.text("'casual'"),
            ),
            sa.Column(
                "host_a_voice",
                sa.String(),
                nullable=False,
                server_default=sa.text("'alloy'"),
            ),
            sa.Column(
                "host_b_voice",
                sa.String(),
                nullable=False,
                server_default=sa.text("'echo'"),
            ),
            sa.Column(
                "podcast_feed_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "podcast_feed_title",
                sa.String(),
                nullable=False,
                server_default=sa.text("'My Ghostwriter Digest'"),
            ),
            sa.Column(
                "podcast_feed_description",
                sa.String(),
                nullable=False,
                server_default=sa.text(
                    "'AI-generated audio digest of your RSS feeds'"
                ),
            ),
            sa.Column("podcast_feed_artwork_path", sa.String(), nullable=True),
            sa.Column(
                "podcast_feed_token",
                sa.String(),
                nullable=False,
                server_default=sa.text("''"),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.CheckConstraint(
                "schedule IN ('daily', 'weekly', 'manual')",
                name="ck_podcast_preferences_schedule",
            ),
            sa.CheckConstraint(
                "schedule_day IN ('monday','tuesday','wednesday','thursday','friday','saturday','sunday')",
                name="ck_podcast_preferences_schedule_day",
            ),
            sa.CheckConstraint(
                "style IN ('casual', 'formal', 'deep-dive')",
                name="ck_podcast_preferences_style",
            ),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _index_exists("ix_podcast_preferences_user_id"):
        op.create_index(
            "ix_podcast_preferences_user_id",
            "podcast_preferences",
            ["user_id"],
            unique=False,
        )

    if not _table_exists("article_feedback"):
        op.create_table(
            "article_feedback",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=True),
            sa.Column("article_id", sa.String(), nullable=False),
            sa.Column("digest_id", sa.String(), nullable=True),
            sa.Column("rating", sa.String(), nullable=True),
            sa.Column("read_duration_sec", sa.Integer(), nullable=True),
            sa.Column("bookmarked", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("shared", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.CheckConstraint(
                "rating IN ('up', 'down') OR rating IS NULL",
                name="ck_article_feedback_rating",
            ),
            sa.ForeignKeyConstraint(["digest_id"], ["digests.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "user_id", "article_id", name="uq_article_feedback_user_article"
            ),
        )

    if not _index_exists("ix_article_feedback_user_id"):
        op.create_index(
            "ix_article_feedback_user_id",
            "article_feedback",
            ["user_id"],
            unique=False,
        )
    if not _index_exists("ix_article_feedback_article_id"):
        op.create_index(
            "ix_article_feedback_article_id",
            "article_feedback",
            ["article_id"],
            unique=False,
        )
    if not _index_exists("ix_article_feedback_digest_id"):
        op.create_index(
            "ix_article_feedback_digest_id",
            "article_feedback",
            ["digest_id"],
            unique=False,
        )
    if not _index_exists("ix_article_feedback_created_at"):
        op.create_index(
            "ix_article_feedback_created_at",
            "article_feedback",
            ["created_at"],
            unique=False,
        )

    if not _table_exists("podcast_episodes"):
        op.create_table(
            "podcast_episodes",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("digest_id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=True),
            sa.Column("script", sa.Text(), nullable=True),
            sa.Column("audio_path", sa.String(), nullable=True),
            sa.Column("audio_size_bytes", sa.Integer(), nullable=True),
            sa.Column("duration_seconds", sa.Integer(), nullable=True),
            sa.Column(
                "article_ids",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            ),
            sa.Column(
                "article_count",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column("generation_cost_cents", sa.Integer(), nullable=True),
            sa.Column(
                "status",
                sa.String(),
                nullable=False,
                server_default=sa.text("'pending'"),
            ),
            sa.Column("error_message", sa.String(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.CheckConstraint(
                "status IN ('pending', 'generating_script', 'generating_audio', 'ready', 'failed')",
                name="ck_podcast_episodes_status",
            ),
            sa.ForeignKeyConstraint(["digest_id"], ["digests.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("digest_id", name="uq_podcast_episodes_digest_id"),
        )

    if not _index_exists("ix_podcast_episodes_digest_id"):
        op.create_index(
            "ix_podcast_episodes_digest_id",
            "podcast_episodes",
            ["digest_id"],
            unique=False,
        )
    if not _index_exists("ix_podcast_episodes_user_id"):
        op.create_index(
            "ix_podcast_episodes_user_id",
            "podcast_episodes",
            ["user_id"],
            unique=False,
        )
    if not _index_exists("ix_podcast_episodes_status"):
        op.create_index(
            "ix_podcast_episodes_status",
            "podcast_episodes",
            ["status"],
            unique=False,
        )


def downgrade() -> None:
    pass
