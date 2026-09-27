"""Feed management endpoints."""

import logging
import os
import re
import time
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import Session, select

from app.core.database import get_session
from app.core.logging import digest_logger
from app.core.security import verify_api_key
from app.models.feed import Feed, FeedCreate, FeedRead, FeedSync, FeedUpdate
from app.models.seen_article import SeenArticle
from app.services import activity_tracker, feed_sync
from app.services.outbound_fetch import validate_public_url_bounded

logger = logging.getLogger(__name__)

_YOUTUBE_CHANNEL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?youtube\.com/"
    r"(?:@[\w.-]+|channel/[\w-]+|c/[\w-]+|user/[\w-]+|feeds/videos\.xml)",
    re.IGNORECASE,
)

_AUDIO_EXTENSIONS = frozenset({
    ".mp3", ".m4a", ".ogg", ".opus", ".wav", ".flac", ".aac", ".wma",
})

router = APIRouter()


def _if_match(value: str | None) -> int | None:
    if value is None:
        return None
    if not re.fullmatch(r'"(?:0|[1-9][0-9]*)"', value):
        raise HTTPException(422, detail="If-Match must be a quoted decimal version")
    version = int(value[1:-1])
    if not feed_sync.validate_version(version):
        raise HTTPException(422, detail="Invalid feed version")
    return version


@router.get("/changes-v2", dependencies=[Depends(verify_api_key)])
async def get_changes_v2(
    since_version: int | None = None,
    server_instance_id: UUID | None = None,
    session: Session = Depends(get_session),
) -> dict:
    if since_version is not None and not feed_sync.validate_version(since_version):
        raise HTTPException(422, detail="Invalid feed cursor")
    if since_version is not None and server_instance_id is None:
        raise HTTPException(422, detail="server_instance_id is required with since_version")
    feed_sync._begin_write(session)
    try:
        clock = feed_sync._clock(session)
        if server_instance_id is not None and str(server_instance_id) != clock.server_instance_id:
            raise feed_sync.server_changed()
        if since_version is not None and since_version > clock.version:
            raise feed_sync.server_changed()
        statement = select(Feed).where(func.substr(Feed.url, 1, 12) != "synthetic://")
        if since_version is not None:
            statement = statement.where(Feed.version > since_version)
        changes = [feed_sync.snapshot(feed) for feed in session.exec(statement.order_by(Feed.version)).all()]
        result = {"server_instance_id": clock.server_instance_id,
                  "server_version": clock.version, "changes": changes}
        session.commit()
        activity_tracker.record_feed_sync()
        return result
    except BaseException:
        session.rollback()
        raise


@router.post("/mutations-v2", dependencies=[Depends(verify_api_key)])
async def mutate_v2(body: dict, session: Session = Depends(get_session)) -> dict:
    try:
        instance_id = str(UUID(body["server_instance_id"]))
        items = body["mutations"]
        if not isinstance(items, list) or len(items) > 100:
            raise ValueError
        op_ids = [str(UUID(item["op_id"])) for item in items]
        if len(op_ids) != len(set(op_ids)):
            raise ValueError
    except (KeyError, ValueError, TypeError, AttributeError):
        raise HTTPException(422, detail="Invalid mutation envelope") from None
    # Bind before processing even an empty batch; a replacement rejects all writes.
    feed_sync._begin_write(session)
    try:
        clock = feed_sync._clock(session)
        if clock.server_instance_id != instance_id:
            raise feed_sync.server_changed()
        session.commit()
    except BaseException:
        session.rollback()
        raise
    results = []
    for item in items:
        results.append(await feed_sync.mutate_one(session, instance_id, item))
    return {"server_instance_id": instance_id, "results": results}


async def _validate_feed_url(url: str) -> None:
    try:
        await validate_public_url_bounded(url)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid feed URL '{url}': {exc}",
        ) from exc
    except TimeoutError as exc:
        raise HTTPException(504, detail="Feed URL validation timed out") from exc


