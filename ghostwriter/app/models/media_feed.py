"""Media feed model for podcast and YouTube feed configuration."""

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import Column, String
from sqlmodel import Field, SQLModel


class MediaFeedBase(SQLModel):
    """Base media feed model with shared fields."""

    feed_type: str = Field(
        sa_column=Column(String, nullable=False),
        description="Feed type: podcast or youtube",
    )
    url: str = Field(index=True, unique=True, description="Original URL entered by user")
    resolved_feed_url: str | None = Field(
        default=None,
        description="Actual RSS URL (e.g. resolved YouTube channel RSS)",
    )
    title: str = Field(description="Feed display title")
    is_active: bool = Field(default=True, description="Whether feed is active")
    mode: str = Field(
        default="raw",
        sa_column=Column(String, nullable=False, default="raw"),
        description="Processing mode: raw or summarize",
    )
    max_items: int = Field(default=5, description="Max items to keep pending per run")
    deleted_at: datetime | None = Field(
        default=None,
        description="Tombstone timestamp for soft-deleted feeds",
    )


class MediaFeed(MediaFeedBase, table=True):
    """
    Media feed entity stored in the database.

    Represents a podcast or YouTube feed with processing preferences.
    Separate from regular RSS feeds to enable decoupled processing.
    """

    __tablename__ = "media_feeds"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MediaFeedCreate(SQLModel):
    """Schema for creating a new media feed."""

    feed_type: Literal["podcast", "youtube"] = Field(description="Feed type")
    url: str = Field(description="Feed URL or YouTube channel URL")
    resolved_feed_url: str | None = Field(
        default=None, description="Resolved RSS feed URL"
    )
    title: str = Field(description="Feed display title")
    is_active: bool = Field(default=True, description="Whether feed is active")
    mode: Literal["raw", "summarize"] = Field(
        default="raw", description="Processing mode"
    )
    max_items: int = Field(default=5, description="Max items per run")


class MediaFeedRead(SQLModel):
    """Schema for reading a media feed."""

    id: UUID
    feed_type: str
    url: str
    resolved_feed_url: str | None = None
    title: str
    is_active: bool
    mode: str
    max_items: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class MediaFeedUpdate(SQLModel):
    """Schema for updating an existing media feed (partial update)."""

    title: str | None = Field(default=None, description="Feed display title")
    is_active: bool | None = Field(default=None, description="Whether feed is active")
    mode: Literal["raw", "summarize"] | None = Field(
        default=None, description="Processing mode"
    )
    max_items: int | None = Field(default=None, description="Max items per run")
