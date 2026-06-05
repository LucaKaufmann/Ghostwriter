"""Digest management and download endpoints."""

import logging
import os
import posixpath
import re
import zipfile
from datetime import datetime
from typing import Literal
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, Response
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlmodel import Session, select

from app.core.config import Settings, get_settings
from app.core.database import get_session
from app.core.security import get_current_user, security, verify_api_key
from app.models.client_config import ClientConfig
from app.models.digest import Digest, DigestArticle, DigestRead
from app.models.podcast_episode import PodcastEpisode
from app.services.content_processor import ExtractedArticle
from app.services.digest_content_formatter import format_digest_content_to_html
from app.services.pdf_generator import PdfGenerator
from app.services.podcast_service import podcast_service
from app.services.reader_service import (
    DocumentTooLargeError,
    NonHtmlContentError,
    fetch_html_document,
)
from app.worker.bindery import generate_digest

logger = logging.getLogger(__name__)

router = APIRouter()


def _epub_media_type_from_name(name: str) -> str:
    lowered = name.lower()
    if lowered.endswith(".jpg") or lowered.endswith(".jpeg"):
        return "image/jpeg"
    if lowered.endswith(".webp"):
        return "image/webp"
    if lowered.endswith(".gif"):
        return "image/gif"
    return "image/png"


class TriggerRequest(BaseModel):
    """Request to manually trigger a digest."""

    period: Literal["morning", "noon", "evening", "manual"] = "manual"


class TriggerResponse(BaseModel):
    """Response from digest trigger."""

    id: UUID | None
    status: str
    message: str


class DigestProgress(BaseModel):
    """Progress information for a digest."""

    total_feeds: int
    feeds_fetched: int
    total_articles: int
    articles_enriched: int


class DigestStatusResponse(BaseModel):
    """Detailed status response for a digest job."""

    id: UUID
    status: str
    stage: str | None
    progress: DigestProgress
    started_at: datetime
    eta_seconds: int | None = None


class NewDigestsResponse(BaseModel):
    """Response for checking new digests."""

    has_new: bool
    count: int
    digests: list[DigestRead]


class DigestArticleRead(BaseModel):
    """Schema for reading a digest article with content."""

    id: UUID
    title: str
    url: str
    mode: str
    word_count: int
    content: str
    content_html: str
    author: str | None
    feed_title: str
    sort_order: int
    ai_failed: bool
    content_type: str = "article"


class DigestArticlesResponse(BaseModel):
    """Response for fetching all articles in a digest."""

    digest_id: UUID
    article_count: int
    articles: list[DigestArticleRead]


class DigestArticleSourceResponse(BaseModel):
    """Raw upstream HTML for an article (used by the web reader)."""

    digest_id: UUID
    article_id: UUID
    url: str
    final_url: str
    content_type: str | None = None
    fetched_at: datetime
    size_bytes: int
    html: str


def _available_formats(pdf_enabled: bool) -> list[str]:
    return ["epub", "pdf"] if pdf_enabled else ["epub"]


def _pdf_enabled(session: Session) -> bool:
    config = session.exec(select(ClientConfig)).first()
    return bool(config.pdf_enabled) if config else False


def _pdf_page_size(session: Session) -> str:
    config = session.exec(select(ClientConfig)).first()
    if not config or not config.pdf_page_size:
        return "A4"
    value = config.pdf_page_size.strip()
    if value in ("A4", "Letter", "A5"):
        return value
    return "A4"


def _to_digest_read(digest: Digest, pdf_enabled: bool) -> DigestRead:
    return DigestRead(
        id=digest.id,
        filename=digest.filename,
        period=digest.period,
        status=digest.status,
        stage=digest.stage,
        article_count=digest.article_count,
        error_message=digest.error_message,
        created_at=digest.created_at,
        completed_at=digest.completed_at,
        downloaded_at=digest.downloaded_at,
        total_feeds=digest.total_feeds,
        feeds_fetched=digest.feeds_fetched,
        total_articles=digest.total_articles,
        articles_enriched=digest.articles_enriched,
        available_formats=_available_formats(pdf_enabled),
    )


