"""Feed model for RSS feed configuration."""

from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import field_validator
from sqlalchemy import BigInteger, Column, String
from sqlmodel import Field, SQLModel

MAX_FEED_ARTICLES = 2**31 - 1


def readable_article_limit(value: int) -> int:
    """Project legacy stored caps to the native wire range without rewriting data."""
    return min(MAX_FEED_ARTICLES, max(0, value))


class FeedBase(SQLModel):
    """Base feed model with shared fields."""

    url: str = Field(index=True, unique=True, description="Feed URL")
    title: str = Field(description="Feed display title")
    is_active: bool = Field(default=True, description="Whether feed is active")
    mode: str = Field(
        default="raw",
        sa_column=Column(String, nullable=False, default="raw"),
        description="Processing mode: raw or summarize",
    )
    max_articles: int = Field(default=10, description="Max articles per run")
    deleted_at: datetime | None = Field(
        default=None,
        description="Tombstone timestamp for deleted feeds"
    )


class Feed(FeedBase, table=True):
    """
    Feed entity stored in the database.

    Represents an RSS/Atom feed configuration with processing preferences.
    """

    __tablename__ = "feeds"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    version: int = Field(default=0, sa_type=BigInteger)


class FeedCreate(SQLModel):
    """Schema for creating a new feed."""

    url: str = Field(description="Feed URL")
    title: str = Field(description="Feed display title")
    is_active: bool = Field(default=True, description="Whether feed is active")
    mode: Literal["raw", "summarize"] = Field(
        default="raw", description="Processing mode"
    )
    max_articles: int = Field(default=10, ge=0, le=MAX_FEED_ARTICLES, description="Max articles per run")


class FeedRead(SQLModel):
    """Schema for reading a feed."""

    id: UUID
    url: str
    title: str
    is_active: bool
    mode: str
    max_articles: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
    version: int

    @field_validator("max_articles")
    @classmethod
    def compatible_article_limit(cls, value: int) -> int:
        return readable_article_limit(value)


class FeedSync(SQLModel):
    """Schema for syncing feeds from the client (bulk update)."""

    url: str = Field(description="Feed URL")
    title: str = Field(description="Feed display title")
    is_active: bool = Field(default=True, description="Whether feed is active")
    mode: Literal["raw", "summarize"] = Field(
        default="raw", description="Processing mode"
    )
    max_articles: int = Field(default=10, ge=0, le=MAX_FEED_ARTICLES, description="Max articles per run")


class FeedUpdate(SQLModel):
    """Schema for updating an existing feed (partial update)."""

    title: str | None = Field(default=None, description="Feed display title")
    is_active: bool | None = Field(default=None, description="Whether feed is active")
    mode: Literal["raw", "summarize"] | None = Field(
        default=None, description="Processing mode"
    )
    max_articles: int | None = Field(default=None, ge=0, le=MAX_FEED_ARTICLES, description="Max articles per run")
