"""Podcast schedule model and API schemas."""

from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column, String
from sqlmodel import Field, SQLModel

PodcastScheduleDay = Literal[
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]


class PodcastScheduleBase(SQLModel):
    """Base podcast schedule fields."""

    user_id: UUID | None = Field(default=None, foreign_key="users.id", index=True)
    name: str = Field(default="", max_length=100)
    days: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False, server_default="[]"),
    )
    time: str = Field(default="08:00", max_length=5)
    timezone: str = Field(
        default="UTC",
        sa_column=Column(String, nullable=False, server_default="UTC"),
    )
    enabled: bool = Field(default=True)
    last_run_at: datetime | None = Field(default=None)
    last_episode_id: UUID | None = Field(default=None)


class PodcastSchedule(PodcastScheduleBase, table=True):
    """Recurring podcast schedule persisted in the database."""

    __tablename__ = "podcast_schedules"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class PodcastScheduleRead(SQLModel):
    """Schema for reading a podcast schedule."""

    id: UUID
    name: str
    days: list[str]
    time: str
    timezone: str
    enabled: bool
    last_run_at: datetime | None = None
    last_episode_id: UUID | None = None
    next_run_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class PodcastScheduleCreate(SQLModel):
    """Schema for creating a podcast schedule."""

    name: str = Field(max_length=100)
    days: list[PodcastScheduleDay]
    time: str = Field(max_length=5)
    timezone: str | None = None
    enabled: bool = True


class PodcastScheduleUpdate(SQLModel):
    """Schema for updating a podcast schedule."""

    name: str | None = Field(default=None, max_length=100)
    days: list[PodcastScheduleDay] | None = None
    time: str | None = Field(default=None, max_length=5)
    timezone: str | None = None
    enabled: bool | None = None