def _one_off_episode_for_digest(
    session: Session,
    digest_id: UUID,
) -> PodcastEpisode | None:
    digest_id_str = str(digest_id)
    episodes = session.exec(
        select(PodcastEpisode).where(PodcastEpisode.trigger == "one_off")
    ).all()
    return next(
        (episode for episode in episodes if digest_id_str in (episode.digest_ids or [])),
        None,
    )


async def _ensure_digest_access(
    *,
    session: Session,
    digest_id: UUID,
    request: Request,
    credentials: HTTPAuthorizationCredentials | None,
) -> None:
    episode = _one_off_episode_for_digest(session, digest_id)
    if episode is None:
        if podcast_service.is_one_off_digest(session, digest_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Digest not found",
            )
        return

    current_user = await get_current_user(request, credentials, session)
    if episode.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Digest not found",
        )


@router.post("/trigger", response_model=TriggerResponse, dependencies=[Depends(verify_api_key)])
async def trigger_digest(
    request: TriggerRequest,
) -> TriggerResponse:
    """
    Manually trigger a digest generation.

    Returns 409 Conflict if a job is already running.
    """
    logger.info("Manual digest trigger requested", extra={"period": request.period})
    digest_id = await generate_digest(request.period)

    if digest_id is None:
        logger.warning("Manual digest trigger blocked (job already running)")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A digest job is already running. Please wait for it to complete.",
        )

    logger.info(
        "Manual digest trigger started",
        extra={"period": request.period, "digest_id": str(digest_id)},
    )
    return TriggerResponse(
        id=digest_id,
        status="started",
        message=f"Digest generation started for period: {request.period}",
    )


@router.get("", response_model=list[DigestRead], dependencies=[Depends(verify_api_key)])
async def list_digests(
    session: Session = Depends(get_session),
    limit: int = 20,
    offset: int = 0,
    since: datetime | None = Query(default=None, description="Filter digests created after this datetime (UTC)"),
    status_filter: str | None = Query(default=None, alias="status", description="Filter by status (completed, failed, processing)"),
    period: str | None = Query(default=None, description="Filter by period (morning, noon, evening, manual)"),
) -> list[DigestRead]:
    """
    List available digests.

    Returns digests ordered by creation date, newest first.
    Supports filtering by creation date, status, and period.
    """
    statement = podcast_service.exclude_one_off_digests(select(Digest))

    # Apply filters
    if since:
        statement = statement.where(Digest.created_at > since)
    if status_filter:
        statement = statement.where(Digest.status == status_filter)
    if period:
        statement = statement.where(Digest.period == period)

    statement = (
        statement
        .order_by(Digest.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    digests = list(session.exec(statement).all())
    pdf_enabled = _pdf_enabled(session)
    return [_to_digest_read(digest, pdf_enabled) for digest in digests]


@router.get("/new", response_model=NewDigestsResponse, dependencies=[Depends(verify_api_key)])
async def get_new_digests(
    session: Session = Depends(get_session),
    last_known_id: UUID | None = Query(default=None, description="ID of the last digest the client knows about"),
    since: datetime | None = Query(default=None, description="Return digests created after this datetime (UTC)"),
) -> NewDigestsResponse:
    """
    Check for new completed digests.

    Returns digests that are newer than the client's last known digest.
    Use either last_known_id OR since parameter to specify the cutoff.

    This endpoint is optimized for clients polling for new digests.
    """
    statement = podcast_service.exclude_one_off_digests(
        select(Digest).where(Digest.status == "completed")
    )

    if last_known_id:
        # Get the creation time of the last known digest
        last_digest = session.get(Digest, last_known_id)
        if last_digest:
            statement = statement.where(Digest.created_at > last_digest.created_at)
    elif since:
        statement = statement.where(Digest.created_at > since)

    statement = statement.order_by(Digest.created_at.desc())
    digests = list(session.exec(statement).all())

    pdf_enabled = _pdf_enabled(session)
    return NewDigestsResponse(
        has_new=len(digests) > 0,
        count=len(digests),
        digests=[_to_digest_read(digest, pdf_enabled) for digest in digests],
    )


@router.get("/latest", response_model=DigestRead, dependencies=[Depends(verify_api_key)])
async def get_latest_digest(
    session: Session = Depends(get_session),
) -> DigestRead:
    """
    Get the most recent completed digest.

    Returns 404 if no completed digests exist.
    """
    statement = (
        podcast_service.exclude_one_off_digests(
            select(Digest).where(Digest.status == "completed")
        )
        .order_by(Digest.completed_at.desc())
        .limit(1)
    )
    digest = session.exec(statement).first()

    if not digest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No completed digests found",
        )

    return _to_digest_read(digest, _pdf_enabled(session))


@router.get("/{digest_id}/status", response_model=DigestStatusResponse, dependencies=[Depends(verify_api_key)])
async def get_digest_status(
    digest_id: UUID,
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    session: Session = Depends(get_session),
) -> DigestStatusResponse:
    """
    Get the status of a digest job.

    Useful for polling progress during generation.
    """
    digest = session.get(Digest, digest_id)

    if not digest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Digest not found",
        )
    await _ensure_digest_access(
        session=session,
        digest_id=digest_id,
        request=request,
        credentials=credentials,
    )

    # Calculate ETA based on progress (rough estimate)
    eta = None
    if digest.status == "processing" and digest.articles_enriched > 0:
        # Estimate based on average time per article
        remaining = digest.total_articles - digest.articles_enriched
        avg_time = 5  # seconds per article (rough estimate)
        eta = remaining * avg_time

    return DigestStatusResponse(
        id=digest.id,
        status=digest.status,
        stage=digest.stage,
        progress=DigestProgress(
            total_feeds=digest.total_feeds,
            feeds_fetched=digest.feeds_fetched,
            total_articles=digest.total_articles,
            articles_enriched=digest.articles_enriched,
        ),
        started_at=digest.created_at,
        eta_seconds=eta,
    )


