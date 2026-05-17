"""Tests for Bindery article filtering integration."""

from uuid import uuid4

import pytest
from sqlmodel import Session, select

from app.core.database import engine, init_db
from app.models.feed import Feed
from app.models.seen_article import SeenArticle
from app.services.content_processor import ParsedArticle
from app.worker.bindery import BinderyPipeline


@pytest.mark.asyncio
async def test_fetch_feed_filters_promotional_candidates_and_marks_seen(monkeypatch):
    init_db()
    feed = Feed(
        id=uuid4(),
        url=f"https://example.com/{uuid4()}/feed.xml",
        title="Example Feed",
        mode="raw",
        max_articles=10,
    )
    sponsored_guid = f"sponsored-{uuid4()}"
    editorial_guid = f"editorial-{uuid4()}"

    with Session(engine) as session:
        session.add(feed)
        session.commit()
        session.refresh(feed)
        feed = Feed.model_validate(feed)

    async def _parse_feed(_url: str, max_entries: int | None = None):
        return [
            ParsedArticle(
                guid=sponsored_guid,
                url="https://example.com/sponsored/story",
                title="Sponsored: A message from Example Co",
                summary="Presented by Example Co.",
            ),
            ParsedArticle(
                guid=editorial_guid,
                url="https://example.com/news/story",
                title="Useful editorial analysis",
                summary="Independent reporting on the industry.",
            ),
        ]

    pipeline = BinderyPipeline(uuid4())
    monkeypatch.setattr(pipeline.content_processor, "parse_feed", _parse_feed)

    articles, total_count = await pipeline._fetch_feed(feed)

    assert total_count == 2
    assert len(articles) == 1
    assert articles[0][1].guid == editorial_guid

    with Session(engine) as session:
        seen = session.exec(
            select(SeenArticle).where(SeenArticle.guid == sponsored_guid)
        ).first()
    assert seen is not None
