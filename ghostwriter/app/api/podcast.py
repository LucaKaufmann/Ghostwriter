"""Podcast digest API endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from typing import Iterator
from uuid import UUID
import logging
import mimetypes
import os
import xml.etree.ElementTree as ET

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError
from sqlmodel import Session, select

from app.core.config import get_settings
from app.core.database import get_session
from app.core.security import security, verify_api_key
from app.models.article_feedback import ArticleFeedbackRead, ArticleFeedbackUpsert
from app.models.digest import DigestArticle
from app.models.podcast_episode import PodcastEpisode, PodcastEpisodeArticleRead
from app.models.podcast_preferences import PodcastPreferencesRead, PodcastPreferencesUpdate
from app.services.podcast_service import podcast_service

router = APIRouter()
logger = logging.getLogger(__name__)


class PodcastEpisodeStatusRead(BaseModel):
    """Episode status payload with downloadable URLs."""

    id: UUID
    digest_id: UUID
    status: str
    audio_size_bytes: int | None = None
    duration_seconds: int | None = None
    article_count: int
    generation_cost_cents: int | None = None
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
    stream_url: str | None = None
    download_url: str | None = None


class PodcastEpisodeDetailRead(PodcastEpisodeStatusRead):
    """Detailed episode payload including script and source article list."""

    script: str | None = None
    article_ids: list[str]
    articles: list[PodcastEpisodeArticleRead]


class PodcastTriggerResponse(BaseModel):
    """Response for manual/automatic trigger endpoints."""

    episode_id: UUID
    status: str
    message: str


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

    return PodcastEpisodeStatusRead(
        id=episode.id,
        digest_id=episode.digest_id,
        status=episode.status,
        audio_size_bytes=episode.audio_size_bytes,
        duration_seconds=episode.duration_seconds,
        article_count=episode.article_count,
        generation_cost_cents=episode.generation_cost_cents,
        error_message=episode.error_message,
        created_at=episode.created_at,
        completed_at=episode.completed_at,
        stream_url=str(request.base_url).rstrip("/") + stream_url,
        download_url=str(request.base_url).rstrip("/") + download_url,
    )


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


def _read_range(path: Path, start: int, end: int, chunk_size: int = 64 * 1024) -> Iterator[bytes]:
    with path.open("rb") as fp:
        fp.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            data = fp.read(min(chunk_size, remaining))
            if not data:
                break
            remaining -= len(data)
            yield data


async def _authorize_standard_or_feed_token(
    request: Request,
    session: Session,
    feed_token: str | None,
) -> None:
    if feed_token:
        prefs = podcast_service.get_preferences_by_feed_token(session, feed_token)
        if prefs is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid feed token",
            )
        return

    credentials = await security(request)
    await verify_api_key(
        request=request,
        credentials=credentials,
        settings=get_settings(),
    )


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
    dependencies=[Depends(verify_api_key)],
)
async def get_podcast_preferences(session: Session = Depends(get_session)):
    """Get podcast preferences for the singleton user."""
    user_id = podcast_service.resolve_user_id(session)
    prefs = podcast_service.get_or_create_preferences(session, user_id=user_id)
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
        style=prefs.style,
        tts_provider=prefs.tts_provider,
        openai_tts_model=prefs.openai_tts_model,
        elevenlabs_model_id=prefs.elevenlabs_model_id,
        elevenlabs_output_format=prefs.elevenlabs_output_format,
        host_a_voice=prefs.host_a_voice,
        host_b_voice=prefs.host_b_voice,
        podcast_feed_enabled=prefs.podcast_feed_enabled,
        podcast_feed_title=prefs.podcast_feed_title,
        podcast_feed_description=prefs.podcast_feed_description,
        podcast_feed_artwork_path=prefs.podcast_feed_artwork_path,
        updated_at=prefs.updated_at,
    )


@router.put(
    "/podcast/preferences",
    response_model=PodcastPreferencesRead,
    dependencies=[Depends(verify_api_key)],
)
async def update_podcast_preferences(
    update: PodcastPreferencesUpdate,
    session: Session = Depends(get_session),
):
    """Update podcast preferences."""
    user_id = podcast_service.resolve_user_id(session)
    try:
        prefs = podcast_service.update_preferences(session, update, user_id=user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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
        style=prefs.style,
        tts_provider=prefs.tts_provider,
        openai_tts_model=prefs.openai_tts_model,
        elevenlabs_model_id=prefs.elevenlabs_model_id,
        elevenlabs_output_format=prefs.elevenlabs_output_format,
        host_a_voice=prefs.host_a_voice,
        host_b_voice=prefs.host_b_voice,
        podcast_feed_enabled=prefs.podcast_feed_enabled,
        podcast_feed_title=prefs.podcast_feed_title,
        podcast_feed_description=prefs.podcast_feed_description,
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
    deleted = podcast_service.delete_feedback(session, article_id=article_id, user_id=user_id)
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
    session: Session = Depends(get_session),
):
    """Manually queue podcast generation for one digest."""
    user_id = podcast_service.resolve_user_id(session)
    try:
        episode = podcast_service.queue_episode_generation(
            session,
            digest_id=digest_id,
            user_id=user_id,
            force=False,
        )
    except ValueError as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=409, detail=message) from exc

    return PodcastTriggerResponse(
        episode_id=episode.id,
        status=episode.status,
        message="Podcast generation queued",
    )


@router.get(
    "/digests/{digest_id}/podcast",
    response_model=DigestPodcastStatusResponse,
    dependencies=[Depends(verify_api_key)],
)
async def get_digest_podcast_status(
    digest_id: UUID,
    request: Request,
    session: Session = Depends(get_session),
):
    """Get podcast generation status for a digest."""
    try:
        episode = session.exec(
            select(PodcastEpisode).where(PodcastEpisode.digest_id == digest_id)
        ).first()
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
        raise HTTPException(status_code=404, detail="Podcast episode not found for digest")
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
    session: Session = Depends(get_session),
):
    """Retry failed podcast generation."""
    episode = session.get(PodcastEpisode, episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail="Podcast episode not found")
    if episode.status != "failed":
        raise HTTPException(status_code=409, detail="Only failed episodes can be retried")

    retried = podcast_service.queue_episode_generation(
        session,
        digest_id=episode.digest_id,
        user_id=episode.user_id,
        force=True,
    )
    return PodcastTriggerResponse(
        episode_id=retried.id,
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
    status_payload = _build_episode_status(request, episode)
    return PodcastEpisodeDetailRead(
        **status_payload.model_dump(),
        script=episode.script,
        article_ids=episode.article_ids,
        articles=_resolve_episode_articles(session, episode),
    )


@router.delete(
    "/podcast/episodes/{episode_id}",
    dependencies=[Depends(verify_api_key)],
)
async def delete_podcast_episode(
    episode_id: UUID,
    session: Session = Depends(get_session),
):
    """Delete one podcast episode and local audio artifact."""
    episode = session.get(PodcastEpisode, episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail="Podcast episode not found")

    if episode.audio_path and os.path.exists(episode.audio_path):
        try:
            os.remove(episode.audio_path)
        except OSError as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to delete audio file: {exc}",
            ) from exc

    session.delete(episode)
    session.commit()
    return {"status": "deleted"}


@router.get("/podcast/episodes/{episode_id}/stream")
async def stream_podcast_episode(
    episode_id: UUID,
    request: Request,
    token: str | None = Query(default=None),
    session: Session = Depends(get_session),
):
    """Stream podcast MP3 with byte-range support."""
    await _authorize_standard_or_feed_token(request, session, token)

    episode = session.get(PodcastEpisode, episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail="Podcast episode not found")
    if episode.status != "ready":
        raise HTTPException(status_code=409, detail="Podcast episode is not ready")
    if not episode.audio_path or not os.path.exists(episode.audio_path):
        raise HTTPException(status_code=404, detail="Audio file not found")

    audio_path = Path(episode.audio_path)
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
    await _authorize_standard_or_feed_token(request, session, token)

    episode = session.get(PodcastEpisode, episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail="Podcast episode not found")
    if episode.status != "ready":
        raise HTTPException(status_code=409, detail="Podcast episode is not ready")
    if not episode.audio_path or not os.path.exists(episode.audio_path):
        raise HTTPException(status_code=404, detail="Audio file not found")

    return FileResponse(
        episode.audio_path,
        media_type="audio/mpeg",
        filename=f"podcast-{episode_id}.mp3",
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

    episodes = session.exec(
        select(PodcastEpisode)
        .where(PodcastEpisode.status == "ready")
        .order_by(PodcastEpisode.created_at.desc())
        .limit(100)
    ).all()

    ET.register_namespace("itunes", "http://www.itunes.com/dtds/podcast-1.0.dtd")
    ET.register_namespace("content", "http://purl.org/rss/1.0/modules/content/")

    rss = ET.Element(
        "rss",
        {
            "version": "2.0",
            "xmlns:itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
            "xmlns:content": "http://purl.org/rss/1.0/modules/content/",
        },
    )
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = prefs.podcast_feed_title
    ET.SubElement(channel, "description").text = prefs.podcast_feed_description
    ET.SubElement(channel, "link").text = str(request.base_url).rstrip("/")
    ET.SubElement(channel, "language").text = "en-us"
    ET.SubElement(channel, "itunes:author").text = "Ghostwriter"
    ET.SubElement(channel, "itunes:explicit").text = "false"
    ET.SubElement(channel, "itunes:category", {"text": "Technology"})

    if prefs.podcast_feed_artwork_path and os.path.exists(prefs.podcast_feed_artwork_path):
        image_url = (
            str(request.base_url).rstrip("/")
            + "/api/podcast/feed/artwork"
            + f"?token={token}"
        )
        ET.SubElement(channel, "itunes:image", {"href": image_url})

    for index, episode in enumerate(episodes, start=1):
        item = ET.SubElement(channel, "item")
        created = episode.completed_at or episode.created_at
        created_local = created.date().isoformat()
        ET.SubElement(item, "title").text = f"Digest Podcast - {created_local}"

        article_titles = [article.title for article in _resolve_episode_articles(session, episode)]
        if article_titles:
            ET.SubElement(item, "description").text = "Includes: " + "; ".join(article_titles[:8])
        else:
            ET.SubElement(item, "description").text = "AI-generated digest podcast episode"

        ET.SubElement(item, "pubDate").text = _to_rfc2822(created)
        enclosure_url = (
            str(request.base_url).rstrip("/")
            + f"/api/podcast/episodes/{episode.id}/download?token={token}"
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
        ET.SubElement(item, "itunes:duration").text = _format_duration(episode.duration_seconds)
        ET.SubElement(item, "itunes:episode").text = str(index)
        ET.SubElement(item, "guid").text = f"podcast-episode-{episode.id}"

    xml_bytes = ET.tostring(rss, encoding="utf-8", xml_declaration=True)
    return Response(content=xml_bytes, media_type="application/rss+xml; charset=utf-8")


@router.get(
    "/podcast/feed/info",
    response_model=PodcastFeedInfoResponse,
    dependencies=[Depends(verify_api_key)],
)
async def get_podcast_feed_info(
    request: Request,
    session: Session = Depends(get_session),
):
    """Return feed URL and setup instructions for podcast apps."""
    user_id = podcast_service.resolve_user_id(session)
    prefs = podcast_service.get_or_create_preferences(session, user_id=user_id)
    base_url = str(request.base_url).rstrip("/")
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
    prefs = podcast_service.get_preferences_by_feed_token(session, token)
    if prefs is None:
        raise HTTPException(status_code=401, detail="Invalid feed token")
    if not prefs.podcast_feed_artwork_path:
        raise HTTPException(status_code=404, detail="Feed artwork not configured")
    artwork_path = Path(prefs.podcast_feed_artwork_path)
    if not artwork_path.exists():
        raise HTTPException(status_code=404, detail="Feed artwork not found")
    media_type = mimetypes.guess_type(str(artwork_path))[0] or "image/jpeg"
    return FileResponse(artwork_path, media_type=media_type)


@router.post(
    "/podcast/feed/artwork",
    response_model=PodcastArtworkUploadResponse,
    dependencies=[Depends(verify_api_key)],
)
async def upload_podcast_feed_artwork(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    """Upload custom podcast feed artwork (minimum 1400x1400)."""
    try:
        from PIL import Image
    except Exception as exc:  # pragma: no cover - Pillow is an install dependency.
        raise HTTPException(status_code=500, detail=f"Pillow unavailable: {exc}") from exc

    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Artwork file must be an image")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Artwork file is empty")

    try:
        from io import BytesIO

        image = Image.open(BytesIO(data))
        width, height = image.size
        image.verify()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid artwork image: {exc}") from exc

    if width < 1400 or height < 1400:
        raise HTTPException(status_code=400, detail="Artwork must be at least 1400x1400")

    ext = (image.format or "JPEG").lower()
    if ext == "jpeg":
        ext = "jpg"

    user_id = podcast_service.resolve_user_id(session)
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
