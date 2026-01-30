"""Wallabag configuration model for database-backed settings."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel
from sqlmodel import Field, SQLModel


class WallabagConfig(SQLModel, table=True):
    """Singleton table for Wallabag integration configuration."""

    __tablename__ = "wallabag_config"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    url: str = Field(default="")
    client_id: str = Field(default="")
    client_secret: str = Field(default="")
    username: str = Field(default="")
    password: str = Field(default="")
    mode: str = Field(default="raw")
    max_articles: int = Field(default=20, ge=1)
    tag_on_process: str = Field(default="ghostwriter")
    enabled: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class WallabagConfigUpdate(SQLModel):
    """Schema for updating Wallabag configuration."""

    url: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    username: str | None = None
    password: str | None = None
    mode: str | None = None
    max_articles: int | None = Field(default=None, ge=1)
    tag_on_process: str | None = None
    enabled: bool | None = None


class WallabagConfigRead(BaseModel):
    """Response model with masked password."""

    url: str
    client_id: str
    client_secret: str
    username: str
    password: str  # masked
    mode: str
    max_articles: int
    tag_on_process: str
    enabled: bool
