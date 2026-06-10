"""Podcast digest API endpoints."""

from __future__ import annotations

import json
import logging
import mimetypes
import os
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError
from sqlmodel import Session, select

from app.core.config import get_settings
from app.core.database import get_session
from app.core.security import get_current_user, security, verify_api_key
from app.models.article_feedback import ArticleFeedbackRead, ArticleFeedbackUpsert
from app.models.digest import DigestArticle
from app.models.podcast_episode import PodcastEpisode, PodcastEpisodeArticleRead
from app.models.podcast_preferences import (
    PodcastPreferences,
    PodcastPreferencesRead,
    PodcastPreferencesUpdate,
)
from app.models.podcast_schedule import (
    PodcastSchedule,
    PodcastScheduleCreate,
    PodcastScheduleRead,
    PodcastScheduleUpdate,
)
from app.models.user import User
from app.services.one_off_podcast_service import (
    ONE_OFF_MAX_BRIEF_CHARS,
    ONE_OFF_MAX_SOURCES,
    ONE_OFF_MAX_TITLE_CHARS,
    OneOffPodcastError,
    one_off_podcast_service,
    one_off_generation_from_payload,
    one_off_source_from_payload,
)
from app.services.podcast_service import podcast_service
from app.services.podcast_voice_catalog import podcast_voice_catalog_payload

router = APIRouter()
logger = logging.getLogger(__name__)
MAX_ARTWORK_UPLOAD_BYTES = 10 * 1024 * 1024


def _podcast_base_url(request: Request, preferred_base_url: str | None = None) -> str:
    """Resolve absolute base URL used in podcast feed and enclosure links."""
    configured = (preferred_base_url or "").strip()
    if configured:
        return configured.rstrip("/")
    settings = get_settings()
    configured = (settings.podcast_public_base_url or "").strip()
    if configured:
        return configured.rstrip("/")
    return str(request.base_url).rstrip("/")


class PodcastEpisodeStatusRead(BaseModel):
    """Episode status payload with downloadable URLs."""

    id: UUID
    digest_ids: list[str]
    trigger: str = "manual"
    title: str | None = None
    status: str
    audio_size_bytes: int | None = None
    duration_seconds: int | None = None
    episode_number: int | None = None
    article_count: int
    generation_cost_cents: int | None = None
    generation_preferences: dict[str, object] = Field(default_factory=dict)
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
    stream_url: str | None = None
    download_url: str | None = None


class PodcastChapterRead(BaseModel):
    """One chapter marker within an episode."""

    title: str
    start_seconds: float


class PodcastEpisodeDetailRead(PodcastEpisodeStatusRead):
    """Detailed episode payload including script and source article list."""

    script: str | None = None
    article_ids: list[str]
    articles: list[PodcastEpisodeArticleRead]
    chapters: list[PodcastChapterRead] | None = None


class PodcastTriggerResponse(BaseModel):
    """Response for manual/automatic trigger endpoints."""

    episode_id: UUID
    digest_ids: list[str]
    status: str
    message: str


class OneOffPodcastSourceRequest(BaseModel):
    """One source for one-off podcast generation."""

    type: Literal["url", "text"]
    title: str | None = Field(default=None, max_length=ONE_OFF_MAX_TITLE_CHARS)
    url: str | None = None
    content: str | None = None


class OneOffPodcastGenerationRequest(BaseModel):
    """Per-episode podcast generation overrides for one-off episodes."""

    preferred_length_minutes: int | None = Field(default=None, ge=5, le=60)
    script_model: str | None = None
    script_timeout_seconds: int | None = Field(default=None, ge=30, le=600)
    style: Literal["casual", "formal", "deep-dive"] | None = None
    tts_provider: Literal["openai", "elevenlabs"] | None = None
    openai_tts_model: str | None = None
    elevenlabs_model_id: str | None = None
    elevenlabs_output_format: str | None = None
    elevenlabs_expressiveness: Literal["creative", "natural", "robust"] | None = None
    host_a_voice: str | None = None
    host_b_voice: str | None = None
    host_count: int | None = Field(default=None, ge=1, le=2)


class OneOffPodcastCreateRequest(BaseModel):
    """Request to create a podcast episode from ad hoc source material."""

    title: str | None = Field(default=None, max_length=ONE_OFF_MAX_TITLE_CHARS)
    brief: str | None = Field(default=None, max_length=ONE_OFF_MAX_BRIEF_CHARS)
    sources: list[OneOffPodcastSourceRequest] = Field(
        min_length=1,
        max_length=ONE_OFF_MAX_SOURCES,
    )
    generation: OneOffPodcastGenerationRequest | None = None


class DigestPodcastStatusResponse(BaseModel):
    """Digest-level podcast status payload."""

    digest_id: UUID
    episode: PodcastEpisodeStatusRead


class PodcastFeedInfoResponse(BaseModel):
    """Feed information and setup guidance."""

    feed_enabled: bool
    feed_title: str
    feed_description: str
    feed_url: str
    setup_instructions: list[str]


class PodcastArtworkUploadResponse(BaseModel):
    """Artwork upload result payload."""

    status: str
    artwork_path: str
    width: int
    height: int


class PodcastVoiceCatalogEntryRead(BaseModel):
    """Display metadata for a configured podcast voice."""

    provider: Literal["openai", "elevenlabs"]
    name: str
    id: str
    vibe: str
    best_suited_for: str
    pairing_notes: str


class PodcastVoicePairPresetRead(BaseModel):
    """Named host voice pair preset."""

    provider: Literal["openai", "elevenlabs"]
    label: str
    host_a_voice: str
    host_b_voice: str
    best_suited_for: str


