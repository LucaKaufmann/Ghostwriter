"""Media feed and item API endpoints for podcasts and YouTube."""

import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
import sqlalchemy as sa
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
from app.models.media_processing_run import MediaProcessingRun, MediaProcessingRunRead
from app.services.digest_content_formatter import format_digest_content_to_html

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
    current_item_title: str | None = None
    current_item_content_type: str | None = None
    last_completed_at: str | None = None
    next_run_at: str | None = None
    last_run: MediaProcessingRunRead | None = None


class MediaTriggerResponse(BaseModel):
    status: str
    detail: str | None = None


class MediaRetryResponse(BaseModel):
    status: str
    detail: str | None = None
    item_id: UUID | None = None


class RetryFailedRequest(BaseModel):
    content_type: str | None = Field(
        default=None,
        description="Optional filter: podcast or youtube",
    )


class RetryFailedResponse(BaseModel):
    retried: int
    skipped: int


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
    """List all podcast items, ordered by status priority then date."""
    status_order = sa.case(
        {"processing": 0, "pending": 1, "failed": 2, "completed": 3},
        value=MediaItem.status,
    )
    items = session.exec(
        select(MediaItem)
        .where(MediaItem.content_type == "podcast")
        .order_by(status_order, MediaItem.created_at.desc())
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
    """List all YouTube items, ordered by status priority then date."""
    status_order = sa.case(
        {"processing": 0, "pending": 1, "failed": 2, "completed": 3},
        value=MediaItem.status,
    )
    items = session.exec(
        select(MediaItem)
        .where(MediaItem.content_type == "youtube")
        .order_by(status_order, MediaItem.created_at.desc())
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
    item_data = item.model_dump()
    item_data["content_html"] = format_digest_content_to_html(item.content)
    return MediaItemRead(**item_data)


@router.post(
    "/items/{item_id}/retry",
    response_model=MediaRetryResponse,
    dependencies=[Depends(verify_api_key)],
)
async def retry_media_item(
    item_id: UUID,
    session: Session = Depends(get_session),
):
    """Re-queue a failed media item for processing in the next run."""
    item = session.get(MediaItem, item_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media item not found",
        )

    if item.status != "failed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only failed media items can be retried",
        )

    _requeue_item(item)
    session.add(item)
    session.commit()
    logger.info("Retried media item %s (%s)", item.id, item.title)
    return MediaRetryResponse(
        status="queued",
        detail="Media item queued for next media processing run",
        item_id=item.id,
    )


@router.post(
    "/items/retry-failed",
    response_model=RetryFailedResponse,
    dependencies=[Depends(verify_api_key)],
)
async def retry_failed_media_items(
    request: RetryFailedRequest,
    session: Session = Depends(get_session),
):
    """Bulk re-queue failed media items for the next media processing run."""
    if request.content_type is not None and request.content_type not in ("podcast", "youtube"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="content_type must be 'podcast' or 'youtube'",
        )

    query = select(MediaItem).where(MediaItem.status == "failed")
    if request.content_type:
        query = query.where(MediaItem.content_type == request.content_type)

    failed_items = session.exec(query).all()
    retried = 0
    skipped = 0

    for item in failed_items:
        if item.status != "failed":
            skipped += 1
            continue
        _requeue_item(item)
        session.add(item)
        retried += 1

    session.commit()
    logger.info(
        "Retried failed media items: retried=%s skipped=%s content_type=%s",
        retried,
        skipped,
        request.content_type or "all",
    )
    return RetryFailedResponse(retried=retried, skipped=skipped)


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
    processing_items = session.exec(
        select(MediaItem).where(MediaItem.status == "processing")
    ).all()
    processing = len(processing_items)
    completed = len(session.exec(
        select(MediaItem).where(MediaItem.status == "completed")
    ).all())
    failed = len(session.exec(
        select(MediaItem).where(MediaItem.status == "failed")
    ).all())

    # Current processing item details
    current_title = None
    current_content_type = None
    if processing_items:
        current_title = processing_items[0].title
        current_content_type = processing_items[0].content_type

    # Most recently completed item
    last_completed_item = session.exec(
        select(MediaItem)
        .where(MediaItem.status == "completed")
        .where(MediaItem.completed_at != None)
        .order_by(MediaItem.completed_at.desc())
        .limit(1)
    ).first()
    last_completed_at = (
        last_completed_item.completed_at.isoformat()
        if last_completed_item and last_completed_item.completed_at
        else None
    )

    # Next scheduled run
    next_run_at = None
    try:
        from app.worker.scheduler import scheduler
        job = scheduler.get_job("media_processing")
        if job and job.next_run_time:
            next_run_at = job.next_run_time.isoformat()
    except Exception:
        pass

    # Latest pipeline run
    latest_run = session.exec(
        select(MediaProcessingRun)
        .order_by(MediaProcessingRun.started_at.desc())
        .limit(1)
    ).first()
    last_run = MediaProcessingRunRead.model_validate(latest_run) if latest_run else None

    return MediaProcessingStatus(
        is_running=processing > 0,
        pending_count=pending,
        processing_count=processing,
        completed_count=completed,
        failed_count=failed,
        current_item_title=current_title,
        current_item_content_type=current_content_type,
        last_completed_at=last_completed_at,
        next_run_at=next_run_at,
        last_run=last_run,
    )


@router.get(
    "/runs",
    response_model=list[MediaProcessingRunRead],
    dependencies=[Depends(verify_api_key)],
)
async def list_media_runs(
    limit: int = 20,
    session: Session = Depends(get_session),
):
    """List recent media processing pipeline runs."""
    runs = session.exec(
        select(MediaProcessingRun)
        .order_by(MediaProcessingRun.started_at.desc())
        .limit(limit)
    ).all()
    return runs


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


def _requeue_item(item: MediaItem) -> None:
    """Reset a failed media item back to pending state."""
    item.status = "pending"
    item.error_message = None
    item.processing_ms = 0
    item.completed_at = None
