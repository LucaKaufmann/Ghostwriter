"""Client configuration endpoints for settings sync."""

import base64
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from sqlmodel import delete as sql_delete

from app.core.database import get_session
from app.core.security import verify_api_key
from app.models.client_config import ClientConfig, ClientConfigRead, ClientConfigUpdate
from app.models.feed import Feed
from app.models.manual_cover import ManualCover
from app.models.seen_article import SeenArticle
from app.models.wallabag_config import WallabagConfig, WallabagConfigRead, WallabagConfigUpdate
from app.services.cover_image_service import CoverImageService
from app.services.newsletter_service import NewsletterService
from app.services.whisper_model_service import WhisperModelService
from app.services.whisper_models import WHISPER_MODELS
from app.services.wallabag_service import WallabagService
from app.worker import scheduler as scheduler_module
from app.core.config import Settings, get_settings

router = APIRouter()
logger = logging.getLogger(__name__)
SECRET_MASK = "\u2022\u2022\u2022\u2022\u2022\u2022"


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
    pdf_enabled: bool
    pdf_page_size: str
    # Cover generation
    cover_enabled: bool
    cover_provider: str
    cover_quality: str
    cover_prompt: str
    cover_overlay_enabled: bool
    cover_openai_api_key: str
    cover_gemini_api_key: str
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
    pdf_enabled: bool | None = Field(
        default=None, description="Enable PDF digest generation/download"
    )
    pdf_page_size: str | None = Field(
        default=None, description="Default PDF page size: A4, Letter, or A5"
    )
    cover_enabled: bool | None = Field(
        default=None,
        description="Generate an AI cover image for each digest",
    )
    cover_provider: str | None = Field(
        default=None,
        description="Cover provider: gpt-image-1 or nano-banana",
    )
    cover_quality: str | None = Field(
        default=None,
        description="Cover quality tier for gpt-image-1: low, medium, high",
    )
    cover_prompt: str | None = Field(
        default=None,
        description="Optional additional prompt text for cover generation",
    )
    cover_overlay_enabled: bool | None = Field(
        default=None,
        description="Overlay deterministic metadata (title, date, sources) on AI-generated covers",
    )
    cover_openai_api_key: str | None = Field(
        default=None,
        description="Dedicated OpenAI API key for cover generation. Empty string clears value.",
    )
    cover_gemini_api_key: str | None = Field(
        default=None,
        description="Dedicated Gemini API key for cover generation. Empty string clears value.",
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


class ManualCoverRead(BaseModel):
    """A single manual cover item for settings UI."""

    id: str
    name: str
    media_type: str
    size_bytes: int
    is_active: bool
    created_at: datetime
    preview_data_url: str


class ManualCoversResponse(BaseModel):
    """Response model for manual cover list."""

    covers: list[ManualCoverRead]


def _manual_cover_dir(settings: Settings) -> Path:
    path = Path(settings.data_dir) / "manual_covers"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _manual_cover_to_read(cover: ManualCover, settings: Settings) -> ManualCoverRead:
    file_path = _manual_cover_dir(settings) / cover.file_name
    preview_data_url = ""
    try:
        if file_path.exists():
            encoded = base64.b64encode(file_path.read_bytes()).decode("utf-8")
            preview_data_url = f"data:{cover.media_type};base64,{encoded}"
    except Exception:
        logger.exception("Failed reading manual cover preview for %s", cover.id)

    return ManualCoverRead(
        id=str(cover.id),
        name=cover.name,
        media_type=cover.media_type,
        size_bytes=cover.size_bytes,
        is_active=cover.is_active,
        created_at=cover.created_at,
        preview_data_url=preview_data_url,
    )


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
        pdf_enabled=config.pdf_enabled,
        pdf_page_size=config.pdf_page_size,
        cover_enabled=config.cover_enabled,
        cover_provider=config.cover_provider,
        cover_quality=config.cover_quality,
        cover_prompt=config.cover_prompt,
        cover_overlay_enabled=config.cover_overlay_enabled,
        cover_openai_api_key=SECRET_MASK if config.cover_openai_api_key else "",
        cover_gemini_api_key=SECRET_MASK if config.cover_gemini_api_key else "",
        wallabag=IntegrationStatus(
            enabled=wallabag_service.is_configured and _get_wallabag_enabled(session),
        ),
        newsletters=IntegrationStatus(
            enabled=newsletter_service.is_configured and config.newsletters_enabled,
            label=settings.gmail_label if newsletter_service.is_configured else None,
        ),
    )


