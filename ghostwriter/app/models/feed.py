"""Feed model for RSS feed configuration."""

from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import Column, String
from sqlmodel import Field, SQLModel


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


class Feed(FeedBase, table=True):
    """
    Feed entity stored in the database.

    Represents an RSS/Atom feed configuration with processing preferences.
    """

    __tablename__ = "feeds"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class FeedCreate(SQLModel):
    """Schema for creating a new feed."""

    url: str = Field(description="Feed URL")
    title: str = Field(description="Feed display title")
    is_active: bool = Field(default=True, description="Whether feed is active")
    mode: Literal["raw", "summarize"] = Field(
        default="raw", description="Processing mode"
    )
    max_articles: int = Field(default=10, description="Max articles per run")


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


class FeedSync(SQLModel):
    """Schema for syncing feeds from the client (bulk update)."""

    url: str = Field(description="Feed URL")
    title: str = Field(description="Feed display title")
    is_active: bool = Field(default=True, description="Whether feed is active")
    mode: Literal["raw", "summarize"] = Field(
        default="raw", description="Processing mode"
    )
    max_articles: int = Field(default=10, description="Max articles per run")
