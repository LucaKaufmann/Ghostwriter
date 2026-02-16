"""Media processing run model for tracking pipeline execution history."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import Column, String, Text
from sqlmodel import Field, SQLModel


class MediaProcessingRun(SQLModel, table=True):
    """Tracks each execution of the media processing pipeline."""

    __tablename__ = "media_processing_runs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = Field(default=None)
    duration_ms: int = Field(default=0)
    status: str = Field(
        default="running",
        sa_column=Column(String, nullable=False, server_default="running"),
        description="Status: running, completed, failed",
    )
    items_discovered: int = Field(default=0)
    items_processed: int = Field(default=0)
    items_failed: int = Field(default=0)
    error_message: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )


class MediaProcessingRunRead(SQLModel):
    """Schema for reading a media processing run."""

    id: UUID
    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: int = 0
    status: str
    items_discovered: int = 0
    items_processed: int = 0
    items_failed: int = 0
    error_message: str | None = None