class SyncResponse(BaseModel):
    """Response for feed sync operation."""

    synced: int
    created: int
    updated: int
    unchanged: int


class FeedTombstone(BaseModel):
    """Tombstone for a deleted feed."""

    url: str
    deleted_at: datetime


class FeedChangesResponse(BaseModel):
    """Response for feed changes (incremental sync)."""

    feeds: list[FeedRead]           # Active/updated feeds
    tombstones: list[FeedTombstone]  # Deleted feeds
    server_timestamp: datetime       # For next sync request


@router.get("", response_model=list[FeedRead], dependencies=[Depends(verify_api_key)])
async def list_feeds(
    session: Session = Depends(get_session),
) -> list[Feed]:
    """
    List all configured feeds.

    Returns all feeds regardless of active status (excludes tombstoned feeds).
    """
    statement = select(Feed).where(
        Feed.deleted_at == None,  # noqa: E711
        func.substr(Feed.url, 1, 12) != "synthetic://",
    ).order_by(Feed.title)
    return list(session.exec(statement).all())


@router.get("/changes", response_model=FeedChangesResponse, dependencies=[Depends(verify_api_key)])
async def get_feed_changes(
    since: Optional[datetime] = Query(None, description="Get changes since this timestamp"),
    session: Session = Depends(get_session),
) -> FeedChangesResponse:
    """
    Get feed changes for incremental sync.

    If since is not provided, returns all active feeds (initial sync).
    If since is provided, returns feeds updated after that time and tombstones
    for deleted feeds.

    This endpoint is designed for bi-directional sync with the Android app.
    """
    server_timestamp = datetime.utcnow()

    if since is None:
        # Initial sync: return all active (non-deleted) feeds
        statement = select(Feed).where(
            Feed.deleted_at == None,  # noqa: E711
            func.substr(Feed.url, 1, 12) != "synthetic://",
        ).order_by(Feed.title)
        feeds = list(session.exec(statement).all())
        return FeedChangesResponse(
            feeds=feeds,
            tombstones=[],
            server_timestamp=server_timestamp,
        )

    # Incremental sync: return changed feeds and tombstones
    # Get feeds updated since the given timestamp (excluding tombstoned)
    feeds_statement = select(Feed).where(
        Feed.updated_at > since,
        Feed.deleted_at == None,  # noqa: E711
        func.substr(Feed.url, 1, 12) != "synthetic://",
    ).order_by(Feed.title)
    feeds = list(session.exec(feeds_statement).all())

    # Get tombstones created since the given timestamp
    tombstones_statement = select(Feed).where(
        Feed.deleted_at != None,  # noqa: E711
        Feed.deleted_at > since,
        func.substr(Feed.url, 1, 12) != "synthetic://",
    )
    tombstoned_feeds = session.exec(tombstones_statement).all()
    tombstones = [
        FeedTombstone(url=f.url, deleted_at=f.deleted_at)
        for f in tombstoned_feeds
        if f.deleted_at is not None
    ]

    return FeedChangesResponse(
        feeds=feeds,
        tombstones=tombstones,
        server_timestamp=server_timestamp,
    )


@router.post("/sync", response_model=SyncResponse, dependencies=[Depends(verify_api_key)])
async def sync_feeds(
    feeds: list[FeedSync],
    session: Session = Depends(get_session),
) -> SyncResponse:
    """Accept exact legacy snapshots as read-safe no-ops.

    Any create, changed feed, or tombstone rejects the whole batch with an
    upgrade-required response. Versioned edits use ``/mutations-v2``.
    """
    t0 = time.perf_counter()

    created = 0
    updated = 0
    unchanged = 0

    # Validate URLs before applying changes
    for feed_data in feeds:
        await _validate_feed_url(feed_data.url)

    # Compare against current rows after the await, under the short writer gate.
    # No DNS work runs while that gate is held.
    feed_sync._begin_write(session)
    try:
        existing_feeds = {f.url: f for f in session.exec(select(Feed)).all()}
        for feed_data in feeds:
            feed = existing_feeds.get(feed_data.url)
            if (feed is None or feed.deleted_at is not None or
                feed_data.url.startswith("synthetic://") or
                any(getattr(feed, key) != getattr(feed_data, key)
                    for key in feed_sync.SYNC_FIELDS)):
                raise HTTPException(409, detail={"code": "legacy_write_requires_upgrade"})
            unchanged += 1
        session.commit()
    except BaseException:
        session.rollback()
        raise

    activity_tracker.record_feed_sync()

    duration_ms = (time.perf_counter() - t0) * 1000
    digest_logger.sync_feed_push(
        feed_count=len(feeds),
        created=created,
        updated=updated,
        unchanged=unchanged,
        duration_ms=duration_ms,
    )

    return SyncResponse(
        synced=len(feeds),
        created=created,
        updated=updated,
        unchanged=unchanged,
    )