@router.get("/{digest_id}/articles", response_model=DigestArticlesResponse, dependencies=[Depends(verify_api_key)])
async def get_digest_articles(
    digest_id: UUID,
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    session: Session = Depends(get_session),
) -> DigestArticlesResponse:
    """
    Get all articles for a digest with their content.

    Returns article content for syncing to clients.
    """
    # Verify digest exists
    digest = session.get(Digest, digest_id)
    if not digest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Digest not found",
        )
    await _ensure_digest_access(
        session=session,
        digest_id=digest_id,
        request=request,
        credentials=credentials,
    )

    # Query articles
    statement = (
        select(DigestArticle)
        .where(DigestArticle.digest_id == digest_id)
        .order_by(DigestArticle.sort_order)
    )
    articles = list(session.exec(statement).all())

    return DigestArticlesResponse(
        digest_id=digest_id,
        article_count=len(articles),
        articles=[
            DigestArticleRead(
                id=article.id,
                title=article.title,
                url=article.url,
                mode=article.mode,
                word_count=article.word_count,
                content=article.content,
                content_html=format_digest_content_to_html(article.content),
                author=article.author,
                feed_title=article.feed_title,
                sort_order=article.sort_order,
                ai_failed=article.ai_failed,
                content_type=article.content_type,
            )
            for article in articles
        ],
    )


