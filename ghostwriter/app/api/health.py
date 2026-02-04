"""Health and system status endpoints."""

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session, func, select

from app import __version__
from app.core.config import Settings, get_settings
from app.core.database import get_session
from app.models.digest import Digest
from app.services.llm_service import LLMService
from app.services.newsletter_service import NewsletterService
from app.services.wallabag_service import WallabagService
from app.worker import scheduler as scheduler_module

router = APIRouter()


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str
    uptime_seconds: int | None = None
    last_successful_digest: str | None = None
    ai_provider: str
    ai_model: str
    ai_status: str | None = None


class IntegrationStatus(BaseModel):
    """Status of an external integration."""

    enabled: bool
    label: str | None = None  # For newsletters, the Gmail label


class ConfigResponse(BaseModel):
    """Configuration response."""

    timezone: str
    ai_provider: str
    ai_model: str
    schedule_enabled: bool
    schedule_morning: str
    schedule_noon: str
    schedule_evening: str
    digest_retention_days: int
    max_articles_per_digest: int
    # Integrations
    wallabag: IntegrationStatus | None = None
    newsletters: IntegrationStatus | None = None


# Track startup time
_startup_time: datetime | None = None


def set_startup_time(time: datetime) -> None:
    """Set the application startup time."""
    global _startup_time
    _startup_time = time


@router.get("/health", response_model=HealthResponse)
async def health_check(
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> HealthResponse:
    """
    Check service health and status.

    Returns basic health information including version, uptime,
    and AI provider status. This endpoint does not require authentication.
    """
    # Calculate uptime
    uptime = None
    if _startup_time:
        uptime = int((datetime.utcnow() - _startup_time).total_seconds())

    # Get last successful digest
    last_digest = None
    statement = (
        select(Digest)
        .where(Digest.status == "completed")
        .order_by(Digest.completed_at.desc())
        .limit(1)
    )
    result = session.exec(statement).first()
    if result and result.completed_at:
        last_digest = result.completed_at.isoformat()

    return HealthResponse(
        status="healthy",
        version=__version__,
        uptime_seconds=uptime,
        last_successful_digest=last_digest,
        ai_provider=settings.ai_provider,
        ai_model=settings.get_llm_model_string(),
    )


@router.get("/health/config", response_model=ConfigResponse)
async def get_config(
    settings: Settings = Depends(get_settings),
) -> ConfigResponse:
    """
    Get current service configuration.

    Returns schedule settings, AI configuration, retention policies,
    and integration status. Does not require authentication.
    """
    # Check integration status
    wallabag_service = WallabagService(settings)
    newsletter_service = NewsletterService(settings)

    wallabag_status = IntegrationStatus(enabled=wallabag_service.is_configured)
    newsletter_status = IntegrationStatus(
        enabled=newsletter_service.is_configured,
        label=settings.gmail_label if newsletter_service.is_configured else None,
    )

    # Read schedule times from database (Schedule table) so they reflect
    # changes made via the web UI, falling back to env var defaults
    schedules = {s.period: s for s in scheduler_module.get_all_schedules()}
    morning = schedules.get("morning")
    noon = schedules.get("noon")
    evening = schedules.get("evening")

    return ConfigResponse(
        timezone=morning.timezone if morning else settings.timezone,
        ai_provider=settings.ai_provider,
        ai_model=settings.get_llm_model_string(),
        schedule_enabled=settings.schedule_enabled,
        schedule_morning=f"{morning.hour:02d}:{morning.minute:02d}" if morning else settings.schedule_morning,
        schedule_noon=f"{noon.hour:02d}:{noon.minute:02d}" if noon else settings.schedule_noon,
        schedule_evening=f"{evening.hour:02d}:{evening.minute:02d}" if evening else settings.schedule_evening,
        digest_retention_days=settings.digest_retention_days,
        max_articles_per_digest=settings.max_articles_per_digest,
        wallabag=wallabag_status,
        newsletters=newsletter_status,
    )