class FeedCheckRequest(BaseModel):
    """Request to check a feed URL type."""
    url: str


class FeedCheckResponse(BaseModel):
    """Response indicating the type of feed a URL points to."""
    feed_type: str  # "article", "podcast", or "youtube"


def _is_audio_url(url: str | None) -> bool:
    """Check if a URL points to an audio file."""
    if not url:
        return False
    path = url.split("?")[0].split("#")[0]
    _, ext = os.path.splitext(path)
    return ext.lower() in _AUDIO_EXTENSIONS


def _is_youtube_url(url: str) -> bool:
    """Check if a URL is any kind of YouTube URL (video or channel)."""
    from app.services.youtube_service import YouTubeService
    return YouTubeService.is_youtube_url(url) or bool(_YOUTUBE_CHANNEL_RE.search(url))


@router.post("/check-url", response_model=FeedCheckResponse, dependencies=[Depends(verify_api_key)])
async def check_feed_url(req: FeedCheckRequest) -> FeedCheckResponse:
    """
    Classify a URL as article, podcast, or youtube feed.

    YouTube URLs are detected instantly via regex. For other URLs, the feed
    is fetched and entries are checked for audio enclosures.
    """
    url = req.url.strip()
    if not url:
        return FeedCheckResponse(feed_type="article")

    # YouTube: instant, no network needed
    if _is_youtube_url(url):
        return FeedCheckResponse(feed_type="youtube")

    # Fetch the feed and check entries for audio enclosures
    try:
        from app.services.content_processor import ContentProcessor
        processor = ContentProcessor()
        entries = await processor.parse_feed(url, max_entries=5)

        if entries:
            audio_count = sum(1 for e in entries if _is_audio_url(e.content_url))
            if audio_count >= len(entries) / 2:
                return FeedCheckResponse(feed_type="podcast")
    except Exception:
        logger.debug("Feed check failed for %s, defaulting to article", url, exc_info=True)

    return FeedCheckResponse(feed_type="article")


@router.post("", response_model=FeedRead, dependencies=[Depends(verify_api_key)])
async def create_feed(
    feed_data: FeedCreate,
    if_match: str | None = Header(None),
    session: Session = Depends(get_session),
) -> Feed:
    """
    Create a new feed.

    If a soft-deleted feed with the same URL exists, it is restored with
    the new settings. Returns 409 Conflict if an active feed already exists.
    """
    if not feed_sync.validate_fields(feed_data.model_dump(exclude={"url"}), creating=True):
        raise HTTPException(422, detail="Invalid feed fields")
    existing = session.exec(select(Feed).where(Feed.url == feed_data.url)).first()
    active_snapshot = feed_sync.snapshot(existing) if existing and existing.deleted_at is None else None
    session.rollback()
    if active_snapshot is not None:
        raise HTTPException(409, detail={"code": "feed_conflict", "current": active_snapshot})
    await _validate_feed_url(feed_data.url)
    try:
        return feed_sync.write_web(
            session, url=feed_data.url, kind="upsert",
            fields=feed_data.model_dump(exclude={"url"}), expected=_if_match(if_match),
        )
    except HTTPException as exc:
        detail = exc.detail
        if (exc.status_code == 428 and isinstance(detail, dict) and
            detail.get("code") == "feed_version_required" and
            isinstance(detail.get("current"), dict) and
            detail["current"].get("kind") == "feed"):
            raise HTTPException(409, detail={"code": "feed_conflict",
                                              "current": detail["current"]}) from exc
        raise


