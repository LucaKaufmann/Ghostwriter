"""Feed management endpoints."""

import logging
import os
import re
import time
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlmodel import Session, select

from app.core.database import get_session
from app.core.net import validate_public_url
from app.core.logging import digest_logger
from app.core.security import verify_api_key
from app.models.feed import Feed, FeedCreate, FeedRead, FeedSync, FeedUpdate
from app.models.seen_article import SeenArticle

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
    statement = select(Feed).where(Feed.deleted_at == None).order_by(Feed.title)  # noqa: E711
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
        statement = select(Feed).where(Feed.deleted_at == None).order_by(Feed.title)  # noqa: E711
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
    ).order_by(Feed.title)
    feeds = list(session.exec(feeds_statement).all())

    # Get tombstones created since the given timestamp
    tombstones_statement = select(Feed).where(
        Feed.deleted_at != None,  # noqa: E711
        Feed.deleted_at > since,
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
    """
    Sync feed configuration from the client.

    This performs an ADDITIVE merge: new feeds are created, existing feeds
    are updated, but feeds not in the list are LEFT UNCHANGED. This allows
    both the app and web UI to manage feeds without conflicts.

    To delete a feed, use DELETE /feeds/{id} explicitly.

    This also records feed sync activity for inactivity tracking.
    """
    t0 = time.perf_counter()

    # Record feed sync activity
    from app.services import activity_tracker
    activity_tracker.record_feed_sync()

    created = 0
    updated = 0
    unchanged = 0

    # Get existing feeds by URL
    existing_statement = select(Feed)
    existing_feeds = {f.url: f for f in session.exec(existing_statement).all()}

    # Validate URLs before applying changes
    for feed_data in feeds:
        try:
            validate_public_url(feed_data.url)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid feed URL '{feed_data.url}': {e}",
            )

    # Update or create feeds from the sync list
    for feed_data in feeds:
        if feed_data.url in existing_feeds:
            feed = existing_feeds[feed_data.url]
            # Check if anything actually changed
            if (feed.title != feed_data.title or
                feed.is_active != feed_data.is_active or
                feed.mode != feed_data.mode or
                feed.max_articles != feed_data.max_articles):
                # Update existing
                feed.title = feed_data.title
                feed.is_active = feed_data.is_active
                feed.mode = feed_data.mode
                feed.max_articles = feed_data.max_articles
                feed.updated_at = datetime.utcnow()
                session.add(feed)
                updated += 1
            else:
                unchanged += 1
        else:
            # Create new
            feed = Feed(
                url=feed_data.url,
                title=feed_data.title,
                is_active=feed_data.is_active,
                mode=feed_data.mode,
                max_articles=feed_data.max_articles,
            )
            session.add(feed)
            created += 1

    # NOTE: We intentionally do NOT deactivate feeds missing from the sync list.
    # This allows feeds added via web UI to coexist with app-synced feeds.

    session.commit()

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
    session: Session = Depends(get_session),
) -> Feed:
    """
    Create a new feed.

    If a soft-deleted feed with the same URL exists, it is restored with
    the new settings. Returns 409 Conflict if an active feed already exists.
    """
    # Check for existing
    statement = select(Feed).where(Feed.url == feed_data.url)
    existing = session.exec(statement).first()

    if existing:
        if existing.deleted_at is not None:
            # Restore the soft-deleted feed with new settings
            existing.title = feed_data.title
            existing.is_active = feed_data.is_active
            existing.mode = feed_data.mode
            existing.max_articles = feed_data.max_articles
            existing.deleted_at = None
            existing.updated_at = datetime.utcnow()
            session.add(existing)
            session.commit()
            session.refresh(existing)
            return existing

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Feed with URL already exists: {feed_data.url}",
        )

    feed = Feed(
        url=feed_data.url,
        title=feed_data.title,
        is_active=feed_data.is_active,
        mode=feed_data.mode,
        max_articles=feed_data.max_articles,
    )
    session.add(feed)
    session.commit()
    session.refresh(feed)

    return feed


@router.get("/{feed_id}", response_model=FeedRead, dependencies=[Depends(verify_api_key)])
async def get_feed(
    feed_id: UUID,
    session: Session = Depends(get_session),
) -> Feed:
    """Get a specific feed by ID."""
    feed = session.get(Feed, feed_id)
    if not feed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feed not found",
        )
    return feed


@router.put("/{feed_id}", response_model=FeedRead, dependencies=[Depends(verify_api_key)])
async def update_feed(
    feed_id: UUID,
    feed_data: FeedUpdate,
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

    # Update only provided fields
    update_data = feed_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(feed, field, value)

    feed.updated_at = datetime.utcnow()
    session.add(feed)
    session.commit()
    session.refresh(feed)

    return feed


@router.delete("/{feed_id}", dependencies=[Depends(verify_api_key)])
async def delete_feed(
    feed_id: UUID,
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

    now = datetime.utcnow()
    feed.is_active = False
    feed.deleted_at = now
    feed.updated_at = now
    session.add(feed)
    session.commit()

    return {"status": "deleted", "id": str(feed_id)}


@router.delete("/by-url/{feed_url:path}", dependencies=[Depends(verify_api_key)])
async def delete_feed_by_url(
    feed_url: str,
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

    now = datetime.utcnow()
    feed.is_active = False
    feed.deleted_at = now
    feed.updated_at = now
    session.add(feed)
    session.commit()

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