@router.get(
    "/{digest_id}/articles/{article_id}/source",
    response_model=DigestArticleSourceResponse,
    dependencies=[Depends(verify_api_key)],
)
async def get_digest_article_source(
    digest_id: UUID,
    article_id: UUID,
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> DigestArticleSourceResponse:
    """Fetch raw upstream HTML for a digest article (SSRF-safe)."""
    await _ensure_digest_access(
        session=session,
        digest_id=digest_id,
        request=request,
        credentials=credentials,
    )
    statement = (
        select(DigestArticle)
        .where(DigestArticle.id == article_id)
        .where(DigestArticle.digest_id == digest_id)
    )
    article = session.exec(statement).first()
    if not article:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")

    # For media content (podcasts, YouTube), return the stored digest content
    # directly instead of fetching upstream HTML which will fail for these URLs.
    if article.content_type in ("podcast", "youtube"):
        formatted_html = format_digest_content_to_html(article.content)
        return DigestArticleSourceResponse(
            digest_id=digest_id,
            article_id=article_id,
            url=article.url,
            final_url=article.url,
            content_type=f"text/html; ghostwriter-{article.content_type}",
            fetched_at=datetime.utcnow(),
            size_bytes=len(formatted_html.encode("utf-8")),
            html=formatted_html,
        )

    try:
        doc = await fetch_html_document(article.url, settings=settings)
    except ValueError as e:
        # validate_public_url failures
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except NonHtmlContentError as e:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(e))
    except DocumentTooLargeError as e:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(e))
    except httpx.TimeoutException:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Upstream fetch timed out")
    except httpx.HTTPError as e:
        logger.warning("Upstream fetch failed", extra={"url": article.url, "error": repr(e)})
        # Fall back to stored content if available (e.g. media articles
        # with content_type not yet set to podcast/youtube)
        if article.content:
            formatted_html = format_digest_content_to_html(article.content)
            return DigestArticleSourceResponse(
                digest_id=digest_id,
                article_id=article_id,
                url=article.url,
                final_url=article.url,
                content_type="text/html; ghostwriter-fallback",
                fetched_at=datetime.utcnow(),
                size_bytes=len(formatted_html.encode("utf-8")),
                html=formatted_html,
            )
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Upstream fetch failed")

    return DigestArticleSourceResponse(
        digest_id=digest_id,
        article_id=article_id,
        url=article.url,
        final_url=doc.final_url,
        content_type=doc.content_type,
        fetched_at=doc.fetched_at,
        size_bytes=doc.size_bytes,
        html=doc.html,
    )


@router.get("/{digest_id}/cover", dependencies=[Depends(verify_api_key)])
async def get_digest_cover(
    digest_id: UUID,
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
) -> Response:
    """Extract and return embedded cover image from a digest EPUB."""
    digest = session.get(Digest, digest_id)
    if not digest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Digest not found",
        )
    await _ensure_digest_access(
        session=session,
        digest_id=digest_id,
        request=request,
        credentials=credentials,
    )

    if not digest.filename:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Digest has no EPUB file",
        )

    file_path = os.path.join(settings.output_dir, digest.filename)
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Digest file not found",
        )

    try:
        with zipfile.ZipFile(file_path, "r") as zf:
            names = zf.namelist()
            cover_xhtml = next((name for name in names if name.endswith("cover.xhtml")), None)
            if not cover_xhtml:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No cover page found in digest",
                )

            cover_html = zf.read(cover_xhtml).decode("utf-8", errors="ignore")
            match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', cover_html, re.IGNORECASE)
            if not match:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No embedded cover image found",
                )

            src = match.group(1).split("?")[0].strip()
            cover_entry = posixpath.normpath(
                posixpath.join(posixpath.dirname(cover_xhtml), src)
            )
            if cover_entry.startswith("../") or cover_entry == "..":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid cover image path in digest",
                )
            if cover_entry not in names:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Cover image entry not found in digest",
                )

            payload = zf.read(cover_entry)
            return Response(
                content=payload,
                media_type=_epub_media_type_from_name(cover_entry),
                headers={"Cache-Control": "public, max-age=300"},
            )
    except zipfile.BadZipFile as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Digest EPUB is invalid",
        ) from exc


def _derive_pdf_filename(epub_filename: str) -> str:
    if "." in epub_filename:
        stem, _ = epub_filename.rsplit(".", 1)
        return f"{stem}.pdf"
    return f"{epub_filename}.pdf"


def _load_digest_articles(session: Session, digest_id: UUID) -> list[DigestArticle]:
    statement = (
        select(DigestArticle)
        .where(DigestArticle.digest_id == digest_id)
        .order_by(DigestArticle.sort_order)
    )
    return list(session.exec(statement).all())