@router.get("/{feed_id}", response_model=FeedRead, dependencies=[Depends(verify_api_key)])
async def get_feed(
    feed_id: UUID,
    session: Session = Depends(get_session),
) -> Feed:
    """Get a specific feed by ID."""
    feed = session.get(Feed, feed_id)
    if not feed or feed.deleted_at is not None or feed.url.startswith("synthetic://"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feed not found",
        )
    return feed


@router.put("/{feed_id}", response_model=FeedRead, dependencies=[Depends(verify_api_key)])
async def update_feed(
    feed_id: UUID,
    feed_data: FeedUpdate,
    if_match: str | None = Header(None),
    session: Session = Depends(get_session),
) -> Feed:
    """
    Update an existing feed.

    Only provided fields will be updated (partial update).
    """
    feed = session.get(Feed, feed_id)
    if not feed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feed not found",
        )

    if feed.deleted_at is not None:
        raise HTTPException(409, detail={"code": "feed_conflict", "current": feed_sync.snapshot(feed)})

    update_data = feed_data.model_dump(exclude_unset=True)
    if not feed_sync.validate_fields(update_data, creating=False):
        raise HTTPException(422, detail="Invalid feed fields")
    url = feed.url
    session.rollback()
    await _validate_feed_url(url)
    return feed_sync.write_web(session, url=url, kind="upsert", fields=update_data,
                               expected=_if_match(if_match), feed_id=feed_id)


@router.delete("/{feed_id}", dependencies=[Depends(verify_api_key)])
async def delete_feed(
    feed_id: UUID,
    if_match: str | None = Header(None),
    session: Session = Depends(get_session),
) -> dict:
    """
    Delete a feed by ID.

    This performs a soft delete by setting is_active to False and
    creating a tombstone (deleted_at timestamp) for sync purposes.
    """
    feed = session.get(Feed, feed_id)
    if not feed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feed not found",
        )

    url = feed.url
    session.rollback()
    feed_sync.write_web(session, url=url, kind="delete", fields={},
                        expected=_if_match(if_match), feed_id=feed_id)

    return {"status": "deleted", "id": str(feed_id)}


@router.delete("/by-url/{feed_url:path}", dependencies=[Depends(verify_api_key)])
async def delete_feed_by_url(
    feed_url: str,
    if_match: str | None = Header(None),
    session: Session = Depends(get_session),
) -> dict:
    """
    Delete a feed by URL.

    This performs a soft delete by setting is_active to False and
    creating a tombstone (deleted_at timestamp) for sync purposes.
    Useful when the client doesn't know the backend's UUID for the feed.
    """
    statement = select(Feed).where(Feed.url == feed_url)
    feed = session.exec(statement).first()

    if not feed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feed not found",
        )

    session.rollback()
    feed_sync.write_web(session, url=feed_url, kind="delete", fields={},
                        expected=_if_match(if_match))

    return {"status": "deleted", "url": feed_url}


@router.post("/{feed_id}/clear-seen", dependencies=[Depends(verify_api_key)])
async def clear_seen_articles(
    feed_id: UUID,
    session: Session = Depends(get_session),
) -> dict:
    """
    Clear seen article history for a specific feed.

    This removes all seen_articles entries for the feed, allowing
    previously processed articles to be included in future digests.
    """
    from sqlmodel import delete as sql_delete

    feed = session.get(Feed, feed_id)
    if not feed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feed not found",
        )

    result = session.exec(
        sql_delete(SeenArticle).where(SeenArticle.feed_id == feed_id)
    )
    session.commit()

    deleted_count = result.rowcount  # type: ignore

    return {
        "status": "cleared",
        "feed_id": str(feed_id),
        "cleared_count": deleted_count,
    }
