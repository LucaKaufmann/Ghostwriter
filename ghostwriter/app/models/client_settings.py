"""Client settings model for activity tracking and configuration."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class ClientSettings(SQLModel, table=True):
    """
    Singleton settings for client activity tracking and auto-disable configuration.

    This table should only have one row, created on first access.
    Tracks when the client was last active and configures auto-disable behavior.
    """

    __tablename__ = "client_settings"

    id: UUID = Field(default_factory=uuid4, primary_key=True)

    # Activity tracking
    last_heartbeat_at: datetime | None = Field(
        default=None,
        description="Last time the client sent a heartbeat"
    )
    last_download_at: datetime | None = Field(
        default=None,
        description="Last time a digest was downloaded"
    )
    last_feed_sync_at: datetime | None = Field(
        default=None,
        description="Last time feeds were synced from the client"
    )

    # Auto-disable configuration
    auto_disable_enabled: bool = Field(
        default=True,
        description="Whether to auto-disable schedules on inactivity"
    )
    auto_disable_after_days: int = Field(
        default=7,
        ge=1,
        le=365,
        description="Days of inactivity before auto-disabling schedules"
    )

    # State tracking
    schedules_auto_disabled: bool = Field(
        default=False,
        description="Whether schedules were auto-disabled due to inactivity"
    )
    auto_disabled_at: datetime | None = Field(
        default=None,
        description="When schedules were auto-disabled"
    )

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ClientSettingsRead(SQLModel):
    """Schema for reading client settings."""

    last_heartbeat_at: datetime | None
    last_download_at: datetime | None
    last_feed_sync_at: datetime | None
    auto_disable_enabled: bool
    auto_disable_after_days: int
    schedules_auto_disabled: bool
    auto_disabled_at: datetime | None
    days_until_auto_disable: int | None = None  # Computed field


class ClientSettingsUpdate(SQLModel):
    """Schema for updating client settings."""

    auto_disable_enabled: bool | None = Field(
        default=None,
        description="Whether to auto-disable schedules on inactivity"
    )
    auto_disable_after_days: int | None = Field(
        default=None,
        ge=1,
        le=365,
        description="Days of inactivity before auto-disabling schedules"
    )
