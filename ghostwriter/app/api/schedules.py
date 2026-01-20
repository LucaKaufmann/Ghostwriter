"""Schedule management endpoints."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.security import verify_api_key
from app.models.schedule import ScheduleRead, ScheduleUpdate
from app.worker import scheduler as scheduler_module
from app.worker.bindery import generate_digest

router = APIRouter()


class ScheduleResponse(BaseModel):
    """Response model for a schedule."""

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
    next_run_at: datetime | None


class ScheduleUpdateRequest(BaseModel):
    """Request to update a schedule."""

    hour: int | None = Field(default=None, ge=0, le=23, description="Hour in 24h format")
    minute: int | None = Field(default=None, ge=0, le=59, description="Minute")
    enabled: bool | None = Field(default=None, description="Whether this schedule is active")
    timezone: str | None = Field(default=None, description="IANA timezone identifier")


class TriggerScheduleResponse(BaseModel):
    """Response from triggering a schedule."""

    id: UUID | None
    status: str
    message: str


def _schedule_to_response(schedule) -> ScheduleResponse:
    """Convert a Schedule model to a response with computed next_run_at."""
    next_run = scheduler_module.get_next_run_time(schedule)
    return ScheduleResponse(
        id=schedule.id,
        period=schedule.period,
        hour=schedule.hour,
        minute=schedule.minute,
        enabled=schedule.enabled,
        timezone=schedule.timezone,
        created_at=schedule.created_at,
        updated_at=schedule.updated_at,
        last_run_at=schedule.last_run_at,
        last_run_digest_id=schedule.last_run_digest_id,
        next_run_at=next_run,
    )


@router.get("", response_model=list[ScheduleResponse], dependencies=[Depends(verify_api_key)])
async def list_schedules() -> list[ScheduleResponse]:
    """
    List all schedule configurations.

    Returns all three schedules (morning, noon, evening) with their
    current configuration and next run times.
    """
    schedules = scheduler_module.get_all_schedules()
    return [_schedule_to_response(s) for s in schedules]


@router.get("/{period}", response_model=ScheduleResponse, dependencies=[Depends(verify_api_key)])
async def get_schedule(
    period: Literal["morning", "noon", "evening"],
) -> ScheduleResponse:
    """
    Get a specific schedule by period.

    Returns the schedule configuration and next run time.
    """
    schedule = scheduler_module.get_schedule(period)

    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule for period '{period}' not found",
        )

    return _schedule_to_response(schedule)


@router.put("/{period}", response_model=ScheduleResponse, dependencies=[Depends(verify_api_key)])
async def update_schedule(
    period: Literal["morning", "noon", "evening"],
    request: ScheduleUpdateRequest,
) -> ScheduleResponse:
    """
    Update a schedule configuration.

    Changes take effect immediately - the APScheduler job is reconfigured.
    Only provided fields are updated; others remain unchanged.
    """
    schedule = scheduler_module.update_schedule(
        period=period,
        hour=request.hour,
        minute=request.minute,
        enabled=request.enabled,
        timezone=request.timezone,
    )

    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule for period '{period}' not found",
        )

    return _schedule_to_response(schedule)


@router.post("/{period}/trigger", response_model=TriggerScheduleResponse, dependencies=[Depends(verify_api_key)])
async def trigger_schedule(
    period: Literal["morning", "noon", "evening"],
) -> TriggerScheduleResponse:
    """
    Manually trigger a scheduled digest immediately.

    This runs the digest generation for the specified period without
    waiting for the scheduled time. Useful for testing.

    Returns 409 Conflict if a digest job is already running.
    """
    schedule = scheduler_module.get_schedule(period)

    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule for period '{period}' not found",
        )

    # Trigger digest generation
    digest_id = await generate_digest(period)

    if digest_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A digest job is already running. Please wait for it to complete.",
        )

    return TriggerScheduleResponse(
        id=digest_id,
        status="started",
        message=f"Digest generation triggered for period: {period}",
    )


@router.post("/{period}/enable", response_model=ScheduleResponse, dependencies=[Depends(verify_api_key)])
async def enable_schedule(
    period: Literal["morning", "noon", "evening"],
) -> ScheduleResponse:
    """
    Enable a schedule.

    Shortcut for setting enabled=true.
    """
    schedule = scheduler_module.update_schedule(period=period, enabled=True)

    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule for period '{period}' not found",
        )

    return _schedule_to_response(schedule)


@router.post("/{period}/disable", response_model=ScheduleResponse, dependencies=[Depends(verify_api_key)])
async def disable_schedule(
    period: Literal["morning", "noon", "evening"],
) -> ScheduleResponse:
    """
    Disable a schedule.

    Shortcut for setting enabled=false. The scheduled job will not run
    until re-enabled.
    """
    schedule = scheduler_module.update_schedule(period=period, enabled=False)

    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule for period '{period}' not found",
        )

    return _schedule_to_response(schedule)
