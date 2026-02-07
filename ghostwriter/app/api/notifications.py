"""Push notification device registration endpoints."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.core.database import get_session
from app.core.security import get_current_user
from app.models.push_device import PushDevice, PushDeviceRead, PushDeviceRegister
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("/devices", response_model=list[PushDeviceRead])
async def list_devices(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Session = Depends(get_session),
) -> list[PushDevice]:
    """List push notification devices registered for the current user."""
    statement = (
        select(PushDevice)
        .where(PushDevice.user_id == current_user.id)
        .order_by(PushDevice.updated_at.desc())
    )
    return list(session.exec(statement).all())


@router.post("/devices", response_model=PushDeviceRead)
async def register_device(
    payload: PushDeviceRegister,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Session = Depends(get_session),
) -> PushDevice:
    """Register or update a device token for push notifications."""
    if not payload.device_id.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="device_id is required")
    if not payload.token.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="token is required")

    now = datetime.utcnow()

    existing = session.exec(
        select(PushDevice)
        .where(PushDevice.user_id == current_user.id)
        .where(PushDevice.device_id == payload.device_id)
    ).first()

    if existing:
        existing.platform = payload.platform
        existing.token = payload.token
        existing.enabled = True
        existing.disabled_at = None
        existing.app_version = payload.app_version
        existing.device_model = payload.device_model
        existing.last_seen_at = now
        existing.updated_at = now
        existing.failure_count = 0
        existing.last_error = None
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing

    device = PushDevice(
        user_id=current_user.id,
        device_id=payload.device_id,
        platform=payload.platform,
        token=payload.token,
        enabled=True,
        disabled_at=None,
        app_version=payload.app_version,
        device_model=payload.device_model,
        last_seen_at=now,
        created_at=now,
        updated_at=now,
        failure_count=0,
        last_error=None,
    )
    session.add(device)
    try:
        session.commit()
    except Exception as e:
        session.rollback()
        logger.exception("Failed to register device", extra={"error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to register device",
        ) from e
    session.refresh(device)
    return device


@router.delete("/devices/{device_id}")
async def unregister_device(
    device_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Session = Depends(get_session),
) -> dict:
    """Disable push notifications for a device (idempotent)."""
    existing = session.exec(
        select(PushDevice)
        .where(PushDevice.user_id == current_user.id)
        .where(PushDevice.device_id == device_id)
    ).first()

    if not existing:
        return {"status": "ok", "message": "Device not registered"}

    now = datetime.utcnow()
    existing.enabled = False
    existing.disabled_at = now
    existing.updated_at = now
    session.add(existing)
    session.commit()
    return {"status": "ok"}