class PodcastVoiceCatalogRead(BaseModel):
    """Podcast voice catalog response."""

    voices: list[PodcastVoiceCatalogEntryRead]
    pair_presets: list[PodcastVoicePairPresetRead]


def _build_episode_status(
    request: Request,
    episode: PodcastEpisode,
    *,
    feed_token: str | None = None,
) -> PodcastEpisodeStatusRead:
    if feed_token:
        stream_url = f"/api/podcast/episodes/{episode.id}/stream?token={feed_token}"
        download_url = f"/api/podcast/episodes/{episode.id}/download?token={feed_token}"
    else:
        stream_url = f"/api/podcast/episodes/{episode.id}/stream"
        download_url = f"/api/podcast/episodes/{episode.id}/download"

    base_url = _podcast_base_url(request)
    return PodcastEpisodeStatusRead(
        id=episode.id,
        digest_ids=episode.digest_ids or [],
        trigger=episode.trigger or "manual",
        title=episode.title,
        status=episode.status,
        audio_size_bytes=episode.audio_size_bytes,
        duration_seconds=episode.duration_seconds,
        episode_number=episode.episode_number,
        article_count=episode.article_count,
        generation_cost_cents=episode.generation_cost_cents,
        generation_preferences=episode.generation_preferences or {},
        error_message=episode.error_message,
        created_at=episode.created_at,
        completed_at=episode.completed_at,
        stream_url=base_url + stream_url,
        download_url=base_url + download_url,
    )


def _episode_chapter_reads(
    episode: PodcastEpisode,
) -> list[PodcastChapterRead] | None:
    """Validate stored chapter dicts into typed reads; None when unusable."""
    if not episode.chapters:
        return None
    chapters: list[PodcastChapterRead] = []
    for raw in episode.chapters:
        if not isinstance(raw, dict):
            continue
        title = str(raw.get("title") or "").strip()
        try:
            start_seconds = float(raw.get("start_seconds", 0.0))
        except (TypeError, ValueError):
            continue
        if title:
            chapters.append(
                PodcastChapterRead(title=title, start_seconds=start_seconds)
            )
    return chapters or None


def _resolve_episode_articles(
    session: Session,
    episode: PodcastEpisode,
) -> list[PodcastEpisodeArticleRead]:
    ids: list[UUID] = []
    for raw in episode.article_ids:
        try:
            ids.append(UUID(raw))
        except ValueError:
            continue

    if not ids:
        return []

    mapping: dict[UUID, DigestArticle] = {}
    rows = session.exec(select(DigestArticle).where(DigestArticle.id.in_(ids))).all()
    for row in rows:
        mapping[row.id] = row

    ordered: list[PodcastEpisodeArticleRead] = []
    for article_id in ids:
        article = mapping.get(article_id)
        if not article:
            continue
        ordered.append(
            PodcastEpisodeArticleRead(
                id=article.id,
                title=article.title,
                url=article.url,
                feed_title=article.feed_title,
            )
        )
    return ordered


def _episode_for_digest(session: Session, digest_id: UUID) -> PodcastEpisode | None:
    digest_id_str = str(digest_id)
    all_episodes = session.exec(
        select(PodcastEpisode).order_by(PodcastEpisode.created_at.desc())
    ).all()
    return next(
        (episode for episode in all_episodes if digest_id_str in (episode.digest_ids or [])),
        None,
    )


def _parse_range(range_header: str | None, file_size: int) -> tuple[int, int] | None:
    if not range_header:
        return None
    if not range_header.startswith("bytes="):
        raise HTTPException(status_code=416, detail="Invalid Range header")

    spec = range_header.replace("bytes=", "", 1).split(",")[0].strip()
    if "-" not in spec:
        raise HTTPException(status_code=416, detail="Invalid Range header")
    start_raw, end_raw = spec.split("-", 1)

    try:
        if start_raw == "":
            length = int(end_raw)
            if length <= 0:
                raise HTTPException(status_code=416, detail="Invalid Range header")
            start = max(0, file_size - length)
            end = file_size - 1
        else:
            start = int(start_raw)
            end = int(end_raw) if end_raw else file_size - 1
    except ValueError as exc:
        raise HTTPException(status_code=416, detail="Invalid Range header") from exc

    if start < 0 or end < start or start >= file_size:
        raise HTTPException(status_code=416, detail="Requested range not satisfiable")

    end = min(end, file_size - 1)
    return start, end


def _read_range(
    path: Path, start: int, end: int, chunk_size: int = 64 * 1024
) -> Iterator[bytes]:
    with path.open("rb") as fp:
        fp.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            data = fp.read(min(chunk_size, remaining))
            if not data:
                break
            remaining -= len(data)
            yield data


def _validated_child_path(
    path: Path, *, allowed_parent: Path, not_found_detail: str
) -> Path:
    """Resolve and validate file path remains inside an expected parent directory."""
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise HTTPException(status_code=404, detail=not_found_detail) from exc

    parent_resolved = allowed_parent.resolve()
    try:
        resolved.relative_to(parent_resolved)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Invalid media file path") from exc
    return resolved


async def _authorize_standard_or_feed_token(
    request: Request,
    session: Session,
    feed_token: str | None,
) -> PodcastPreferences | None:
    if feed_token:
        prefs = podcast_service.get_preferences_by_feed_token(session, feed_token)
        if prefs is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid feed token",
            )
        return prefs

    credentials = await security(request)
    await verify_api_key(
        request=request,
        credentials=credentials,
        settings=get_settings(),
    )
    return None


async def _current_user_for_request(request: Request, session: Session) -> User:
    credentials = await security(request)
    return await get_current_user(request, credentials, session)


async def _ensure_one_off_episode_access(
    request: Request,
    session: Session,
    episode: PodcastEpisode,
) -> None:
    if episode.user_id is None:
        return

    current_user = await _current_user_for_request(request, session)
    if episode.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Podcast episode not found")