@router.get("/covers", response_model=ManualCoversResponse, dependencies=[Depends(verify_api_key)])
async def list_manual_covers(
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> ManualCoversResponse:
    """List uploaded manual digest covers."""
    covers = session.exec(
        select(ManualCover).order_by(ManualCover.created_at.desc())
    ).all()
    return ManualCoversResponse(
        covers=[_manual_cover_to_read(cover, settings) for cover in covers]
    )


@router.post("/covers/upload", response_model=ManualCoverRead, dependencies=[Depends(verify_api_key)])
async def upload_manual_cover(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> ManualCoverRead:
    """Upload and normalize a manual digest cover image."""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only image uploads are supported",
        )

    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty",
        )
    if len(raw_bytes) > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Uploaded file is too large (max 10MB)",
        )

    cover_service = CoverImageService(settings)
    normalized = cover_service.normalize_for_epub(
        data=raw_bytes,
        media_type=file.content_type,
        provider="manual-upload",
    )
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not process uploaded image",
        )

    cover_id = uuid4()
    ext = cover_service.extension_for_media_type(normalized.media_type)
    stored_file_name = f"{cover_id}.{ext}"
    target_path = _manual_cover_dir(settings) / stored_file_name
    target_path.write_bytes(normalized.data)

    has_active = session.exec(
        select(ManualCover).where(ManualCover.is_active == True)
    ).first()
    cover = ManualCover(
        id=cover_id,
        name=(file.filename or "Manual Cover").strip() or "Manual Cover",
        file_name=stored_file_name,
        media_type=normalized.media_type,
        size_bytes=len(normalized.data),
        is_active=has_active is None,
    )
    session.add(cover)
    session.commit()
    session.refresh(cover)
    return _manual_cover_to_read(cover, settings)


@router.post("/covers/{cover_id}/activate", response_model=ManualCoverRead, dependencies=[Depends(verify_api_key)])
async def activate_manual_cover(
    cover_id: UUID,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> ManualCoverRead:
    """Set a manual cover as the active one."""
    cover = session.get(ManualCover, cover_id)
    if not cover:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cover not found")

    current_active = session.exec(
        select(ManualCover).where(ManualCover.is_active == True)
    ).all()
    for row in current_active:
        if row.id != cover.id:
            row.is_active = False
            row.updated_at = datetime.now(timezone.utc)
            session.add(row)

    cover.is_active = True
    cover.updated_at = datetime.now(timezone.utc)
    session.add(cover)
    session.commit()
    session.refresh(cover)
    return _manual_cover_to_read(cover, settings)


@router.delete("/covers/{cover_id}", response_model=ManualCoversResponse, dependencies=[Depends(verify_api_key)])
async def delete_manual_cover(
    cover_id: UUID,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> ManualCoversResponse:
    """Delete a manual cover and return remaining covers."""
    cover = session.get(ManualCover, cover_id)
    if not cover:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cover not found")

    was_active = cover.is_active
    file_path = _manual_cover_dir(settings) / cover.file_name
    session.delete(cover)
    session.commit()

    if file_path.exists():
        try:
            file_path.unlink()
        except Exception:
            logger.exception("Failed to remove manual cover file: %s", file_path)

    if was_active:
        next_cover = session.exec(
            select(ManualCover).order_by(ManualCover.created_at.desc())
        ).first()
        if next_cover:
            next_cover.is_active = True
            next_cover.updated_at = datetime.now(timezone.utc)
            session.add(next_cover)
            session.commit()

    covers = session.exec(
        select(ManualCover).order_by(ManualCover.created_at.desc())
    ).all()
    return ManualCoversResponse(
        covers=[_manual_cover_to_read(row, settings) for row in covers]
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

    if request.pdf_enabled is not None:
        config.pdf_enabled = request.pdf_enabled

    if request.pdf_page_size is not None:
        normalized_page_size = request.pdf_page_size.strip().upper()
        if normalized_page_size not in ("A4", "LETTER", "A5"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="pdf_page_size must be 'A4', 'Letter', or 'A5'",
            )
        config.pdf_page_size = "Letter" if normalized_page_size == "LETTER" else normalized_page_size

    if request.media_processing_interval_hours is not None:
        config.media_processing_interval_hours = request.media_processing_interval_hours

    if request.cover_enabled is not None:
        config.cover_enabled = request.cover_enabled

    if request.cover_provider is not None:
        if request.cover_provider not in ("gpt-image-1", "nano-banana"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="cover_provider must be 'gpt-image-1' or 'nano-banana'",
            )
        config.cover_provider = request.cover_provider

    if request.cover_quality is not None:
        if request.cover_quality not in ("low", "medium", "high"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="cover_quality must be 'low', 'medium', or 'high'",
            )
        config.cover_quality = request.cover_quality

    if request.cover_prompt is not None:
        config.cover_prompt = request.cover_prompt.strip()

    if request.cover_overlay_enabled is not None:
        config.cover_overlay_enabled = request.cover_overlay_enabled

    if request.cover_openai_api_key is not None and request.cover_openai_api_key != SECRET_MASK:
        config.cover_openai_api_key = request.cover_openai_api_key.strip()

    if request.cover_gemini_api_key is not None and request.cover_gemini_api_key != SECRET_MASK:
        config.cover_gemini_api_key = request.cover_gemini_api_key.strip()

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

    changed_fields = request.model_dump(exclude_none=True)
    for secret_field in ("cover_openai_api_key", "cover_gemini_api_key"):
        if secret_field in changed_fields:
            raw_value = str(changed_fields[secret_field])
            if raw_value == SECRET_MASK:
                changed_fields[secret_field] = "<unchanged>"
            elif raw_value == "":
                changed_fields[secret_field] = "<cleared>"
            else:
                changed_fields[secret_field] = "<redacted>"
    logger.info(f"Updated client configuration: {changed_fields}")
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

PASSWORD_MASK = SECRET_MASK


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
