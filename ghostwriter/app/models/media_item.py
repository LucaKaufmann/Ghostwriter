"""Media item model for podcast and YouTube transcription results."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import Column, Index, String, Text
from sqlmodel import Field, SQLModel


class MediaItem(SQLModel, table=True):
    """
    Media item entity stored in the database.

    Stores completed (or in-progress) transcripts for podcast episodes
    and YouTube videos, independently from digest articles.
    """

    __tablename__ = "media_items"
    __table_args__ = (
        Index("ix_media_items_feed_id", "media_feed_id"),
        Index("ix_media_items_guid", "guid"),
        Index("ix_media_items_status", "status"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    media_feed_id: UUID = Field(foreign_key="media_feeds.id", description="Parent media feed")
    guid: str = Field(description="RSS GUID for deduplication")
    url: str = Field(description="Original episode/video URL")
    content_url: str | None = Field(
        default=None,
        description="Audio enclosure URL for podcasts",
    )
    title: str = Field(description="Episode/video title")
    author: str | None = Field(default=None, description="Author or channel name")
    content: str = Field(
        default="",
        sa_column=Column(Text, nullable=False, server_default=""),
        description="Transcript or summary text",
    )
    content_type: str = Field(
        default="podcast",
        sa_column=Column(String, nullable=False, server_default="podcast"),
        description="Content type: podcast or youtube",
    )
    mode: str = Field(
        default="raw",
        sa_column=Column(String, nullable=False, server_default="raw"),
        description="Processing mode used: raw or summarize",
    )
    word_count: int = Field(default=0, description="Word count of content")
    is_summary: bool = Field(default=False, description="True if content is AI summary")
    ai_failed: bool = Field(default=False, description="True if AI summarization failed")
    processing_ms: int = Field(default=0, description="Processing time in milliseconds")
    status: str = Field(
        default="pending",
        sa_column=Column(String, nullable=False, server_default="pending"),
        description="Status: pending, processing, completed, failed",
    )
    error_message: str | None = Field(default=None, description="Error message if failed")
    consumed_at: datetime | None = Field(
        default=None,
        description="When this item was included in a digest",
    )
    consumed_digest_id: UUID | None = Field(
        default=None,
        description="Digest ID that consumed this item",
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = Field(default=None, description="When processing completed")


class MediaItemRead(SQLModel):
    """Schema for reading a media item."""

    id: UUID
    media_feed_id: UUID
    guid: str
    url: str
    content_url: str | None = None
    title: str
    author: str | None = None
    content: str = ""
    content_type: str
    mode: str
    word_count: int
    is_summary: bool
    ai_failed: bool
    processing_ms: int
    status: str
    error_message: str | None = None
    consumed_at: datetime | None = None
    consumed_digest_id: UUID | None = None
    created_at: datetime
    completed_at: datetime | None = None


class MediaItemSummary(SQLModel):
    """Schema for listing media items without full content."""

    id: UUID
    media_feed_id: UUID
    title: str
    author: str | None = None
    content_type: str
    mode: str
    word_count: int
    is_summary: bool
    ai_failed: bool
    processing_ms: int = 0
    status: str
    error_message: str | None = None
    consumed_at: datetime | None = None
    created_at: datetime
    completed_at: datetime | None = None