async def _ensure_one_off_digest_episode_access(
    request: Request,
    session: Session,
    digest_id: UUID,
) -> None:
    if not podcast_service.is_one_off_digest(session, digest_id):
        return

    episode = _episode_for_digest(session, digest_id)
    if episode is None:
        raise HTTPException(status_code=404, detail="Podcast episode not found")
    await _ensure_one_off_episode_access(request, session, episode)


async def _resolve_podcast_preferences_user_id(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None,
    session: Session,
) -> UUID | None:
    try:
        user = await get_current_user(request, credentials, session)
        return user.id
    except HTTPException as exc:
        settings = get_settings()
        has_users = session.exec(select(User)).first() is not None
        if exc.status_code == 401 and not has_users:
            token = None
            if credentials and credentials.credentials:
                token = credentials.credentials
            else:
                token = request.headers.get("x-api-key")
            if not settings.api_key or token == settings.api_key:
                return None
        raise


def _to_rfc2822(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return format_datetime(dt)


def _format_duration(seconds: int | None) -> str:
    if not seconds:
        return "0:00"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours:
        return f"{hours:d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:d}:{secs:02d}"


@router.get(
    "/podcast/preferences",
    response_model=PodcastPreferencesRead,
)
async def get_podcast_preferences(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    session: Session = Depends(get_session),
):
    """Get podcast preferences for the authenticated user."""
    user_id = await _resolve_podcast_preferences_user_id(
        request,
        credentials,
        session,
    )
    prefs = podcast_service.get_or_create_preferences(
        session,
        user_id=user_id,
    )
    return PodcastPreferencesRead(
        enabled=prefs.enabled,
        schedule=prefs.schedule,
        schedule_time=prefs.schedule_time,
        schedule_day=prefs.schedule_day,
        topic_weights=prefs.topic_weights,
        boost_sources=prefs.boost_sources,
        boost_keywords=prefs.boost_keywords,
        filter_keywords=prefs.filter_keywords,
        preferred_length_minutes=prefs.preferred_length_minutes,
        script_model=prefs.script_model,
        script_timeout_seconds=prefs.script_timeout_seconds,
        style=prefs.style,
        tts_provider=prefs.tts_provider,
        openai_tts_model=prefs.openai_tts_model,
        elevenlabs_model_id=prefs.elevenlabs_model_id,
        elevenlabs_output_format=prefs.elevenlabs_output_format,
        elevenlabs_expressiveness=prefs.elevenlabs_expressiveness,
        host_a_voice=prefs.host_a_voice,
        host_b_voice=prefs.host_b_voice,
        host_count=prefs.host_count,
        podcast_feed_enabled=prefs.podcast_feed_enabled,
        podcast_feed_title=prefs.podcast_feed_title,
        podcast_feed_description=prefs.podcast_feed_description,
        podcast_feed_base_url=prefs.podcast_feed_base_url,
        podcast_feed_artwork_path=prefs.podcast_feed_artwork_path,
        updated_at=prefs.updated_at,
    )


@router.get(
    "/podcast/voices",
    response_model=PodcastVoiceCatalogRead,
    dependencies=[Depends(verify_api_key)],
)
async def get_podcast_voice_catalog():
    """Return provider voice IDs and pairing guidance for podcast generation."""
    return podcast_voice_catalog_payload()


@router.put(
    "/podcast/preferences",
    response_model=PodcastPreferencesRead,
)
async def update_podcast_preferences(
    update: PodcastPreferencesUpdate,
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    session: Session = Depends(get_session),
):
    """Update podcast preferences."""
    from app.worker.scheduler import update_podcast_schedule

    user_id = await _resolve_podcast_preferences_user_id(
        request,
        credentials,
        session,
    )
    schedule_fields = ("enabled", "schedule", "schedule_time", "schedule_day")
    singleton_user_id = podcast_service.resolve_user_id(session)
    if (
        user_id is not None
        and user_id != singleton_user_id
        and any(getattr(update, field) is not None for field in schedule_fields)
    ):
        raise HTTPException(
            status_code=400,
            detail="Podcast schedule settings can only be changed by the singleton owner",
        )
    try:
        prefs = podcast_service.update_preferences(
            session,
            update,
            user_id=user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Sync the independent podcast APScheduler job
    update_podcast_schedule()

    return PodcastPreferencesRead(
        enabled=prefs.enabled,
        schedule=prefs.schedule,
        schedule_time=prefs.schedule_time,
        schedule_day=prefs.schedule_day,
        topic_weights=prefs.topic_weights,
        boost_sources=prefs.boost_sources,
        boost_keywords=prefs.boost_keywords,
        filter_keywords=prefs.filter_keywords,
        preferred_length_minutes=prefs.preferred_length_minutes,
        script_model=prefs.script_model,
        script_timeout_seconds=prefs.script_timeout_seconds,
        style=prefs.style,
        tts_provider=prefs.tts_provider,
        openai_tts_model=prefs.openai_tts_model,
        elevenlabs_model_id=prefs.elevenlabs_model_id,
        elevenlabs_output_format=prefs.elevenlabs_output_format,
        elevenlabs_expressiveness=prefs.elevenlabs_expressiveness,
        host_a_voice=prefs.host_a_voice,
        host_b_voice=prefs.host_b_voice,
        host_count=prefs.host_count,
        podcast_feed_enabled=prefs.podcast_feed_enabled,
        podcast_feed_title=prefs.podcast_feed_title,
        podcast_feed_description=prefs.podcast_feed_description,
        podcast_feed_base_url=prefs.podcast_feed_base_url,
        podcast_feed_artwork_path=prefs.podcast_feed_artwork_path,
        updated_at=prefs.updated_at,
    )


@router.post(
    "/articles/{article_id}/feedback",
    response_model=ArticleFeedbackRead,
    dependencies=[Depends(verify_api_key)],
)
async def upsert_article_feedback(
    article_id: UUID,
    payload: ArticleFeedbackUpsert,
    session: Session = Depends(get_session),
):
    """Create or update explicit feedback for one digest article."""
    article = session.get(DigestArticle, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    user_id = podcast_service.resolve_user_id(session)
    feedback = podcast_service.upsert_feedback(
        session,
        article=article,
        payload=payload,
        user_id=user_id,
    )
    return ArticleFeedbackRead(
        article_id=feedback.article_id,
        digest_id=feedback.digest_id,
        rating=feedback.rating,
        read_duration_sec=feedback.read_duration_sec,
        bookmarked=feedback.bookmarked,
        shared=feedback.shared,
        created_at=feedback.created_at,
        updated_at=feedback.updated_at,
    )


@router.delete(
    "/articles/{article_id}/feedback",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(verify_api_key)],
)
async def delete_article_feedback(
    article_id: UUID,
    session: Session = Depends(get_session),
):
    """Delete explicit feedback for one digest article."""
    user_id = podcast_service.resolve_user_id(session)
    deleted = podcast_service.delete_feedback(
        session, article_id=article_id, user_id=user_id
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Feedback not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/digests/{digest_id}/podcast",
    response_model=PodcastTriggerResponse,
    dependencies=[Depends(verify_api_key)],
)
async def trigger_digest_podcast(
    digest_id: UUID,
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    session: Session = Depends(get_session),
):
    """Manually queue podcast generation for one digest."""
    await _ensure_one_off_digest_episode_access(request, session, digest_id)
    user_id = await _resolve_podcast_preferences_user_id(
        request,
        credentials,
        session,
    )
    trigger = (
        "one_off" if podcast_service.is_one_off_digest(session, digest_id) else "manual"
    )
    try:
        episode = podcast_service.queue_episode_generation(
            session,
            digest_id=digest_id,
            user_id=user_id,
            force=False,
            trigger=trigger,
        )
    except ValueError as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=409, detail=message) from exc

    return PodcastTriggerResponse(
        episode_id=episode.id,
        digest_ids=episode.digest_ids or [],
        status=episode.status,
        message="Podcast generation queued",
    )


@router.post(
    "/podcast/episodes/generate",
    response_model=PodcastTriggerResponse,
    dependencies=[Depends(verify_api_key)],
)
async def generate_podcast_now(
    session: Session = Depends(get_session),
):
    """Manually trigger podcast generation using the time-window approach (same as scheduled)."""
    try:
        episode_id = podcast_service.generate_scheduled_episode()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)[:300]) from exc

    if episode_id is None:
        raise HTTPException(
            status_code=409,
            detail="No eligible digests found or episode already exists for current window",
        )

    episode = session.get(PodcastEpisode, episode_id)
    if episode is None:
        raise HTTPException(status_code=500, detail="Episode created but not found")

    return PodcastTriggerResponse(
        episode_id=episode.id,
        digest_ids=episode.digest_ids or [],
        status=episode.status,
        message="Podcast generation queued from recent digests",
    )


