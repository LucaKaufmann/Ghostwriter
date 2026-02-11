"""Media feed and item API endpoints for podcasts and YouTube."""

import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session, select

from app.core.database import get_session
from app.core.security import verify_api_key
from app.models.media_feed import (
    MediaFeed,
    MediaFeedCreate,
    MediaFeedRead,
    MediaFeedUpdate,
)
from app.models.media_item import MediaItem, MediaItemRead, MediaItemSummary

router = APIRouter()
logger = logging.getLogger(__name__)


# ============ Schemas ============


class YouTubeResolveRequest(BaseModel):
    url: str


class YouTubeResolveResponse(BaseModel):
    rss_feed_url: str
    channel_id: str
    channel_title: str | None = None


class MediaProcessingStatus(BaseModel):
    is_running: bool
    pending_count: int
    processing_count: int
    completed_count: int
    failed_count: int


class MediaTriggerResponse(BaseModel):
    status: str
    detail: str | None = None


# ============ Podcast Feeds ============


@router.get(
    "/podcasts",
    response_model=list[MediaFeedRead],
    dependencies=[Depends(verify_api_key)],
)
async def list_podcast_feeds(session: Session = Depends(get_session)):
    """List all podcast feeds."""
    feeds = session.exec(
        select(MediaFeed)
        .where(MediaFeed.feed_type == "podcast")
        .where(MediaFeed.deleted_at == None)
        .order_by(MediaFeed.title)
    ).all()
    return feeds


@router.post(
    "/podcasts",
    response_model=MediaFeedRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_api_key)],
)
async def create_podcast_feed(
    feed_data: MediaFeedCreate,
    session: Session = Depends(get_session),
):
    """Create a new podcast feed."""
    if feed_data.feed_type != "podcast":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="feed_type must be 'podcast' for this endpoint",
        )
    return _create_media_feed(feed_data, session)


@router.put(
    "/podcasts/{feed_id}",
    response_model=MediaFeedRead,
    dependencies=[Depends(verify_api_key)],
)
async def update_podcast_feed(
    feed_id: UUID,
    update: MediaFeedUpdate,
    session: Session = Depends(get_session),
):
    """Update a podcast feed."""
    return _update_media_feed(feed_id, "podcast", update, session)


@router.delete(
    "/podcasts/{feed_id}",
    dependencies=[Depends(verify_api_key)],
)
async def delete_podcast_feed(
    feed_id: UUID,
    session: Session = Depends(get_session),
):
    """Soft-delete a podcast feed."""
    return _delete_media_feed(feed_id, "podcast", session)


@router.get(
    "/podcasts/{feed_id}/items",
    response_model=list[MediaItemSummary],
    dependencies=[Depends(verify_api_key)],
)
async def list_podcast_feed_items(
    feed_id: UUID,
    session: Session = Depends(get_session),
):
    """List items for a specific podcast feed."""
    _ensure_feed_exists(feed_id, "podcast", session)
    items = session.exec(
        select(MediaItem)
        .where(MediaItem.media_feed_id == feed_id)
        .order_by(MediaItem.created_at.desc())
    ).all()
    return items


@router.get(
    "/podcasts/items/all",
    response_model=list[MediaItemSummary],
    dependencies=[Depends(verify_api_key)],
)
async def list_all_podcast_items(session: Session = Depends(get_session)):
    """List all completed podcast items."""
    items = session.exec(
        select(MediaItem)
        .where(MediaItem.content_type == "podcast")
        .where(MediaItem.status == "completed")
        .order_by(MediaItem.completed_at.desc())
    ).all()
    return items


# ============ YouTube Feeds ============


@router.get(
    "/youtube",
    response_model=list[MediaFeedRead],
    dependencies=[Depends(verify_api_key)],
)
async def list_youtube_feeds(session: Session = Depends(get_session)):
    """List all YouTube feeds."""
    feeds = session.exec(
        select(MediaFeed)
        .where(MediaFeed.feed_type == "youtube")
        .where(MediaFeed.deleted_at == None)
        .order_by(MediaFeed.title)
    ).all()
    return feeds


@router.post(
    "/youtube",
    response_model=MediaFeedRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_api_key)],
)
async def create_youtube_feed(
    feed_data: MediaFeedCreate,
    session: Session = Depends(get_session),
):
    """Create a new YouTube feed."""
    if feed_data.feed_type != "youtube":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="feed_type must be 'youtube' for this endpoint",
        )
    return _create_media_feed(feed_data, session)


@router.put(
    "/youtube/{feed_id}",
    response_model=MediaFeedRead,
    dependencies=[Depends(verify_api_key)],
)
async def update_youtube_feed(
    feed_id: UUID,
    update: MediaFeedUpdate,
    session: Session = Depends(get_session),
):
    """Update a YouTube feed."""
    return _update_media_feed(feed_id, "youtube", update, session)


@router.delete(
    "/youtube/{feed_id}",
    dependencies=[Depends(verify_api_key)],
)
async def delete_youtube_feed(
    feed_id: UUID,
    session: Session = Depends(get_session),
):
    """Soft-delete a YouTube feed."""
    return _delete_media_feed(feed_id, "youtube", session)


@router.get(
    "/youtube/{feed_id}/items",
    response_model=list[MediaItemSummary],
    dependencies=[Depends(verify_api_key)],
)
async def list_youtube_feed_items(
    feed_id: UUID,
    session: Session = Depends(get_session),
):
    """List items for a specific YouTube feed."""
    _ensure_feed_exists(feed_id, "youtube", session)
    items = session.exec(
        select(MediaItem)
        .where(MediaItem.media_feed_id == feed_id)
        .order_by(MediaItem.created_at.desc())
    ).all()
    return items


