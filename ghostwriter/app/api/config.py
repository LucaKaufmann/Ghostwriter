"""Client configuration endpoints for settings sync."""

import logging
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from sqlmodel import delete as sql_delete

from app.core.database import get_session
from app.core.security import verify_api_key
from app.models.client_config import ClientConfig, ClientConfigRead, ClientConfigUpdate
from app.models.feed import Feed
from app.models.seen_article import SeenArticle
from app.models.wallabag_config import WallabagConfig, WallabagConfigRead, WallabagConfigUpdate
from app.services.newsletter_service import NewsletterService
from app.services.whisper_model_service import WhisperModelService
from app.services.whisper_models import WHISPER_MODELS
from app.services.wallabag_service import WallabagService
from app.worker import scheduler as scheduler_module
from app.core.config import Settings, get_settings

router = APIRouter()
logger = logging.getLogger(__name__)


class IntegrationStatus(BaseModel):
    """Status of an external integration."""

    enabled: bool
    label: str | None = None  # For newsletters, the Gmail label


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
    whisper_provider: str
    whisper_model: str
    whisper_timeout_minutes: int
    # Media processing
    media_processing_interval_hours: int
    include_podcasts_in_digest: bool
    include_youtube_in_digest: bool
    # Integration status
    wallabag: IntegrationStatus | None = None
    newsletters: IntegrationStatus | None = None


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
    newsletters_enabled: bool | None = Field(default=None, description="Enable newsletter integration")
    whisper_provider: str | None = Field(
        default=None, description="Transcription provider: local, openai, auto"
    )
    whisper_model: str | None = Field(
        default=None, description="whisper.cpp model name for local transcription"
    )
    whisper_timeout_minutes: int | None = Field(
        default=None, ge=1, le=120, description="Transcription timeout in minutes"
    )
    media_processing_interval_hours: int | None = Field(
        default=None, ge=1, le=24, description="Hours between media processing runs"
    )
    include_podcasts_in_digest: bool | None = Field(
        default=None, description="Include completed podcast transcripts in digests"
    )
    include_youtube_in_digest: bool | None = Field(
        default=None, description="Include completed YouTube transcripts in digests"
    )
    # Client's updated_at for conflict detection
    client_updated_at: datetime | None = Field(default=None, description="Client's last known updated_at")


class WhisperModelInfo(BaseModel):
    """Information about a whisper.cpp model."""

    name: str
    filename: str
    downloaded: bool
    size_bytes: int | None = None
    status: Literal["not_downloaded", "downloading", "downloaded", "failed"]
    bytes_downloaded: int | None = None
    total_bytes: int | None = None
    error: str | None = None


class WhisperModelsResponse(BaseModel):
    """Response model for whisper.cpp model management."""

    active_model: str
    models: list[WhisperModelInfo]


class WhisperModelRequest(BaseModel):
    """Request for whisper.cpp model actions."""

    model: str


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


def _get_wallabag_enabled(session: Session | None) -> bool:
    """Check if Wallabag integration is enabled in its config."""
    if not session:
        return True
    wb_config = session.exec(select(WallabagConfig)).first()
    return wb_config.enabled if wb_config else True


def _config_to_response(config: ClientConfig, session: Session | None = None) -> ConfigResponse:
    """Convert a ClientConfig to a response model."""
    settings = get_settings()
    if session:
        wallabag_service = WallabagService.from_db_or_settings(session, settings)
    else:
        wallabag_service = WallabagService(settings)
    newsletter_service = NewsletterService(settings)

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
        whisper_provider=config.whisper_provider,
        whisper_model=config.whisper_model,
        whisper_timeout_minutes=config.whisper_timeout_minutes,
        media_processing_interval_hours=config.media_processing_interval_hours,
        include_podcasts_in_digest=config.include_podcasts_in_digest,
        include_youtube_in_digest=config.include_youtube_in_digest,
        wallabag=IntegrationStatus(
            enabled=wallabag_service.is_configured and _get_wallabag_enabled(session),
        ),
        newsletters=IntegrationStatus(
            enabled=newsletter_service.is_configured and config.newsletters_enabled,
            label=settings.gmail_label if newsletter_service.is_configured else None,
        ),
    )