@router.post(
    "/podcast/episodes/one-off",
    response_model=PodcastTriggerResponse,
)
async def create_one_off_podcast_episode(
    payload: OneOffPodcastCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Session = Depends(get_session),
):
    """Create a podcast episode from caller-supplied URL and text sources."""
    try:
        episode = await one_off_podcast_service.create_episode(
            session,
            title=payload.title,
            brief=payload.brief,
            sources=[one_off_source_from_payload(source) for source in payload.sources],
            generation=one_off_generation_from_payload(payload.generation),
            user_id=current_user.id,
        )
    except OneOffPodcastError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return PodcastTriggerResponse(
        episode_id=episode.id,
        digest_ids=episode.digest_ids or [],
        status=episode.status,
        message="One-off podcast generation queued",
    )


@router.get(
    "/digests/{digest_id}/podcast",
    response_model=DigestPodcastStatusResponse,
    dependencies=[Depends(verify_api_key)],
)
async def get_digest_podcast_status(
    digest_id: UUID,
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    session: Session = Depends(get_session),
):
    """Get podcast generation status for a digest."""
    await _ensure_one_off_digest_episode_access(request, session, digest_id)
    digest_id_str = str(digest_id)
    try:
        # Find episodes that contain this digest_id in their digest_ids JSON array
        all_episodes = session.exec(
            select(PodcastEpisode).order_by(PodcastEpisode.created_at.desc())
        ).all()
        user_id = await _resolve_podcast_preferences_user_id(
            request,
            credentials,
            session,
        )
        matching_episodes = [
            ep for ep in all_episodes if digest_id_str in (ep.digest_ids or [])
        ]
        user_episodes = (
            [ep for ep in matching_episodes if ep.user_id == user_id]
            if user_id is not None
            else []
        )
        legacy_episodes = [
            ep for ep in matching_episodes if ep.user_id is None
        ]
        episode = next(
            iter(user_episodes or legacy_episodes),
            None,
        )
    except SQLAlchemyTimeoutError as exc:
        logger.warning(
            "Podcast status check timed out waiting for DB connection",
            extra={"digest_id": str(digest_id)},
            exc_info=exc,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Podcast status temporarily unavailable. Please retry shortly.",
        ) from exc
    if episode is None:
        raise HTTPException(
            status_code=404, detail="Podcast episode not found for digest"
        )
    return DigestPodcastStatusResponse(
        digest_id=digest_id,
        episode=_build_episode_status(request, episode),
    )