@router.get(
    "/youtube/items/all",
    response_model=list[MediaItemSummary],
    dependencies=[Depends(verify_api_key)],
)
async def list_all_youtube_items(session: Session = Depends(get_session)):
    """List all completed YouTube items."""
    items = session.exec(
        select(MediaItem)
        .where(MediaItem.content_type == "youtube")
        .where(MediaItem.status == "completed")
        .order_by(MediaItem.completed_at.desc())
    ).all()
    return items


@router.post(
    "/youtube/resolve",
    response_model=YouTubeResolveResponse,
    dependencies=[Depends(verify_api_key)],
)
async def resolve_youtube_url(request: YouTubeResolveRequest):
    """Resolve a YouTube channel URL to its RSS feed URL."""
    from app.services.youtube_channel_resolver import resolve_youtube_channel

    try:
        result = await resolve_youtube_channel(request.url)
        return YouTubeResolveResponse(
            rss_feed_url=result.rss_feed_url,
            channel_id=result.channel_id,
            channel_title=result.channel_title,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


# ============ Shared: Items + Processing ============


@router.get(
    "/items/{item_id}",
    response_model=MediaItemRead,
    dependencies=[Depends(verify_api_key)],
)
async def get_media_item(
    item_id: UUID,
    session: Session = Depends(get_session),
):
    """Get a single media item with full content."""
    item = session.get(MediaItem, item_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media item not found",
        )
    return item


@router.post(
    "/trigger",
    response_model=MediaTriggerResponse,
    dependencies=[Depends(verify_api_key)],
)
async def trigger_media_processing():
    """Manually trigger media processing."""
    import asyncio
    from app.worker.media_pipeline import run_media_pipeline

    asyncio.create_task(run_media_pipeline())
    return MediaTriggerResponse(
        status="started",
        detail="Media processing triggered",
    )


@router.get(
    "/status",
    response_model=MediaProcessingStatus,
    dependencies=[Depends(verify_api_key)],
)
async def get_media_status(session: Session = Depends(get_session)):
    """Get current media processing status."""
    pending = len(session.exec(
        select(MediaItem).where(MediaItem.status == "pending")
    ).all())
    processing = len(session.exec(
        select(MediaItem).where(MediaItem.status == "processing")
    ).all())
    completed = len(session.exec(
        select(MediaItem).where(MediaItem.status == "completed")
    ).all())
    failed = len(session.exec(
        select(MediaItem).where(MediaItem.status == "failed")
    ).all())

    return MediaProcessingStatus(
        is_running=processing > 0,
        pending_count=pending,
        processing_count=processing,
        completed_count=completed,
        failed_count=failed,
    )


# ============ Internal helpers ============


def _create_media_feed(feed_data: MediaFeedCreate, session: Session) -> MediaFeed:
    """Create a new media feed (shared logic)."""
    # Check for duplicate URL
    existing = session.exec(
        select(MediaFeed).where(MediaFeed.url == feed_data.url)
    ).first()
    if existing:
        if existing.deleted_at:
            # Re-activate soft-deleted feed
            existing.deleted_at = None
            existing.is_active = feed_data.is_active
            existing.title = feed_data.title
            existing.mode = feed_data.mode
            existing.max_items = feed_data.max_items
            existing.resolved_feed_url = feed_data.resolved_feed_url
            existing.updated_at = datetime.now(timezone.utc)
            session.add(existing)
            session.commit()
            session.refresh(existing)
            return existing
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A feed with this URL already exists",
        )

    feed = MediaFeed(
        feed_type=feed_data.feed_type,
        url=feed_data.url,
        resolved_feed_url=feed_data.resolved_feed_url,
        title=feed_data.title,
        is_active=feed_data.is_active,
        mode=feed_data.mode,
        max_items=feed_data.max_items,
    )
    session.add(feed)
    session.commit()
    session.refresh(feed)
    logger.info(f"Created media feed: {feed.title} ({feed.feed_type})")
    return feed


def _update_media_feed(
    feed_id: UUID, feed_type: str, update: MediaFeedUpdate, session: Session
) -> MediaFeed:
    """Update a media feed (shared logic)."""
    feed = session.get(MediaFeed, feed_id)
    if not feed or feed.deleted_at or feed.feed_type != feed_type:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feed not found",
        )

    if update.title is not None:
        feed.title = update.title
    if update.is_active is not None:
        feed.is_active = update.is_active
    if update.mode is not None:
        feed.mode = update.mode
    if update.max_items is not None:
        feed.max_items = update.max_items

    feed.updated_at = datetime.now(timezone.utc)
    session.add(feed)
    session.commit()
    session.refresh(feed)
    logger.info(f"Updated media feed: {feed.title}")
    return feed


def _delete_media_feed(feed_id: UUID, feed_type: str, session: Session) -> dict:
    """Soft-delete a media feed (shared logic)."""
    feed = session.get(MediaFeed, feed_id)
    if not feed or feed.deleted_at or feed.feed_type != feed_type:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feed not found",
        )

    feed.is_active = False
    feed.deleted_at = datetime.now(timezone.utc)
    feed.updated_at = datetime.now(timezone.utc)
    session.add(feed)
    session.commit()
    logger.info(f"Soft-deleted media feed: {feed.title}")
    return {"status": "deleted"}


def _ensure_feed_exists(feed_id: UUID, feed_type: str, session: Session) -> MediaFeed:
    """Ensure a media feed exists and return it."""
    feed = session.get(MediaFeed, feed_id)
    if not feed or feed.deleted_at or feed.feed_type != feed_type:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feed not found",
        )
    return feed