def _to_extracted_articles(articles: list[DigestArticle]) -> list[ExtractedArticle]:
    extracted: list[ExtractedArticle] = []
    for article in articles:
        extracted.append(
            ExtractedArticle(
                guid=str(article.id),
                url=article.url,
                title=article.title,
                content=article.content,
                author=article.author,
                word_count=article.word_count,
                is_summary=article.mode in ("summarized", "summarize"),
                ai_failed=article.ai_failed,
                processing_ms=article.processing_ms,
                feed_title=article.feed_title,
                content_type=article.content_type or "article",
            )
        )
    return extracted


@router.get("/{digest_id}/download", dependencies=[Depends(verify_api_key)])
async def download_digest_by_id(
    digest_id: UUID,
    request: Request,
    format: Literal["epub", "pdf"] = Query(default="epub"),
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
) -> FileResponse:
    """Download a digest by ID in EPUB or PDF format."""
    digest = session.get(Digest, digest_id)
    if not digest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Digest not found",
        )
    await _ensure_digest_access(
        session=session,
        digest_id=digest_id,
        request=request,
        credentials=credentials,
    )

    if digest.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Digest is not completed yet",
        )

    target_filename = digest.filename
    media_type = "application/epub+zip"

    pdf_enabled = _pdf_enabled(session)

    if format == "pdf":
        if not pdf_enabled:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="PDF downloads are disabled in settings",
            )

        target_filename = _derive_pdf_filename(digest.filename)
        media_type = "application/pdf"

    file_path = os.path.join(settings.output_dir, target_filename)

    if format == "pdf" and not os.path.exists(file_path):
        articles = _load_digest_articles(session, digest_id)
        if not articles:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Digest has no article content to render PDF",
            )

        pdf_generator = PdfGenerator(settings=settings)
        pdf_generator.generate(
            articles=_to_extracted_articles(articles),
            period=digest.period,
            date=digest.created_at,
            page_size=_pdf_page_size(session),
            output_filename=target_filename,
        )

    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Digest file not found",
        )

    from app.services import activity_tracker
    activity_tracker.record_download()

    if not digest.downloaded_at:
        digest.downloaded_at = datetime.utcnow()
        session.add(digest)
        session.commit()

    return FileResponse(
        path=file_path,
        filename=target_filename,
        media_type=media_type,
    )


@router.get("/{filename}", dependencies=[Depends(verify_api_key)])
async def download_digest(
    filename: str,
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
) -> FileResponse:
    """
    Download a digest EPUB file.

    The filename should be the EPUB filename (e.g., 2024-10-24_morning.epub).
    This also records download activity for inactivity tracking.
    """
    # Validate filename to prevent path traversal
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filename",
        )

    if not filename.endswith(".epub"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only EPUB files can be downloaded",
        )

    file_path = os.path.join(settings.output_dir, filename)

    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Digest file not found",
        )

    # Record download activity and mark digest as downloaded
    from app.services import activity_tracker
    activity_tracker.record_download()

    # Mark the specific digest as downloaded
    digest = session.exec(select(Digest).where(Digest.filename == filename)).first()
    if digest:
        await _ensure_digest_access(
            session=session,
            digest_id=digest.id,
            request=request,
            credentials=credentials,
        )
    if digest and not digest.downloaded_at:
        digest.downloaded_at = datetime.utcnow()
        session.add(digest)
        session.commit()

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/epub+zip",
    )


@router.delete("/{filename}", dependencies=[Depends(verify_api_key)])
async def delete_digest(
    filename: str,
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
) -> dict:
    """
    Delete a digest EPUB file.

    This also removes the database record.
    """
    # Validate filename
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filename",
        )

    # Find and delete database record
    statement = select(Digest).where(Digest.filename == filename)
    digest = session.exec(statement).first()

    if digest:
        await _ensure_digest_access(
            session=session,
            digest_id=digest.id,
            request=request,
            credentials=credentials,
        )
        session.delete(digest)
        session.commit()

    # Delete file
    file_path = os.path.join(settings.output_dir, filename)
    if os.path.exists(file_path):
        os.remove(file_path)
        return {"status": "deleted", "filename": filename}

    if not digest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Digest not found",
        )

    return {"status": "deleted", "filename": filename, "note": "File already removed"}