@router.post(
    "/podcast/episodes/{episode_id}/retry",
    response_model=PodcastTriggerResponse,
    dependencies=[Depends(verify_api_key)],
)
async def retry_podcast_episode(
    episode_id: UUID,
    request: Request,
    session: Session = Depends(get_session),
):
    """Retry failed podcast generation."""
    episode = session.get(PodcastEpisode, episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail="Podcast episode not found")
    await _ensure_one_off_episode_access(request, session, episode)
    if episode.status != "failed":
        raise HTTPException(
            status_code=409, detail="Only failed episodes can be retried"
        )

    digest_ids = episode.digest_ids or []
    if not digest_ids:
        raise HTTPException(status_code=409, detail="Episode has no associated digests")

    # Retry using the first digest for single-digest episodes
    first_digest_id = UUID(digest_ids[0])
    retried = podcast_service.queue_episode_generation(
        session,
        digest_id=first_digest_id,
        user_id=episode.user_id,
        force=True,
        trigger=episode.trigger,
    )
    return PodcastTriggerResponse(
        episode_id=retried.id,
        digest_ids=retried.digest_ids or [],
        status=retried.status,
        message="Podcast episode retry queued",
    )


@router.get(
    "/podcast/episodes",
    response_model=list[PodcastEpisodeStatusRead],
    dependencies=[Depends(verify_api_key)],
)
async def list_podcast_episodes(
    request: Request,
    session: Session = Depends(get_session),
):
    """List podcast episodes."""
    episodes = session.exec(
        select(PodcastEpisode).order_by(PodcastEpisode.created_at.desc())
    ).all()
    if any(episode.user_id is not None for episode in episodes):
        current_user = await _current_user_for_request(request, session)
        episodes = [
            episode
            for episode in episodes
            if episode.user_id is None or episode.user_id == current_user.id
        ]
    return [_build_episode_status(request, episode) for episode in episodes]


@router.get(
    "/podcast/episodes/{episode_id}",
    response_model=PodcastEpisodeDetailRead,
    dependencies=[Depends(verify_api_key)],
)
async def get_podcast_episode(
    episode_id: UUID,
    request: Request,
    session: Session = Depends(get_session),
):
    """Get detailed episode information."""
    episode = session.get(PodcastEpisode, episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail="Podcast episode not found")
    await _ensure_one_off_episode_access(request, session, episode)
    status_payload = _build_episode_status(request, episode)
    return PodcastEpisodeDetailRead(
        **status_payload.model_dump(),
        script=episode.script,
        article_ids=episode.article_ids,
        articles=_resolve_episode_articles(session, episode),
        chapters=_episode_chapter_reads(episode),
    )


@router.delete(
    "/podcast/episodes/{episode_id}",
    dependencies=[Depends(verify_api_key)],
)
async def delete_podcast_episode(
    episode_id: UUID,
    request: Request,
    session: Session = Depends(get_session),
):
    """Delete one podcast episode and local audio artifact."""
    settings = get_settings()
    episode = session.get(PodcastEpisode, episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail="Podcast episode not found")
    await _ensure_one_off_episode_access(request, session, episode)

    audio_path: Path | None = None
    if episode.audio_path and os.path.exists(episode.audio_path):
        audio_path = _validated_child_path(
            Path(episode.audio_path),
            allowed_parent=Path(settings.output_dir) / "podcasts",
            not_found_detail="Audio file not found",
        )

    session.delete(episode)
    session.commit()
    if audio_path is not None:
        try:
            os.remove(audio_path)
        except OSError as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to delete audio file: {exc}",
            ) from exc
    return {"status": "deleted"}


@router.get("/podcast/episodes/{episode_id}/stream")
async def stream_podcast_episode(
    episode_id: UUID,
    request: Request,
    token: str | None = Query(default=None),
    session: Session = Depends(get_session),
):
    """Stream podcast MP3 with byte-range support."""
    token_prefs = await _authorize_standard_or_feed_token(request, session, token)
    settings = get_settings()

    episode = session.get(PodcastEpisode, episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail="Podcast episode not found")
    if token_prefs is not None and episode.user_id != token_prefs.user_id:
        raise HTTPException(status_code=404, detail="Podcast episode not found")
    if token_prefs is None:
        await _ensure_one_off_episode_access(request, session, episode)
    if episode.status != "ready":
        raise HTTPException(status_code=409, detail="Podcast episode is not ready")
    if not episode.audio_path or not os.path.exists(episode.audio_path):
        raise HTTPException(status_code=404, detail="Audio file not found")

    audio_path = _validated_child_path(
        Path(episode.audio_path),
        allowed_parent=Path(settings.output_dir) / "podcasts",
        not_found_detail="Audio file not found",
    )
    file_size = audio_path.stat().st_size
    range_header = request.headers.get("range")
    requested_range = _parse_range(range_header, file_size)

    base_headers = {
        "Accept-Ranges": "bytes",
        "Cache-Control": "no-cache",
    }

    if requested_range is None:
        return FileResponse(
            audio_path,
            media_type="audio/mpeg",
            headers=base_headers,
        )

    start, end = requested_range
    headers = {
        **base_headers,
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Content-Length": str(end - start + 1),
    }
    return StreamingResponse(
        _read_range(audio_path, start, end),
        media_type="audio/mpeg",
        headers=headers,
        status_code=status.HTTP_206_PARTIAL_CONTENT,
    )


