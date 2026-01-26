"""Client configuration endpoints for settings sync."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.core.database import get_session
from app.core.security import verify_api_key
from app.models.client_config import ClientConfig, ClientConfigRead, ClientConfigUpdate
from app.worker import scheduler as scheduler_module

router = APIRouter()
logger = logging.getLogger(__name__)


class ConfigResponse(BaseModel):
    """Response model for client configuration."""

    min_word_count: int
    morning_hour: int
    morning_minute: int
    noon_hour: int
    noon_minute: int
    evening_hour: int
    evening_minute: int
    timezone: str
    updated_at: datetime


class ConfigUpdateRequest(BaseModel):
    """Request to update client configuration."""

    min_word_count: int | None = Field(default=None, ge=0, description="Minimum word count filter")
    morning_hour: int | None = Field(default=None, ge=0, le=23, description="Morning hour (24h)")
    morning_minute: int | None = Field(default=None, ge=0, le=59, description="Morning minute")
    noon_hour: int | None = Field(default=None, ge=0, le=23, description="Noon hour (24h)")
    noon_minute: int | None = Field(default=None, ge=0, le=59, description="Noon minute")
    evening_hour: int | None = Field(default=None, ge=0, le=23, description="Evening hour (24h)")
    evening_minute: int | None = Field(default=None, ge=0, le=59, description="Evening minute")
    timezone: str | None = Field(default=None, description="IANA timezone")
    # Client's updated_at for conflict detection
    client_updated_at: datetime | None = Field(default=None, description="Client's last known updated_at")


def get_or_create_config(session: Session) -> ClientConfig:
    """Get the singleton config or create it with defaults."""
    config = session.exec(select(ClientConfig)).first()
    if config is None:
        config = ClientConfig()
        session.add(config)
        session.commit()
        session.refresh(config)
        logger.info("Created default client configuration")
    return config


def _config_to_response(config: ClientConfig) -> ConfigResponse:
    """Convert a ClientConfig to a response model."""
    return ConfigResponse(
        min_word_count=config.min_word_count,
        morning_hour=config.morning_hour,
        morning_minute=config.morning_minute,
        noon_hour=config.noon_hour,
        noon_minute=config.noon_minute,
        evening_hour=config.evening_hour,
        evening_minute=config.evening_minute,
        timezone=config.timezone,
        updated_at=config.updated_at,
    )


@router.get("", response_model=ConfigResponse, dependencies=[Depends(verify_api_key)])
async def get_config(session: Session = Depends(get_session)) -> ConfigResponse:
    """
    Get the current shared client configuration.

    Returns all synced settings with an updated_at timestamp for
    conflict detection during sync.
    """
    config = get_or_create_config(session)
    return _config_to_response(config)


@router.put("", response_model=ConfigResponse, dependencies=[Depends(verify_api_key)])
async def update_config(
    request: ConfigUpdateRequest,
    session: Session = Depends(get_session),
) -> ConfigResponse:
    """
    Update the shared client configuration.

    Only provided fields are updated; others remain unchanged.
    Also updates the corresponding schedule times if schedule fields are provided.

    Conflict detection: If client_updated_at is provided and doesn't match
    the server's updated_at, a 409 Conflict is returned.
    """
    config = get_or_create_config(session)

    # Check for conflicts if client provided their last known timestamp
    if request.client_updated_at is not None:
        # Allow 1 second tolerance for timestamp comparison
        server_ts = config.updated_at.replace(tzinfo=timezone.utc)
        client_ts = request.client_updated_at.replace(tzinfo=timezone.utc)
        diff = abs((server_ts - client_ts).total_seconds())
        if diff > 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "Configuration was modified by another client",
                    "server_updated_at": config.updated_at.isoformat(),
                    "client_updated_at": request.client_updated_at.isoformat(),
                },
            )

    # Track which schedule times changed for scheduler update
    schedule_updates = {}

    # Update config fields
    if request.min_word_count is not None:
        config.min_word_count = request.min_word_count

    if request.morning_hour is not None:
        config.morning_hour = request.morning_hour
        schedule_updates.setdefault("morning", {})["hour"] = request.morning_hour
    if request.morning_minute is not None:
        config.morning_minute = request.morning_minute
        schedule_updates.setdefault("morning", {})["minute"] = request.morning_minute

    if request.noon_hour is not None:
        config.noon_hour = request.noon_hour
        schedule_updates.setdefault("noon", {})["hour"] = request.noon_hour
    if request.noon_minute is not None:
        config.noon_minute = request.noon_minute
        schedule_updates.setdefault("noon", {})["minute"] = request.noon_minute

    if request.evening_hour is not None:
        config.evening_hour = request.evening_hour
        schedule_updates.setdefault("evening", {})["hour"] = request.evening_hour
    if request.evening_minute is not None:
        config.evening_minute = request.evening_minute
        schedule_updates.setdefault("evening", {})["minute"] = request.evening_minute

    if request.timezone is not None:
        config.timezone = request.timezone
        # Apply timezone to all schedules
        for period in ["morning", "noon", "evening"]:
            schedule_updates.setdefault(period, {})["timezone"] = request.timezone

    # Update timestamp
    config.updated_at = datetime.now(timezone.utc)

    session.add(config)
    session.commit()
    session.refresh(config)

    # Update scheduler for any changed schedule times
    for period, updates in schedule_updates.items():
        scheduler_module.update_schedule(
            period=period,
            hour=updates.get("hour"),
            minute=updates.get("minute"),
            timezone=updates.get("timezone"),
        )
        logger.info(f"Updated schedule {period} from config sync: {updates}")

    logger.info(f"Updated client configuration: {request.model_dump(exclude_none=True)}")
    return _config_to_response(config)