@router.get("", response_model=ConfigResponse, dependencies=[Depends(verify_api_key)])
async def get_config(session: Session = Depends(get_session)) -> ConfigResponse:
    """
    Get the current shared client configuration.

    Returns all synced settings with an updated_at timestamp for
    conflict detection during sync.
    """
    config = get_or_create_config(session)
    return _config_to_response(config, session)


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

    if request.newsletters_enabled is not None:
        config.newsletters_enabled = request.newsletters_enabled

    if request.whisper_provider is not None:
        if request.whisper_provider not in ("local", "openai", "auto"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="whisper_provider must be 'local', 'openai', or 'auto'",
            )
        config.whisper_provider = request.whisper_provider

    if request.whisper_model is not None:
        if request.whisper_model not in WHISPER_MODELS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unknown whisper model",
            )
        service = WhisperModelService(get_settings())
        if not service.is_downloaded(request.whisper_model):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Model must be downloaded before activation",
            )
        config.whisper_model = request.whisper_model

    if request.whisper_timeout_minutes is not None:
        config.whisper_timeout_minutes = request.whisper_timeout_minutes

    if request.include_podcasts_in_digest is not None:
        config.include_podcasts_in_digest = request.include_podcasts_in_digest

    if request.include_youtube_in_digest is not None:
        config.include_youtube_in_digest = request.include_youtube_in_digest

    if request.media_processing_interval_hours is not None:
        config.media_processing_interval_hours = request.media_processing_interval_hours

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

    # Update media processing interval if changed
    if request.media_processing_interval_hours is not None:
        scheduler_module.update_media_processing_interval(
            request.media_processing_interval_hours
        )

    logger.info(f"Updated client configuration: {request.model_dump(exclude_none=True)}")
    return _config_to_response(config, session)


# ============ Whisper Model Management ============


@router.get(
    "/whisper/models",
    response_model=WhisperModelsResponse,
    dependencies=[Depends(verify_api_key)],
)
async def list_whisper_models(
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> WhisperModelsResponse:
    """List whisper.cpp models and download status."""
    config = get_or_create_config(session)
    service = WhisperModelService(settings)
    return WhisperModelsResponse(
        active_model=config.whisper_model or "base.en",
        models=service.list_models(),
    )


@router.post(
    "/whisper/models/download",
    response_model=WhisperModelsResponse,
    dependencies=[Depends(verify_api_key)],
)
async def download_whisper_model(
    request: WhisperModelRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> WhisperModelsResponse:
    """Start a whisper.cpp model download."""
    if request.model not in WHISPER_MODELS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown whisper model"
        )
    service = WhisperModelService(settings)
    if service.is_downloading(request.model):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Model download already in progress",
        )
    background_tasks.add_task(service.download_model, request.model)
    config = get_or_create_config(session)
    return WhisperModelsResponse(
        active_model=config.whisper_model or "base.en",
        models=service.list_models(),
    )


@router.delete(
    "/whisper/models/{model_name}",
    response_model=WhisperModelsResponse,
    dependencies=[Depends(verify_api_key)],
)
async def delete_whisper_model(
    model_name: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> WhisperModelsResponse:
    """Delete a downloaded whisper.cpp model."""
    if model_name not in WHISPER_MODELS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown whisper model"
        )
    service = WhisperModelService(settings)
    try:
        service.delete_model(model_name)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    config = get_or_create_config(session)
    return WhisperModelsResponse(
        active_model=config.whisper_model or "base.en",
        models=service.list_models(),
    )


@router.put(
    "/whisper/models/active",
    response_model=WhisperModelsResponse,
    dependencies=[Depends(verify_api_key)],
)
async def set_active_whisper_model(
    request: WhisperModelRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> WhisperModelsResponse:
    """Set the active whisper.cpp model."""
    if request.model not in WHISPER_MODELS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown whisper model"
        )
    service = WhisperModelService(settings)
    if not service.is_downloaded(request.model):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Model must be downloaded before activation",
        )
    config = get_or_create_config(session)
    config.whisper_model = request.model
    config.updated_at = datetime.now(timezone.utc)
    session.add(config)
    session.commit()
    return WhisperModelsResponse(
        active_model=config.whisper_model or "base.en",
        models=service.list_models(),
    )


# ============ Wallabag Configuration ============

PASSWORD_MASK = "\u2022\u2022\u2022\u2022\u2022\u2022"


def _get_or_create_wallabag_config(session: Session) -> WallabagConfig:
    """Get the singleton Wallabag config or create it with defaults."""
    config = session.exec(select(WallabagConfig)).first()
    if config is None:
        config = WallabagConfig()
        session.add(config)
        session.commit()
        session.refresh(config)
    return config


def _wallabag_config_to_read(config: WallabagConfig) -> WallabagConfigRead:
    """Convert DB model to response with masked password."""
    return WallabagConfigRead(
        url=config.url,
        client_id=config.client_id,
        client_secret=PASSWORD_MASK if config.client_secret else "",
        username=config.username,
        password=PASSWORD_MASK if config.password else "",
        mode=config.mode,
        max_articles=config.max_articles,
        tag_on_process=config.tag_on_process,
        enabled=config.enabled,
    )