@router.get("/podcast/episodes/{episode_id}/download")
async def download_podcast_episode(
    episode_id: UUID,
    request: Request,
    token: str | None = Query(default=None),
    session: Session = Depends(get_session),
):
    """Download podcast MP3 file."""
    token_prefs = await _authorize_standard_or_feed_token(request, session, token)
    settings = get_settings()

    episode = session.get(PodcastEpisode, episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail="Podcast episode not found")
    if token_prefs is not None and episode.user_id != token_prefs.user_id:
        raise HTTPException(status_code=404, detail="Podcast episode not found")
    if token_prefs is None:
        await _ensure_one_off_episode_access(request, session, episode)
    if episode.status != "ready":
        raise HTTPException(status_code=409, detail="Podcast episode is not ready")
    if not episode.audio_path or not os.path.exists(episode.audio_path):
        raise HTTPException(status_code=404, detail="Audio file not found")

    audio_path = _validated_child_path(
        Path(episode.audio_path),
        allowed_parent=Path(settings.output_dir) / "podcasts",
        not_found_detail="Audio file not found",
    )

    return FileResponse(
        audio_path,
        media_type="audio/mpeg",
        filename=f"podcast-{episode_id}.mp3",
    )


@router.get("/podcast/episodes/{episode_id}/chapters")
async def get_podcast_episode_chapters(
    episode_id: UUID,
    request: Request,
    token: str | None = Query(default=None),
    session: Session = Depends(get_session),
):
    """Return episode chapters in Podcasting 2.0 JSON chapters format."""
    token_prefs = await _authorize_standard_or_feed_token(request, session, token)

    episode = session.get(PodcastEpisode, episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail="Podcast episode not found")
    if token_prefs is not None and episode.user_id != token_prefs.user_id:
        raise HTTPException(status_code=404, detail="Podcast episode not found")
    if token_prefs is None:
        await _ensure_one_off_episode_access(request, session, episode)
    if episode.status != "ready":
        raise HTTPException(status_code=409, detail="Podcast episode is not ready")

    chapters = _episode_chapter_reads(episode)
    if not chapters:
        raise HTTPException(status_code=404, detail="Episode has no chapters")

    payload = {
        "version": "1.2.0",
        "chapters": [
            {"startTime": chapter.start_seconds, "title": chapter.title}
            for chapter in chapters
        ],
    }
    return Response(
        content=json.dumps(payload),
        media_type="application/json+chapters",
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/podcast/feed.xml")
async def get_podcast_feed_xml(
    request: Request,
    token: str = Query(..., min_length=8),
    session: Session = Depends(get_session),
):
    """Return private RSS feed XML for podcast applications."""
    prefs = podcast_service.get_preferences_by_feed_token(session, token)
    if prefs is None:
        raise HTTPException(status_code=401, detail="Invalid feed token")
    if not prefs.podcast_feed_enabled:
        raise HTTPException(status_code=404, detail="Podcast feed is disabled")

    base_url = _podcast_base_url(request, prefs.podcast_feed_base_url)
    episodes = session.exec(
        select(PodcastEpisode)
        .where(PodcastEpisode.status == "ready")
        .where(PodcastEpisode.user_id == prefs.user_id)
        .order_by(PodcastEpisode.created_at.desc())
        .limit(100)
    ).all()

    ET.register_namespace("itunes", "http://www.itunes.com/dtds/podcast-1.0.dtd")
    ET.register_namespace("content", "http://purl.org/rss/1.0/modules/content/")
    ET.register_namespace("podcast", "https://podcastindex.org/namespace/1.0")

    rss = ET.Element(
        "rss",
        {
            "version": "2.0",
            "xmlns:itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
            "xmlns:content": "http://purl.org/rss/1.0/modules/content/",
            "xmlns:podcast": "https://podcastindex.org/namespace/1.0",
        },
    )
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = prefs.podcast_feed_title
    ET.SubElement(channel, "description").text = prefs.podcast_feed_description
    ET.SubElement(channel, "itunes:subtitle").text = prefs.podcast_feed_description
    ET.SubElement(channel, "link").text = base_url
    ET.SubElement(channel, "language").text = "en-us"
    ET.SubElement(channel, "itunes:author").text = "Ghostwriter"
    ET.SubElement(channel, "itunes:explicit").text = "false"
    ET.SubElement(channel, "itunes:category", {"text": "Technology"})
    if episodes:
        newest = episodes[0].completed_at or episodes[0].created_at
        ET.SubElement(channel, "lastBuildDate").text = _to_rfc2822(newest)

    if prefs.podcast_feed_artwork_path and os.path.exists(
        prefs.podcast_feed_artwork_path
    ):
        image_url = base_url + "/api/podcast/feed/artwork" + f"?token={token}"
        ET.SubElement(channel, "itunes:image", {"href": image_url})

    for episode in episodes:
        item = ET.SubElement(channel, "item")
        created = episode.completed_at or episode.created_at
        created_local = created.date().isoformat()

        digest_count = len(episode.digest_ids or [])
        if episode.trigger == "one_off":
            ET.SubElement(item, "title").text = (
                episode.title or ""
            ).strip() or f"One-off Podcast - {created_local}"
        elif digest_count > 1:
            ET.SubElement(
                item, "title"
            ).text = f"Digest Podcast - {created_local} ({digest_count} digests)"
        else:
            ET.SubElement(item, "title").text = f"Digest Podcast - {created_local}"

        article_titles = [
            article.title for article in _resolve_episode_articles(session, episode)
        ]
        if article_titles:
            ET.SubElement(item, "description").text = "Includes: " + "; ".join(
                article_titles[:8]
            )
        else:
            ET.SubElement(
                item, "description"
            ).text = "AI-generated digest podcast episode"

        ET.SubElement(item, "pubDate").text = _to_rfc2822(created)
        enclosure_url = (
            base_url + f"/api/podcast/episodes/{episode.id}/download?token={token}"
        )
        ET.SubElement(
            item,
            "enclosure",
            {
                "url": enclosure_url,
                "length": str(episode.audio_size_bytes or 0),
                "type": "audio/mpeg",
            },
        )
        ET.SubElement(item, "itunes:duration").text = _format_duration(
            episode.duration_seconds
        )
        if _episode_chapter_reads(episode):
            ET.SubElement(
                item,
                "podcast:chapters",
                {
                    "url": (
                        base_url
                        + f"/api/podcast/episodes/{episode.id}/chapters?token={token}"
                    ),
                    "type": "application/json+chapters",
                },
            )
        if episode.trigger == "one_off":
            ET.SubElement(item, "itunes:episodeType").text = "bonus"
        else:
            if episode.episode_number is not None:
                ET.SubElement(item, "itunes:episode").text = str(
                    episode.episode_number
                )
            ET.SubElement(item, "itunes:episodeType").text = "full"
        ET.SubElement(
            item, "guid", {"isPermaLink": "false"}
        ).text = f"podcast-episode-{episode.id}"

    xml_bytes = ET.tostring(rss, encoding="utf-8", xml_declaration=True)
    return Response(content=xml_bytes, media_type="application/rss+xml; charset=utf-8")


@router.get(
    "/podcast/feed/info",
    response_model=PodcastFeedInfoResponse,
)
async def get_podcast_feed_info(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    session: Session = Depends(get_session),
):
    """Return feed URL and setup instructions for podcast apps."""
    user_id = await _resolve_podcast_preferences_user_id(
        request,
        credentials,
        session,
    )
    prefs = podcast_service.get_or_create_preferences(
        session,
        user_id=user_id,
    )
    base_url = _podcast_base_url(request, prefs.podcast_feed_base_url)
    feed_url = f"{base_url}/api/podcast/feed.xml?token={prefs.podcast_feed_token}"

    return PodcastFeedInfoResponse(
        feed_enabled=prefs.podcast_feed_enabled,
        feed_title=prefs.podcast_feed_title,
        feed_description=prefs.podcast_feed_description,
        feed_url=feed_url,
        setup_instructions=[
            "Copy the feed URL.",
            "Open your podcast app and choose Add Podcast by URL.",
            "Paste the URL to subscribe to your private digest feed.",
        ],
    )


@router.get("/podcast/feed/artwork")
async def get_podcast_feed_artwork(
    token: str = Query(..., min_length=8),
    session: Session = Depends(get_session),
):
    """Serve uploaded feed artwork for authenticated feed clients."""
    settings = get_settings()
    prefs = podcast_service.get_preferences_by_feed_token(session, token)
    if prefs is None:
        raise HTTPException(status_code=401, detail="Invalid feed token")
    if not prefs.podcast_feed_artwork_path:
        raise HTTPException(status_code=404, detail="Feed artwork not configured")
    artwork_path = _validated_child_path(
        Path(prefs.podcast_feed_artwork_path),
        allowed_parent=Path(settings.data_dir) / "podcast_artwork",
        not_found_detail="Feed artwork not found",
    )
    media_type = mimetypes.guess_type(str(artwork_path))[0] or "image/jpeg"
    return FileResponse(artwork_path, media_type=media_type)


@router.post(
    "/podcast/feed/artwork",
    response_model=PodcastArtworkUploadResponse,
)
async def upload_podcast_feed_artwork(
    request: Request,
    file: UploadFile = File(...),
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    session: Session = Depends(get_session),
):
    """Upload custom podcast feed artwork (minimum 1400x1400)."""
    user_id = await _resolve_podcast_preferences_user_id(
        request,
        credentials,
        session,
    )

    try:
        from PIL import Image
    except Exception as exc:  # pragma: no cover - Pillow is an install dependency.
        raise HTTPException(
            status_code=500, detail=f"Pillow unavailable: {exc}"
        ) from exc

    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Artwork file must be an image")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Artwork file is empty")
    if len(data) > MAX_ARTWORK_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Artwork file exceeds 10MB limit")

    try:
        from io import BytesIO

        image = Image.open(BytesIO(data))
        width, height = image.size
        image.verify()
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Invalid artwork image: {exc}"
        ) from exc

    ext = (image.format or "JPEG").lower()
    if ext == "jpeg":
        ext = "jpg"

    prefs = podcast_service.get_or_create_preferences(session, user_id=user_id)

    settings = get_settings()
    artwork_dir = Path(settings.data_dir) / "podcast_artwork"
    artwork_dir.mkdir(parents=True, exist_ok=True)
    artwork_path = artwork_dir / f"podcast_feed_{prefs.id}.{ext}"
    artwork_path.write_bytes(data)

    prefs.podcast_feed_artwork_path = str(artwork_path)
    prefs.updated_at = datetime.utcnow()
    session.add(prefs)
    session.commit()

    return PodcastArtworkUploadResponse(
        status="uploaded",
        artwork_path=str(artwork_path),
        width=width,
        height=height,
    )


