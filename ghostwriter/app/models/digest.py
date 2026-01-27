"""Digest and DigestArticle models."""

from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import Column, String, Text
from sqlmodel import Field, SQLModel


class DigestBase(SQLModel):
    """Base digest model with shared fields."""

    filename: str = Field(description="EPUB filename")
    period: str = Field(
        sa_column=Column(String, nullable=False),
        description="Time period: morning, noon, evening, manual",
    )
    status: str = Field(
        default="queued",
        sa_column=Column(String, nullable=False, default="queued"),
        description="Job status: queued, processing, completed, failed",
    )
    stage: str | None = Field(
        default="queued",
        description="Current pipeline stage: queued, fetching, extracting, enriching, compiling, completed",
    )
    article_count: int = Field(default=0, description="Number of articles")
    error_message: str | None = Field(default=None, description="Error if failed")


class Digest(DigestBase, table=True):
    """
    Digest entity stored in the database.

    Represents a generated EPUB digest with job tracking metadata.
    """

    __tablename__ = "digests"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = Field(default=None, description="Completion time")
    downloaded_at: datetime | None = Field(default=None, description="When client downloaded this digest")
    locked_at: datetime | None = Field(default=None, description="Lock timestamp")
    locked_by: str | None = Field(default=None, description="Instance identifier")

    # Progress tracking (stored as JSON-serializable fields)
    total_feeds: int = Field(default=0, description="Total feeds to process")
    feeds_fetched: int = Field(default=0, description="Feeds fetched so far")
    total_articles: int = Field(default=0, description="Total articles found")
    articles_enriched: int = Field(default=0, description="Articles enriched so far")


class DigestCreate(SQLModel):
    """Schema for creating a new digest."""

    period: Literal["morning", "noon", "evening", "manual"] = Field(
        description="Time period"
    )


class DigestRead(SQLModel):
    """Schema for reading a digest."""

    id: UUID
    filename: str
    period: str
    status: str
    stage: str | None
    article_count: int
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None
    downloaded_at: datetime | None = None


class DigestStatus(SQLModel):
    """Schema for digest job status polling."""

    id: UUID
    status: str
    stage: str | None
    progress: dict
    started_at: datetime
    eta_seconds: int | None = None


class DigestArticleBase(SQLModel):
    """Base digest article model with shared fields."""

    title: str = Field(description="Article title")
    url: str = Field(description="Original article URL")
    mode: str = Field(
        sa_column=Column(String, nullable=False),
        description="Processing mode used: raw, summarized",
    )
    word_count: int = Field(default=0, description="Word count")
    ai_failed: bool = Field(default=False, description="True if fell back to raw")
    processing_ms: int = Field(default=0, description="Processing time in ms")

    # Article content for syncing to clients
    content: str = Field(
        default="",
        sa_column=Column(Text, nullable=False, server_default=""),
        description="Full article content (HTML or Markdown)",
    )
    author: str | None = Field(default=None, description="Article author")
    feed_title: str = Field(
        default="",
        sa_column=Column(String, nullable=False, server_default=""),
        description="Title of the source feed",
    )
    sort_order: int = Field(default=0, description="Order within the digest")


class DigestArticle(DigestArticleBase, table=True):
    """
    DigestArticle entity for audit trail.

    Links processed articles to their parent digest.
    """

    __tablename__ = "digest_articles"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    digest_id: UUID = Field(foreign_key="digests.id", index=True)
    feed_id: UUID = Field(foreign_key="feeds.id", index=True)