@router.get("/wallabag", response_model=WallabagConfigRead, dependencies=[Depends(verify_api_key)])
async def get_wallabag_config(session: Session = Depends(get_session)) -> WallabagConfigRead:
    """Get the Wallabag integration configuration (password masked)."""
    config = _get_or_create_wallabag_config(session)
    return _wallabag_config_to_read(config)


@router.put("/wallabag", response_model=WallabagConfigRead, dependencies=[Depends(verify_api_key)])
async def update_wallabag_config(
    request: WallabagConfigUpdate,
    session: Session = Depends(get_session),
) -> WallabagConfigRead:
    """Update Wallabag configuration. Empty string clears a field. Password sentinel skips update."""
    config = _get_or_create_wallabag_config(session)

    if request.enabled is not None:
        config.enabled = request.enabled

    for field_name in ["url", "client_id", "client_secret", "username", "mode", "tag_on_process"]:
        value = getattr(request, field_name, None)
        if value is not None:
            setattr(config, field_name, value)

    # Password: skip if sentinel, otherwise update
    if request.password is not None and request.password != PASSWORD_MASK:
        config.password = request.password

    if request.max_articles is not None:
        config.max_articles = request.max_articles

    # Validate URL format if provided
    if config.url and not config.url.startswith(("http://", "https://")):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Wallabag URL must start with http:// or https://",
        )

    config.updated_at = datetime.now(timezone.utc)
    session.add(config)
    session.commit()
    session.refresh(config)

    logger.info("Updated Wallabag configuration")
    return _wallabag_config_to_read(config)


class WallabagTestResult(BaseModel):
    status: str
    detail: str | None = None


class PreviewArticle(BaseModel):
    title: str
    url: str
    author: str | None = None
    word_count: int | None = None


class PreviewResponse(BaseModel):
    status: str  # "ok" | "error"
    detail: str | None = None
    count: int = 0
    articles: list[PreviewArticle] = []


@router.post("/wallabag/test", response_model=WallabagTestResult, dependencies=[Depends(verify_api_key)])
async def test_wallabag_connection(
    session: Session = Depends(get_session),
) -> WallabagTestResult:
    """Test Wallabag connection by attempting OAuth token fetch."""
    service = WallabagService.from_db_or_settings(session)
    if not service.is_configured:
        return WallabagTestResult(status="error", detail="Wallabag is not fully configured")

    try:
        await service._ensure_token()
        return WallabagTestResult(status="ok")
    except Exception as e:
        return WallabagTestResult(status="error", detail=str(e))


@router.post("/wallabag/preview", response_model=PreviewResponse, dependencies=[Depends(verify_api_key)])
async def preview_wallabag(
    session: Session = Depends(get_session),
) -> PreviewResponse:
    """Preview unread Wallabag articles without archiving or tagging."""
    service = WallabagService.from_db_or_settings(session)
    if not service.is_configured:
        return PreviewResponse(status="error", detail="Wallabag is not configured")

    try:
        articles = await service.fetch_unread_articles()
        preview_articles = [
            PreviewArticle(
                title=a.get("title", "Untitled"),
                url=a.get("url", ""),
                author=a.get("domain_name"),
                word_count=len(a.get("content", "").split()) if a.get("content") else None,
            )
            for a in articles
        ]
        return PreviewResponse(status="ok", count=len(preview_articles), articles=preview_articles)
    except Exception as e:
        logger.error(f"Wallabag preview failed: {e}")
        return PreviewResponse(status="error", detail=str(e))


def _clear_seen_for_synthetic_feed(session: Session, synthetic_url: str) -> int:
    """Delete seen_articles rows for a synthetic feed, returning count deleted."""
    feed = session.exec(select(Feed).where(Feed.url == synthetic_url)).first()
    if not feed:
        return 0
    result = session.exec(
        sql_delete(SeenArticle).where(SeenArticle.feed_id == feed.id)
    )
    session.commit()
    return result.rowcount  # type: ignore[union-attr]


@router.post("/wallabag/clear-seen", dependencies=[Depends(verify_api_key)])
async def clear_wallabag_seen(session: Session = Depends(get_session)) -> dict:
    """Clear seen-article history for Wallabag integration."""
    cleared = _clear_seen_for_synthetic_feed(session, "synthetic://wallabag")
    logger.info(f"Cleared {cleared} Wallabag seen articles")
    return {"cleared": cleared}


@router.post("/newsletters/clear-seen", dependencies=[Depends(verify_api_key)])
async def clear_newsletter_seen(session: Session = Depends(get_session)) -> dict:
    """Clear seen-article history for Newsletter integration."""
    cleared = _clear_seen_for_synthetic_feed(session, "synthetic://newsletter")
    logger.info(f"Cleared {cleared} Newsletter seen articles")
    return {"cleared": cleared}
