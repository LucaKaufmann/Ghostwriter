"""Schedule model for persistent digest scheduling."""

from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import Column, String
from sqlmodel import Field, SQLModel


class ScheduleBase(SQLModel):
    """Base schedule model with shared fields."""

    period: str = Field(
        sa_column=Column(String, nullable=False),
        description="Time period: morning, noon, evening",
    )
    hour: int = Field(default=7, ge=0, le=23, description="Hour in 24h format (0-23)")
    minute: int = Field(default=0, ge=0, le=59, description="Minute (0-59)")
    enabled: bool = Field(default=True, description="Whether this schedule is active")
    timezone: str = Field(default="UTC", description="IANA timezone identifier")


class Schedule(ScheduleBase, table=True):
    """
    Schedule entity stored in the database.

    Each schedule represents a recurring digest generation time.
    Periods are unique - only one schedule per period (morning, noon, evening).
    """

    __tablename__ = "schedules"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_run_at: datetime | None = Field(default=None, description="Last successful run")
    last_run_digest_id: UUID | None = Field(default=None, description="Last digest ID")


class ScheduleCreate(SQLModel):
    """Schema for creating a new schedule."""

    period: Literal["morning", "noon", "evening"] = Field(description="Time period")
    hour: int = Field(default=7, ge=0, le=23, description="Hour in 24h format")
    minute: int = Field(default=0, ge=0, le=59, description="Minute")
    enabled: bool = Field(default=True, description="Whether this schedule is active")
    timezone: str = Field(default="UTC", description="IANA timezone")


class ScheduleUpdate(SQLModel):
    """Schema for updating a schedule."""

    hour: int | None = Field(default=None, ge=0, le=23, description="Hour in 24h format")
    minute: int | None = Field(default=None, ge=0, le=59, description="Minute")
    enabled: bool | None = Field(default=None, description="Whether this schedule is active")
    timezone: str | None = Field(default=None, description="IANA timezone")


class ScheduleRead(SQLModel):
    """Schema for reading a schedule."""

    id: UUID
    period: str
    hour: int
    minute: int
    enabled: bool
    timezone: str
    created_at: datetime
    updated_at: datetime
    last_run_at: datetime | None
    last_run_digest_id: UUID | None
    next_run_at: datetime | None = None  # Computed field
