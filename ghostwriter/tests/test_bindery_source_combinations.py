"""Offline regression coverage for editions built without RSS articles."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from ebooklib import ITEM_DOCUMENT, epub
from lxml import html
from sqlmodel import Session, SQLModel, create_engine, select

from app.models.client_config import ClientConfig
from app.models.digest import Digest, DigestArticle
from app.models.feed import Feed
from app.models.media_feed import MediaFeed
from app.models.media_item import MediaItem
from app.models.seen_article import SeenArticle
from app.models.wallabag_config import WallabagConfig
from app.services.content_processor import ExtractedArticle
from app.services.wallabag_service import WallabagService
from app.worker import bindery

REAL_WALLABAG_FACTORY = WallabagService.from_db_or_settings.__func__


class WallabagStub:
    def __init__(self, entries=(), mode="raw", configured=True):
        self.entries = list(entries)
        self.settings = SimpleNamespace(wallabag_mode=mode)
        self.is_configured = configured
        self.marked = []

    async def fetch_unread_articles(self):
        return self.entries

    async def mark_processed(self, entry_id):
        self.marked.append(entry_id)


class NewsletterStub:
    def __init__(self, articles=(), configured=True):
        self.articles = list(articles)
        self.is_configured = configured
        self.marked = []

    async def fetch_newsletters(self):
        return self.articles, [f"message-{a.guid}" for a in self.articles]

    async def mark_processed(self, ids):
        self.marked.extend(ids)


class EmptyFeedProcessor:
    async def parse_feed(self, _url, max_entries):
        return []


def article(guid="newsletter-1"):
    content = (
        "A useful editorial newsletter with enough substance for a reading edition."
    )
    return ExtractedArticle(
        guid=guid,
        url=f"https://example.com/{guid}",
        title="Editorial analysis",
        content=content,
        author="Writer",
        word_count=len(content.split()),
        is_summary=False,
        ai_failed=False,
        processing_ms=0,
        feed_title="Newsletter",
    )


def wallabag_entry():
    return {
        "id": 7,
        "url": "https://example.com/saved",
        "title": "Saved analysis",
        "content": "<p>A useful saved article with enough substance for a reading edition.</p>",
        "domain_name": "example.com",
    }


@pytest.fixture
def scene(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(bindery, "engine", engine)

    def make(
        *,
        wallabag=None,
        newsletter=None,
        media=None,
        active_rss=False,
        config=None,
        wallabag_config=None,
    ):
        digest_id = uuid4()
        with Session(engine) as session:
            session.add(
                Digest(id=digest_id, filename=f"{digest_id}.epub", period="manual")
            )
            if active_rss:
                session.add(
                    Feed(
                        url="https://example.com/feed.xml", title="RSS", is_active=True
                    )
                )
            if config:
                session.add(config)
            if wallabag_config:
                session.add(wallabag_config)
            if media:
                feed = MediaFeed(
                    feed_type=media, url=f"https://example.com/{media}", title=media
                )
                session.add(feed)
                session.flush()
                session.add(
                    MediaItem(
                        media_feed_id=feed.id,
                        guid=f"{media}-1",
                        url=f"https://example.com/{media}/1",
                        title=f"{media} transcript",
                        content="A complete transcript for a reading edition.",
                        word_count=7,
                        content_type=media,
                        status="completed",
                    )
                )
            session.commit()
        wb = wallabag or WallabagStub(configured=False)
        nl = newsletter or NewsletterStub(configured=False)
        monkeypatch.setattr(
            bindery.WallabagService,
            "from_db_or_settings",
            classmethod(lambda cls, *args: wb),
        )
        monkeypatch.setattr(bindery, "NewsletterService", lambda *args: nl)
        pipeline = bindery.BinderyPipeline(digest_id)
        pipeline.content_processor = EmptyFeedProcessor()
        pipeline.epub_generator.settings = pipeline.settings.model_copy(
            update={"output_dir": str(tmp_path)}
        )
        return pipeline, wb, nl

    return engine, tmp_path, make


def inspect_edition(engine, output_dir, digest_id, expected_count):
    with Session(engine) as session:
        digest = session.get(Digest, digest_id)
        rows = session.exec(
            select(DigestArticle).where(DigestArticle.digest_id == digest_id)
        ).all()
        assert digest.status == "completed"
        assert digest.article_count == expected_count
        assert len(rows) == expected_count
        if expected_count:
            path = output_dir / digest.filename
            assert path.stat().st_size > 0
            book = epub.read_epub(str(path))
            chapters = [
                " ".join(
                    " ".join(html.fromstring(item.get_content()).itertext()).split()
                )
                for item in book.get_items_of_type(ITEM_DOCUMENT)
            ]
            for row in rows:
                content_text = " ".join(
                    " ".join(html.fromstring(row.content).itertext()).split()
                )
                assert content_text
                assert any(
                    row.title in chapter and content_text in chapter
                    for chapter in chapters
                )
        else:
            assert not (output_dir / digest.filename).exists()
        return rows


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["wallabag", "newsletter", "podcast", "youtube"])
async def test_source_only_editions_are_persisted_and_readable(scene, source):
    engine, output_dir, make = scene
    pipeline, wb, nl = make(
        wallabag=WallabagStub([wallabag_entry()]) if source == "wallabag" else None,
        newsletter=NewsletterStub([article()]) if source == "newsletter" else None,
        media=source if source in ("podcast", "youtube") else None,
    )
    await pipeline.run()
    rows = inspect_edition(engine, output_dir, pipeline.digest_id, 1)
    assert rows[0].content_type == (
        source if source in ("podcast", "youtube") else "article"
    )
    if source == "wallabag":
        assert wb.marked == [7]
    if source == "newsletter":
        assert nl.marked == ["message-newsletter-1"]
    if source in ("podcast", "youtube"):
        with Session(engine) as session:
            assert (
                session.exec(select(MediaItem)).one().consumed_digest_id
                == pipeline.digest_id
            )


@pytest.mark.asyncio
async def test_empty_active_rss_still_allows_media(scene):
    engine, output_dir, make = scene
    pipeline, _, _ = make(media="podcast", active_rss=True)
    await pipeline.run()
    inspect_edition(engine, output_dir, pipeline.digest_id, 1)


@pytest.mark.asyncio
async def test_truly_empty_and_disabled_sources_complete_without_epub(scene):
    engine, output_dir, make = scene
    empty, _, _ = make()
    await empty.run()
    inspect_edition(engine, output_dir, empty.digest_id, 0)

    disabled, wb, nl = make(
        wallabag=WallabagStub([wallabag_entry()]),
        newsletter=NewsletterStub([article()]),
        media="youtube",
        config=ClientConfig(newsletters_enabled=False, include_youtube_in_digest=False),
        wallabag_config=WallabagConfig(enabled=False),
    )
    await disabled.run()
    inspect_edition(engine, output_dir, disabled.digest_id, 0)
    assert wb.marked == [] and nl.marked == []


@pytest.mark.asyncio
async def test_seen_filtered_and_consumed_sources_remain_empty(scene):
    engine, output_dir, make = scene
    pipeline, wb, nl = make(
        wallabag=WallabagStub([wallabag_entry()]),
        newsletter=NewsletterStub([article()]),
        media="podcast",
    )
    with Session(engine) as session:
        wb_feed = bindery.get_or_create_synthetic_feed(session, "wallabag")
        session.add(
            SeenArticle(
                feed_id=wb_feed.id,
                guid="wallabag-7",
                url="https://example.com/saved",
                title="Saved analysis",
            )
        )
        item = session.exec(select(MediaItem)).one()
        from datetime import datetime

        item.consumed_at = datetime.utcnow()
        session.add(item)
        session.commit()
    pipeline.article_filter.check_extracted = lambda **kwargs: SimpleNamespace(
        eligible=False, reason="filtered", confidence=1.0
    )
    await pipeline.run()
    inspect_edition(engine, output_dir, pipeline.digest_id, 0)
    assert wb.marked == [] and nl.marked == []
    with Session(engine) as session:
        assert {seen.guid for seen in session.exec(select(SeenArticle)).all()} == {
            "wallabag-7",
            "newsletter-1",
        }
        assert session.exec(select(MediaItem)).one().consumed_digest_id is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "db_mode,env_mode,expected",
    [
        ("summarize", "raw", "summarized"),
        ("raw", "summarize", "raw"),
    ],
)
async def test_wallabag_database_mode_overrides_environment(
    scene, monkeypatch, db_mode, env_mode, expected
):
    engine, output_dir, make = scene
    pipeline, _, _ = make(
        wallabag_config=WallabagConfig(
            enabled=True,
            mode=db_mode,
            url="https://example.com",
            client_id="fixture",
            client_secret="fixture",
            username="fixture",
            password="fixture",
        ),
    )
    pipeline.settings = pipeline.settings.model_copy(update={"wallabag_mode": env_mode})

    monkeypatch.setattr(
        WallabagService, "from_db_or_settings", classmethod(REAL_WALLABAG_FACTORY)
    )

    async def fetch(service):
        assert service.settings.wallabag_mode == db_mode
        return [wallabag_entry()]

    async def mark(_service, _entry_id):
        return None

    monkeypatch.setattr(WallabagService, "fetch_unread_articles", fetch)
    monkeypatch.setattr(WallabagService, "mark_processed", mark)

    async def summarize(*args, **kwargs):
        return "A concise summary of the saved analysis.", False

    pipeline.llm_service.summarize = summarize
    await pipeline.run()
    rows = inspect_edition(engine, output_dir, pipeline.digest_id, 1)
    assert rows[0].mode == expected


@pytest.mark.asyncio
async def test_wallabag_environment_config_is_used_without_database_credentials(
    scene,
    monkeypatch,
):
    engine, output_dir, make = scene
    pipeline, _, _ = make()
    pipeline.settings = pipeline.settings.model_copy(
        update={
            "wallabag_url": "https://example.com",
            "wallabag_client_id": "test",
            "wallabag_client_secret": "test",
            "wallabag_username": "test",
            "wallabag_password": "test",
            "wallabag_mode": "summarize",
        }
    )
    monkeypatch.setattr(
        WallabagService, "from_db_or_settings", classmethod(REAL_WALLABAG_FACTORY)
    )

    async def fetch(_self):
        return [wallabag_entry()]

    async def mark(_self, _id):
        return None

    monkeypatch.setattr(WallabagService, "fetch_unread_articles", fetch)
    monkeypatch.setattr(WallabagService, "mark_processed", mark)

    async def summarize(*args, **kwargs):
        return "A concise summary of the saved analysis.", False

    pipeline.llm_service.summarize = summarize
    await pipeline.run()
    assert (
        inspect_edition(engine, output_dir, pipeline.digest_id, 1)[0].mode
        == "summarized"
    )


@pytest.mark.asyncio
async def test_wallabag_llm_failure_keeps_raw_article(scene):
    engine, output_dir, make = scene
    pipeline, _, _ = make(wallabag=WallabagStub([wallabag_entry()], mode="summarize"))

    async def fail(*args, **kwargs):
        return "LLM failed", True

    pipeline.llm_service.summarize = fail
    await pipeline.run()
    rows = inspect_edition(engine, output_dir, pipeline.digest_id, 1)
    assert rows[0].mode == "raw"
    assert "useful saved article" in rows[0].content


@pytest.mark.asyncio
async def test_pre_output_failure_preserves_retry_state(scene):
    engine, output_dir, make = scene
    pipeline, wb, nl = make(
        wallabag=WallabagStub([wallabag_entry()]),
        newsletter=NewsletterStub([article()]),
        media="podcast",
    )
    original_generate = pipeline.epub_generator.generate

    def fail(*args, **kwargs):
        raise RuntimeError("epub boom")

    pipeline.epub_generator.generate = fail
    with pytest.raises(RuntimeError, match="epub boom"):
        await pipeline.run()
    with Session(engine) as session:
        assert session.exec(select(DigestArticle)).all() == []
        assert session.exec(select(SeenArticle)).all() == []
        assert session.exec(select(MediaItem)).one().consumed_at is None
        assert session.get(Digest, pipeline.digest_id).status == "failed"
    assert wb.marked == [] and nl.marked == []

    pipeline.epub_generator.generate = original_generate
    await pipeline.run()
    inspect_edition(engine, output_dir, pipeline.digest_id, 3)
    with Session(engine) as session:
        assert len(session.exec(select(DigestArticle)).all()) == 3
        assert session.exec(select(MediaItem)).one().consumed_at is not None
