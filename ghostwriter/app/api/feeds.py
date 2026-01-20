"""Feed management endpoints."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session, select

from app.core.database import get_session
from app.core.security import verify_api_key
from app.models.feed import Feed, FeedCreate, FeedRead, FeedSync

router = APIRouter()


class SyncResponse(BaseModel):
    """Response for feed sync operation."""

    synced: int
    created: int
    updated: int
    unchanged: int


@router.get("", response_model=list[FeedRead], dependencies=[Depends(verify_api_key)])
async def list_feeds(
    session: Session = Depends(get_session),
) -> list[Feed]:
    """
    List all configured feeds.

    Returns all feeds regardless of active status.
    """
    statement = select(Feed).order_by(Feed.title)
    return list(session.exec(statement).all())


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
    # Record feed sync activity
    from app.services import activity_tracker
    activity_tracker.record_feed_sync()

    created = 0
    updated = 0
    unchanged = 0

    # Get existing feeds by URL
    existing_statement = select(Feed)
    existing_feeds = {f.url: f for f in session.exec(existing_statement).all()}

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

    return SyncResponse(
        synced=len(feeds),
        created=created,
        updated=updated,
        unchanged=unchanged,
    )


@router.post("", response_model=FeedRead, dependencies=[Depends(verify_api_key)])
async def create_feed(
    feed_data: FeedCreate,
    session: Session = Depends(get_session),
) -> Feed:
    """
    Create a new feed.

    Returns 409 Conflict if a feed with the same URL already exists.
    """
    # Check for existing
    statement = select(Feed).where(Feed.url == feed_data.url)
    existing = session.exec(statement).first()

    if existing:
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


@router.delete("/{feed_id}", dependencies=[Depends(verify_api_key)])
async def delete_feed(
    feed_id: UUID,
    session: Session = Depends(get_session),
) -> dict:
    """
    Delete a feed by ID.

    This performs a soft delete by setting is_active to False.
    """
    feed = session.get(Feed, feed_id)
    if not feed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feed not found",
        )

    feed.is_active = False
    feed.updated_at = datetime.utcnow()
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

    This performs a soft delete by setting is_active to False.
    Useful when the client doesn't know the backend's UUID for the feed.
    """
    statement = select(Feed).where(Feed.url == feed_url)
    feed = session.exec(statement).first()

    if not feed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feed not found",
        )

    feed.is_active = False
    feed.updated_at = datetime.utcnow()
    session.add(feed)
    session.commit()

    return {"status": "deleted", "url": feed_url}
