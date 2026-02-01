"""Client activity and settings endpoints."""

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.logging import digest_logger
from app.core.security import verify_api_key
from app.models.client_settings import ClientSettingsRead, ClientSettingsUpdate
from app.services import activity_tracker

router = APIRouter()


class HeartbeatResponse(BaseModel):
    """Response from heartbeat endpoint."""

    status: str
    received_at: datetime
    schedules_active: bool
    message: str | None = None


class ClientStatusResponse(BaseModel):
    """Full client status response."""

    last_heartbeat_at: datetime | None
    last_download_at: datetime | None
    last_feed_sync_at: datetime | None
    auto_disable_enabled: bool
    auto_disable_after_days: int
    schedules_auto_disabled: bool
    auto_disabled_at: datetime | None
    days_until_auto_disable: int | None


class SettingsUpdateRequest(BaseModel):
    """Request to update client settings."""

    auto_disable_enabled: bool | None = Field(
        default=None,
        description="Whether to auto-disable schedules on inactivity"
    )
    auto_disable_after_days: int | None = Field(
        default=None,
        ge=1,
        le=365,
        description="Days of inactivity before auto-disabling (1-365)"
    )


@router.post("/heartbeat", response_model=HeartbeatResponse, dependencies=[Depends(verify_api_key)])
async def send_heartbeat() -> HeartbeatResponse:
    """
    Send a heartbeat to indicate the client is active.

    Call this periodically (e.g., daily) to prevent auto-disable of schedules.
    If schedules were auto-disabled due to inactivity, this will re-enable them.
    """
    settings = activity_tracker.record_heartbeat()
    reactivated = not settings.schedules_auto_disabled  # True if schedules are active (may have been reactivated)
    digest_logger.sync_heartbeat(
        schedules_active=not settings.schedules_auto_disabled,
        reactivated=reactivated and settings.auto_disable_enabled,
    )

    message = None
    if not settings.schedules_auto_disabled and settings.auto_disable_enabled:
        days_remaining = activity_tracker.get_days_until_auto_disable()
        if days_remaining is not None and days_remaining <= 3:
            message = f"Schedules will auto-disable in {days_remaining} days without activity"

    return HeartbeatResponse(
        status="ok",
        received_at=settings.last_heartbeat_at,
        schedules_active=not settings.schedules_auto_disabled,
        message=message,
    )


@router.get("/status", response_model=ClientStatusResponse, dependencies=[Depends(verify_api_key)])
async def get_client_status() -> ClientStatusResponse:
    """
    Get the current client status and activity information.

    Shows last activity times, auto-disable configuration, and days until
    schedules would be auto-disabled.
    """
    settings = activity_tracker.get_client_settings()
    days_remaining = activity_tracker.get_days_until_auto_disable()

    return ClientStatusResponse(
        last_heartbeat_at=settings.last_heartbeat_at,
        last_download_at=settings.last_download_at,
        last_feed_sync_at=settings.last_feed_sync_at,
        auto_disable_enabled=settings.auto_disable_enabled,
        auto_disable_after_days=settings.auto_disable_after_days,
        schedules_auto_disabled=settings.schedules_auto_disabled,
        auto_disabled_at=settings.auto_disabled_at,
        days_until_auto_disable=days_remaining,
    )


@router.put("/settings", response_model=ClientStatusResponse, dependencies=[Depends(verify_api_key)])
async def update_client_settings(
    request: SettingsUpdateRequest,
) -> ClientStatusResponse:
    """
    Update client settings.

    Configure auto-disable behavior:
    - auto_disable_enabled: Turn auto-disable on/off
    - auto_disable_after_days: Set inactivity threshold (1-365 days)
    """
    settings = activity_tracker.update_settings(
        auto_disable_enabled=request.auto_disable_enabled,
        auto_disable_after_days=request.auto_disable_after_days,
    )
    days_remaining = activity_tracker.get_days_until_auto_disable()

    return ClientStatusResponse(
        last_heartbeat_at=settings.last_heartbeat_at,
        last_download_at=settings.last_download_at,
        last_feed_sync_at=settings.last_feed_sync_at,
        auto_disable_enabled=settings.auto_disable_enabled,
        auto_disable_after_days=settings.auto_disable_after_days,
        schedules_auto_disabled=settings.schedules_auto_disabled,
        auto_disabled_at=settings.auto_disabled_at,
        days_until_auto_disable=days_remaining,
    )


@router.post("/reactivate", response_model=HeartbeatResponse, dependencies=[Depends(verify_api_key)])
async def reactivate_schedules() -> HeartbeatResponse:
    """
    Reactivate schedules that were auto-disabled.

    This is equivalent to sending a heartbeat - it records activity and
    re-enables all schedules.
    """
    settings = activity_tracker.record_heartbeat()

    return HeartbeatResponse(
        status="ok",
        received_at=settings.last_heartbeat_at,
        schedules_active=not settings.schedules_auto_disabled,
        message="Schedules reactivated" if not settings.schedules_auto_disabled else None,
    )
