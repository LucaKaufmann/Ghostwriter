"""Push notification device registrations."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class PushDeviceBase(SQLModel):
    """Base push device model with shared fields."""

    user_id: UUID = Field(foreign_key="users.id", index=True)
    device_id: str = Field(
        index=True,
        max_length=128,
        description="Client-generated stable device identifier",
    )
    platform: str = Field(description="Device platform (ios or android)")
    token: str = Field(
        max_length=4096,
        description="APNs device token (iOS) or FCM registration token (Android)",
    )

    enabled: bool = Field(default=True, description="Whether push notifications are enabled")
    disabled_at: datetime | None = Field(default=None, description="When this device was disabled")

    app_version: str | None = Field(default=None, max_length=64, description="App version string")
    device_model: str | None = Field(default=None, max_length=128, description="Device model string")

    last_seen_at: datetime = Field(
        default_factory=datetime.utcnow, description="Last registration/update time"
    )
    failure_count: int = Field(default=0, description="Consecutive send failures")
    last_error: str | None = Field(default=None, max_length=500, description="Last send error")


class PushDevice(PushDeviceBase, table=True):
    """
    Push device entity stored in the database.

    Each device belongs to a user account and can be enabled/disabled independently.
    """

    __tablename__ = "push_devices"
    __table_args__ = (
        UniqueConstraint("user_id", "device_id", name="uq_push_devices_user_device"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class PushDeviceRegister(SQLModel):
    """Request schema for registering/updating a device token."""

    device_id: str = Field(max_length=128)
    platform: Literal["ios", "android"]
    token: str = Field(max_length=4096)
    app_version: str | None = Field(default=None, max_length=64)
    device_model: str | None = Field(default=None, max_length=128)


class PushDeviceRead(SQLModel):
    """Response schema for a registered device (token is not returned)."""

    id: UUID
    device_id: str
    platform: str
    enabled: bool
    disabled_at: datetime | None
    app_version: str | None
    device_model: str | None
    last_seen_at: datetime
    created_at: datetime
    updated_at: datetime