# ---------------------------------------------------------------------------
# Podcast Schedules CRUD
# ---------------------------------------------------------------------------


def _schedule_to_read(
    sched: PodcastSchedule, next_run_at: datetime | None = None
) -> PodcastScheduleRead:
    return PodcastScheduleRead(
        id=sched.id,
        name=sched.name,
        days=sched.days or [],
        time=sched.time,
        timezone=sched.timezone,
        enabled=sched.enabled,
        last_run_at=sched.last_run_at,
        last_episode_id=sched.last_episode_id,
        next_run_at=next_run_at,
        created_at=sched.created_at,
        updated_at=sched.updated_at,
    )


@router.get(
    "/podcast/schedules",
    response_model=list[PodcastScheduleRead],
    dependencies=[Depends(verify_api_key)],
)
async def list_podcast_schedules(session: Session = Depends(get_session)):
    """List all podcast schedules."""
    from app.worker.scheduler import get_podcast_schedule_next_run

    schedules = session.exec(
        select(PodcastSchedule).order_by(PodcastSchedule.created_at.asc())
    ).all()
    return [
        _schedule_to_read(s, get_podcast_schedule_next_run(s.id)) for s in schedules
    ]


@router.post(
    "/podcast/schedules",
    response_model=PodcastScheduleRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_api_key)],
)
async def create_podcast_schedule(
    payload: PodcastScheduleCreate,
    session: Session = Depends(get_session),
):
    """Create a new podcast schedule."""
    from app.worker.scheduler import (
        get_podcast_schedule_next_run,
        update_podcast_schedule,
    )

    if not payload.days:
        raise HTTPException(
            status_code=400, detail="At least one day must be specified"
        )

    # Validate time format
    parts = payload.time.strip().split(":")
    if len(parts) != 2:
        raise HTTPException(status_code=400, detail="time must be in HH:MM format")
    try:
        h, m = int(parts[0]), int(parts[1])
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError
    except ValueError:
        raise HTTPException(status_code=400, detail="time must be in HH:MM format")

    user_id = podcast_service.resolve_user_id(session)
    now = datetime.utcnow()

    # Resolve timezone: use payload, fall back to client config
    tz = payload.timezone
    if not tz:
        from app.models.client_config import ClientConfig

        config = session.exec(select(ClientConfig)).first()
        tz = config.timezone if config and config.timezone else "UTC"

    sched = PodcastSchedule(
        user_id=user_id,
        name=payload.name,
        days=[d for d in payload.days],
        time=payload.time,
        timezone=tz,
        enabled=payload.enabled,
        created_at=now,
        updated_at=now,
    )
    session.add(sched)
    session.commit()
    session.refresh(sched)

    update_podcast_schedule()

    return _schedule_to_read(sched, get_podcast_schedule_next_run(sched.id))


