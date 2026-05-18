"""Regression tests for Bindery seen-article durability."""

from dataclasses import dataclass
from uuid import uuid4

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.models.digest import Digest
from app.models.feed import Feed
from app.models.seen_article import SeenArticle
from app.worker import bindery
from app.worker.bindery import BinderyPipeline


@dataclass
class ParsedArticleStub:
    guid: str
    url: str
    title: str
    author: str | None = None
    content_url: str | None = None


class ContentProcessorStub:
    def __init__(self, articles: list[ParsedArticleStub]) -> None:
        self.articles = articles

    async def parse_feed(self, _url: str, max_entries: int) -> list[ParsedArticleStub]:
        return self.articles[:max_entries]

    async def extract_content(self, _url: str) -> str:
        return "Extracted article body"


class FailingEpubGenerator:
    def generate(self, *args, **kwargs) -> str:
        raise RuntimeError("epub boom")


class UnconfiguredWallabagService:
    is_configured = False


class UnconfiguredNewsletterService:
    is_configured = False

    def __init__(self, *args, **kwargs) -> None:
        pass


@pytest.fixture
def bindery_engine(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'ghostwriter.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(bindery, "engine", engine)
    return engine


@pytest.mark.asyncio
async def test_seen_articles_are_not_saved_when_epub_generation_fails(
    bindery_engine,
    monkeypatch,
) -> None:
    """A failed digest must leave successfully extracted articles eligible to retry."""
    article = ParsedArticleStub(
        guid="article-1",
        url="https://example.com/article-1",
        title="Article 1",
    )
    digest_id = uuid4()

    with Session(bindery_engine) as session:
        feed = Feed(
            url="https://example.com/feed.xml",
            title="Example Feed",
            is_active=True,
            mode="raw",
            max_articles=10,
        )
        session.add(feed)
        session.add(
            Digest(
                id=digest_id,
                filename="failed.epub",
                period="manual",
                status="processing",
                stage="queued",
            )
        )
        session.commit()
        feed_id = feed.id

    monkeypatch.setattr(
        bindery.WallabagService,
        "from_db_or_settings",
        staticmethod(lambda *args, **kwargs: UnconfiguredWallabagService()),
    )
    monkeypatch.setattr(bindery, "NewsletterService", UnconfiguredNewsletterService)
    monkeypatch.setattr(
        bindery.MediaProcessor,
        "quick_check",
        staticmethod(lambda *args, **kwargs: False),
    )

    pipeline = BinderyPipeline(digest_id)
    pipeline.content_processor = ContentProcessorStub([article])
    pipeline.epub_generator = FailingEpubGenerator()

    with pytest.raises(RuntimeError, match="epub boom"):
        await pipeline.run()

    with Session(bindery_engine) as session:
        assert session.exec(select(SeenArticle)).all() == []
        digest = session.get(Digest, digest_id)
        assert digest is not None
        assert digest.status == "failed"

    assert await pipeline._is_seen(feed_id, article.guid) is False


@pytest.mark.asyncio
async def test_complete_saves_seen_articles_with_completed_digest(
    bindery_engine,
) -> None:
    digest_id = uuid4()

    with Session(bindery_engine) as session:
        feed = Feed(url="https://example.com/feed.xml", title="Example Feed")
        session.add(feed)
        session.add(
            Digest(
                id=digest_id,
                filename="completed.epub",
                period="manual",
                status="processing",
                stage="compiling",
            )
        )
        session.commit()
        feed_id = feed.id

    pipeline = BinderyPipeline(digest_id)
    await pipeline._complete(
        1,
        seen_articles=[
            (
                feed_id,
                "article-1",
                "https://example.com/article-1",
                "Article 1",
            )
        ],
    )

    with Session(bindery_engine) as session:
        digest = session.get(Digest, digest_id)
        assert digest is not None
        assert digest.status == "completed"

        seen = session.exec(select(SeenArticle)).one()
        assert seen.feed_id == feed_id
        assert seen.guid == "article-1"
