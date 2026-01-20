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
    deleted: int


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

    This performs a full replacement: feeds not in the input list will be
    deactivated (not deleted, to preserve history). Existing feeds are
    updated, new feeds are created.
    """
    created = 0
    updated = 0

    # Get existing feeds by URL
    existing_statement = select(Feed)
    existing_feeds = {f.url: f for f in session.exec(existing_statement).all()}
    incoming_urls = {f.url for f in feeds}

    # Update or create feeds
    for feed_data in feeds:
        if feed_data.url in existing_feeds:
            # Update existing
            feed = existing_feeds[feed_data.url]
            feed.title = feed_data.title
            feed.is_active = feed_data.is_active
            feed.mode = feed_data.mode
            feed.max_articles = feed_data.max_articles
            feed.updated_at = datetime.utcnow()
            session.add(feed)
            updated += 1
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

    # Deactivate feeds not in the sync list
    deleted = 0
    for url, feed in existing_feeds.items():
        if url not in incoming_urls and feed.is_active:
            feed.is_active = False
            feed.updated_at = datetime.utcnow()
            session.add(feed)
            deleted += 1

    session.commit()

    return SyncResponse(
        synced=len(feeds),
        created=created,
        updated=updated,
        deleted=deleted,
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
    Delete a feed.

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