@router.get(
    "/podcast/schedules/{schedule_id}",
    response_model=PodcastScheduleRead,
    dependencies=[Depends(verify_api_key)],
)
async def get_podcast_schedule(
    schedule_id: UUID,
    session: Session = Depends(get_session),
):
    """Get a single podcast schedule."""
    from app.worker.scheduler import get_podcast_schedule_next_run

    sched = session.get(PodcastSchedule, schedule_id)
    if sched is None:
        raise HTTPException(status_code=404, detail="Podcast schedule not found")
    return _schedule_to_read(sched, get_podcast_schedule_next_run(sched.id))


@router.put(
    "/podcast/schedules/{schedule_id}",
    response_model=PodcastScheduleRead,
    dependencies=[Depends(verify_api_key)],
)
async def update_podcast_schedule_endpoint(
    schedule_id: UUID,
    payload: PodcastScheduleUpdate,
    session: Session = Depends(get_session),
):
    """Update a podcast schedule."""
    from app.worker.scheduler import (
        get_podcast_schedule_next_run,
        update_podcast_schedule,
    )

    sched = session.get(PodcastSchedule, schedule_id)
    if sched is None:
        raise HTTPException(status_code=404, detail="Podcast schedule not found")

    if payload.name is not None:
        sched.name = payload.name
    if payload.days is not None:
        if not payload.days:
            raise HTTPException(
                status_code=400, detail="At least one day must be specified"
            )
        sched.days = [d for d in payload.days]
    if payload.time is not None:
        parts = payload.time.strip().split(":")
        if len(parts) != 2:
            raise HTTPException(status_code=400, detail="time must be in HH:MM format")
        try:
            h, m = int(parts[0]), int(parts[1])
            if not (0 <= h <= 23 and 0 <= m <= 59):
                raise ValueError
        except ValueError:
            raise HTTPException(status_code=400, detail="time must be in HH:MM format")
        sched.time = payload.time
    if payload.timezone is not None:
        sched.timezone = payload.timezone
    if payload.enabled is not None:
        sched.enabled = payload.enabled

    sched.updated_at = datetime.utcnow()
    session.add(sched)
    session.commit()
    session.refresh(sched)

    update_podcast_schedule()

    return _schedule_to_read(sched, get_podcast_schedule_next_run(sched.id))


@router.delete(
    "/podcast/schedules/{schedule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(verify_api_key)],
)
async def delete_podcast_schedule(
    schedule_id: UUID,
    session: Session = Depends(get_session),
):
    """Delete a podcast schedule."""
    from app.worker.scheduler import update_podcast_schedule

    sched = session.get(PodcastSchedule, schedule_id)
    if sched is None:
        raise HTTPException(status_code=404, detail="Podcast schedule not found")

    session.delete(sched)
    session.commit()

    update_podcast_schedule()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/podcast/schedules/{schedule_id}/trigger",
    response_model=PodcastTriggerResponse,
    dependencies=[Depends(verify_api_key)],
)
async def trigger_podcast_schedule(
    schedule_id: UUID,
    session: Session = Depends(get_session),
):
    """Manually trigger podcast generation for a specific schedule."""
    sched = session.get(PodcastSchedule, schedule_id)
    if sched is None:
        raise HTTPException(status_code=404, detail="Podcast schedule not found")

    try:
        episode_id = podcast_service.generate_episode_for_schedule(schedule_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)[:300]) from exc

    if episode_id is None:
        raise HTTPException(
            status_code=409,
            detail="No eligible digests found since last podcast generation",
        )

    episode = session.get(PodcastEpisode, episode_id)
    if episode is None:
        raise HTTPException(status_code=500, detail="Episode created but not found")

    return PodcastTriggerResponse(
        episode_id=episode.id,
        digest_ids=episode.digest_ids or [],
        status=episode.status,
        message=f"Podcast generation queued for schedule '{sched.name}'",
    )
