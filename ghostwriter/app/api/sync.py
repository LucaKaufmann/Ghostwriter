"""Combined sync endpoint for efficient client synchronization."""

import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from app.core.database import get_session
from app.core.security import verify_api_key
from app.models.digest import Digest, DigestArticle
from app.models.feed import Feed
from app.api.config import ConfigResponse, get_or_create_config, _config_to_response
from app.api.feeds import FeedChangesResponse, FeedTombstone
from app.api.schedules import ScheduleResponse, _schedule_to_response
from app.worker import scheduler as scheduler_module

router = APIRouter()
logger = logging.getLogger(__name__)


class SyncDigestArticle(BaseModel):
    """Article embedded in a sync digest response."""

    id: UUID
    title: str
    url: str
    mode: str
    word_count: int
    content: str
    author: str | None
    feed_title: str
    sort_order: int
    ai_failed: bool


class SyncDigest(BaseModel):
    """Digest with embedded articles for sync response."""

    id: UUID
    filename: str
    period: str
    status: str
    stage: str | None
    article_count: int
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None
    articles: list[SyncDigestArticle]


class SyncDigestsSection(BaseModel):
    """Digests section of the sync response."""

    new_digests: list[SyncDigest]


class SyncResponse(BaseModel):
    """Combined sync response containing all data the client needs."""

    config: ConfigResponse
    feeds: FeedChangesResponse
    digests: SyncDigestsSection
    schedules: list[ScheduleResponse]


@router.get("", response_model=SyncResponse, dependencies=[Depends(verify_api_key)])
async def combined_sync(
    feed_since: Optional[datetime] = Query(None, description="Get feed changes since this timestamp"),
    digest_ids: Optional[str] = Query(None, description="Comma-separated list of known digest IDs to exclude"),
    session: Session = Depends(get_session),
) -> SyncResponse:
    """
    Combined sync endpoint that returns everything the client needs in one response.

    This replaces multiple sequential calls:
    - GET /config
    - GET /feeds/changes
    - GET /digests + GET /digests/{id}/articles (for each new digest)
    - GET /schedules

    Query parameters:
    - feed_since: Timestamp for incremental feed sync (omit for initial sync)
    - digest_ids: Comma-separated list of digest IDs the client already has
    """
    # 1. Config
    config = get_or_create_config(session)
    config_response = _config_to_response(config, session)

    # 2. Feeds (same logic as GET /feeds/changes)
    server_timestamp = datetime.utcnow()

    if feed_since is None:
        # Initial sync: return all active feeds
        feeds_statement = select(Feed).where(Feed.deleted_at == None).order_by(Feed.title)  # noqa: E711
        feeds = list(session.exec(feeds_statement).all())
        feeds_response = FeedChangesResponse(
            feeds=feeds,
            tombstones=[],
            server_timestamp=server_timestamp,
        )
    else:
        # Incremental sync
        feeds_statement = select(Feed).where(
            Feed.updated_at > feed_since,
            Feed.deleted_at == None,  # noqa: E711
        ).order_by(Feed.title)
        feeds = list(session.exec(feeds_statement).all())

        tombstones_statement = select(Feed).where(
            Feed.deleted_at != None,  # noqa: E711
            Feed.deleted_at > feed_since,
        )
        tombstoned_feeds = session.exec(tombstones_statement).all()
        tombstones = [
            FeedTombstone(url=f.url, deleted_at=f.deleted_at)
            for f in tombstoned_feeds
            if f.deleted_at is not None
        ]

        feeds_response = FeedChangesResponse(
            feeds=feeds,
            tombstones=tombstones,
            server_timestamp=server_timestamp,
        )

    # 3. Digests - only completed, excluding known IDs
    known_ids: set[str] = set()
    if digest_ids:
        known_ids = {id_str.strip() for id_str in digest_ids.split(",") if id_str.strip()}

    digests_statement = select(Digest).where(Digest.status == "completed")
    all_completed = list(session.exec(digests_statement).all())

    new_digests: list[SyncDigest] = []
    for digest in all_completed:
        if str(digest.id) in known_ids:
            continue

        # Fetch articles for this digest
        articles_statement = (
            select(DigestArticle)
            .where(DigestArticle.digest_id == digest.id)
            .order_by(DigestArticle.sort_order)
        )
        articles = list(session.exec(articles_statement).all())

        new_digests.append(SyncDigest(
            id=digest.id,
            filename=digest.filename,
            period=digest.period,
            status=digest.status,
            stage=digest.stage,
            article_count=digest.article_count,
            error_message=digest.error_message,
            created_at=digest.created_at,
            completed_at=digest.completed_at,
            articles=[
                SyncDigestArticle(
                    id=a.id,
                    title=a.title,
                    url=a.url,
                    mode=a.mode,
                    word_count=a.word_count,
                    content=a.content,
                    author=a.author,
                    feed_title=a.feed_title,
                    sort_order=a.sort_order,
                    ai_failed=a.ai_failed,
                )
                for a in articles
            ],
        ))

    digests_response = SyncDigestsSection(new_digests=new_digests)

    # 4. Schedules
    schedules = scheduler_module.get_all_schedules()
    schedules_response = [_schedule_to_response(s) for s in schedules]

    return SyncResponse(
        config=config_response,
        feeds=feeds_response,
        digests=digests_response,
        schedules=schedules_response,
    )
