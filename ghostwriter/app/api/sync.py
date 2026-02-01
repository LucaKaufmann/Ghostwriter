"""Combined sync endpoint for efficient client synchronization."""

import json
import logging
import time
from collections import defaultdict
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlmodel import Session, col, select

from app.core.database import get_session
from app.core.security import verify_api_key
from app.models.digest import Digest, DigestArticle
from app.models.feed import Feed
from app.api.config import ConfigResponse, get_or_create_config, _config_to_response
from app.api.feeds import FeedChangesResponse, FeedTombstone
from app.api.schedules import ScheduleResponse, _schedule_to_response
from app.core.logging import digest_logger
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


@router.get("", dependencies=[Depends(verify_api_key)])
async def combined_sync(
    feed_since: Optional[datetime] = Query(None, description="Get feed changes since this timestamp"),
    digest_ids: Optional[str] = Query(None, description="Comma-separated list of known digest IDs to exclude"),
    session: Session = Depends(get_session),
) -> Response:
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
    t0 = time.perf_counter()

    # 1. Config
    config = get_or_create_config(session)
    config_response = _config_to_response(config, session)
    t_config = time.perf_counter()

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
    t_feeds = time.perf_counter()

    # 3. Digests - only completed, excluding known IDs in SQL
    known_ids: set[str] = set()
    if digest_ids:
        known_ids = {id_str.strip() for id_str in digest_ids.split(",") if id_str.strip()}

    digests_statement = select(Digest).where(Digest.status == "completed")
    if known_ids:
        digests_statement = digests_statement.where(
            col(Digest.id).notin_([UUID(id_str) for id_str in known_ids])
        )
    new_completed = list(session.exec(digests_statement).all())
    t_digests_query = time.perf_counter()

    # Batch-fetch all articles for new digests in a single query
    new_digests: list[dict] = []
    if new_completed:
        digest_id_list = [d.id for d in new_completed]
        articles_statement = (
            select(DigestArticle)
            .where(col(DigestArticle.digest_id).in_(digest_id_list))
            .order_by(DigestArticle.sort_order)
        )
        all_articles = list(session.exec(articles_statement).all())

        # Group articles by digest_id
        articles_by_digest: dict[UUID, list] = defaultdict(list)
        for a in all_articles:
            articles_by_digest[a.digest_id].append({
                "id": str(a.id),
                "title": a.title,
                "url": a.url,
                "mode": a.mode,
                "word_count": a.word_count,
                "content": a.content,
                "author": a.author,
                "feed_title": a.feed_title,
                "sort_order": a.sort_order,
                "ai_failed": a.ai_failed,
            })

        for digest in new_completed:
            new_digests.append({
                "id": str(digest.id),
                "filename": digest.filename,
                "period": digest.period,
                "status": digest.status,
                "stage": digest.stage,
                "article_count": digest.article_count,
                "error_message": digest.error_message,
                "created_at": digest.created_at.isoformat(),
                "completed_at": digest.completed_at.isoformat() if digest.completed_at else None,
                "articles": articles_by_digest.get(digest.id, []),
            })
    t_articles = time.perf_counter()

    # 4. Schedules
    schedules = scheduler_module.get_all_schedules()
    schedules_response = [_schedule_to_response(s) for s in schedules]
    t_schedules = time.perf_counter()

    # Build response as dict and serialize directly, skipping Pydantic validation
    response_data = {
        "config": config_response.model_dump(mode="json"),
        "feeds": feeds_response.model_dump(mode="json"),
        "digests": {"new_digests": new_digests},
        "schedules": [s.model_dump(mode="json") for s in schedules_response],
    }
    t_serialize = time.perf_counter()

    body = json.dumps(response_data, default=str)
    t_json = time.perf_counter()

    total_ms = (t_json - t0) * 1000
    article_count = sum(len(d["articles"]) for d in new_digests)
    breakdown = {
        "config_ms": round((t_config - t0) * 1000),
        "feeds_ms": round((t_feeds - t_config) * 1000),
        "digests_query_ms": round((t_digests_query - t_feeds) * 1000),
        "articles_query_ms": round((t_articles - t_digests_query) * 1000),
        "schedules_ms": round((t_schedules - t_articles) * 1000),
        "serialize_ms": round((t_serialize - t_schedules) * 1000),
        "json_ms": round((t_json - t_serialize) * 1000),
    }

    logger.info(
        "Sync completed in %.0fms (config=%.0f feeds=%.0f digests_q=%.0f "
        "articles_q=%.0f schedules=%.0f serialize=%.0f json=%.0f) "
        "digests=%d articles=%d bytes=%d",
        total_ms,
        breakdown["config_ms"],
        breakdown["feeds_ms"],
        breakdown["digests_query_ms"],
        breakdown["articles_query_ms"],
        breakdown["schedules_ms"],
        breakdown["serialize_ms"],
        breakdown["json_ms"],
        len(new_digests),
        article_count,
        len(body),
    )

    digest_logger.sync_combined(
        duration_ms=total_ms,
        new_digests=len(new_digests),
        article_count=article_count,
        response_bytes=len(body),
        breakdown=breakdown,
    )

    return Response(content=body, media_type="application/json")
