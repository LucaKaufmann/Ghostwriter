"""Podcast episode model and API schemas."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column, Index, String, Text
from sqlmodel import Field, SQLModel


class PodcastEpisodeBase(SQLModel):
    """Base podcast episode fields."""

    digest_ids: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False, server_default="[]"),
    )
    trigger: str = Field(
        default="manual",
        sa_column=Column(String, nullable=False, server_default="manual"),
    )
    user_id: UUID | None = Field(default=None, foreign_key="users.id", index=True)
    script: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    audio_path: str | None = Field(default=None)
    audio_size_bytes: int | None = Field(default=None, ge=0)
    duration_seconds: int | None = Field(default=None, ge=0)
    article_ids: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False, server_default="[]"),
    )
    article_count: int = Field(default=0, ge=0)
    generation_cost_cents: int | None = Field(default=None, ge=0)
    status: str = Field(
        default="pending",
        sa_column=Column(String, nullable=False, server_default="pending"),
    )
    error_message: str | None = Field(default=None)


class PodcastEpisode(PodcastEpisodeBase, table=True):
    """Generated podcast episode persisted in the database."""

    __tablename__ = "podcast_episodes"
    __table_args__ = (
        Index("ix_podcast_episodes_status", "status"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: datetime | None = Field(default=None)
    completed_at: datetime | None = Field(default=None)


class PodcastEpisodeSummaryRead(SQLModel):
    """Schema for listing podcast episodes."""

    id: UUID
    digest_ids: list[str]
    trigger: str = "manual"
    status: str
    audio_size_bytes: int | None = None
    duration_seconds: int | None = None
    article_count: int
    generation_cost_cents: int | None = None
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class PodcastEpisodeArticleRead(SQLModel):
    """Article metadata included in a podcast episode."""

    id: UUID
    title: str
    url: str
    feed_title: str


class PodcastEpisodeRead(PodcastEpisodeSummaryRead):
    """Schema for reading a podcast episode with script/articles."""

    script: str | None = None
    article_ids: list[str]
    articles: list[PodcastEpisodeArticleRead] = []
