"""Tests for RSS content parsing helpers."""

from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.services.content_processor import ContentProcessor
from app.services.outbound_fetch import FetchedResource


@pytest.fixture(autouse=True)
def mock_fetch(monkeypatch):
    async def _fetch(url, **_kwargs):
        return FetchedResource(url, "application/rss+xml", "utf-8", b"<rss/>")

    monkeypatch.setattr("app.services.content_processor.fetch_resource", _fetch)


@pytest.mark.asyncio
async def test_parse_feed_preserves_feed_content_negotiation(monkeypatch):
    async def _fetch(url, **kwargs):
        assert kwargs["headers"]["User-Agent"] == "Ghostwriter/1.0"
        accept = kwargs["headers"]["Accept"]
        assert "application/rss+xml" in accept
        assert "application/atom+xml" in accept
        return FetchedResource(url, "application/rss+xml", "utf-8", b"<rss/>")

    monkeypatch.setattr("app.services.content_processor.fetch_resource", _fetch)
    await ContentProcessor(Settings(allow_private_hosts=True)).parse_feed(
        "https://example.com/feed"
    )


@pytest.mark.asyncio
async def test_parse_feed_prefers_media_content(monkeypatch):
    settings = Settings(allow_private_hosts=True)
    processor = ContentProcessor(settings=settings)

    entries = [
        {
            "id": "a1",
            "link": "https://example.com/post",
            "title": "Episode 1",
            "media_content": [{"url": "https://cdn.example.com/episode1.mp3", "type": "audio/mpeg"}],
        }
    ]
    feed = SimpleNamespace(bozo=False, entries=entries)
    monkeypatch.setattr("feedparser.parse", lambda *_args, **_kwargs: feed)

    articles = await processor.parse_feed("https://example.com/feed.xml")

    assert len(articles) == 1
    assert articles[0].url == "https://example.com/post"
    assert articles[0].content_url == "https://cdn.example.com/episode1.mp3"


@pytest.mark.asyncio
async def test_parse_feed_uses_enclosure_when_missing_media_content(monkeypatch):
    settings = Settings(allow_private_hosts=True)
    processor = ContentProcessor(settings=settings)

    entries = [
        {
            "id": "b2",
            "link": "https://example.com/post-2",
            "title": "Episode 2",
            "enclosures": [{"url": "https://cdn.example.com/episode2.m4a", "type": "audio/mp4"}],
        }
    ]
    feed = SimpleNamespace(bozo=False, entries=entries)
    monkeypatch.setattr("feedparser.parse", lambda *_args, **_kwargs: feed)

    articles = await processor.parse_feed("https://example.com/feed.xml")

    assert len(articles) == 1
    assert articles[0].content_url == "https://cdn.example.com/episode2.m4a"


@pytest.mark.asyncio
async def test_parse_feed_uses_enclosure_link_rel(monkeypatch):
    settings = Settings(allow_private_hosts=True)
    processor = ContentProcessor(settings=settings)

    entries = [
        {
            "id": "c3",
            "link": "https://example.com/post-3",
            "title": "Episode 3",
            "links": [
                {"rel": "alternate", "href": "https://example.com/post-3"},
                {
                    "rel": "enclosure",
                    "href": "https://cdn.example.com/episode3.ogg",
                    "type": "audio/ogg",
                },
            ],
        }
    ]
    feed = SimpleNamespace(bozo=False, entries=entries)
    monkeypatch.setattr("feedparser.parse", lambda *_args, **_kwargs: feed)

    articles = await processor.parse_feed("https://example.com/feed.xml")

    assert len(articles) == 1
    assert articles[0].content_url == "https://cdn.example.com/episode3.ogg"


@pytest.mark.asyncio
async def test_parse_feed_respects_max_entries(monkeypatch):
    settings = Settings(allow_private_hosts=True, max_articles_per_feed=10)
    processor = ContentProcessor(settings=settings)

    entries = [
        {"id": "a1", "link": "https://example.com/1", "title": "One"},
        {"id": "a2", "link": "https://example.com/2", "title": "Two"},
        {"id": "a3", "link": "https://example.com/3", "title": "Three"},
    ]
    feed = SimpleNamespace(bozo=False, entries=entries)
    monkeypatch.setattr("feedparser.parse", lambda *_args, **_kwargs: feed)

    articles = await processor.parse_feed("https://example.com/feed.xml", max_entries=1)

    assert len(articles) == 1
    assert articles[0].url == "https://example.com/1"


@pytest.mark.asyncio
async def test_parse_feed_preserves_filter_metadata(monkeypatch):
    settings = Settings(allow_private_hosts=True)
    processor = ContentProcessor(settings=settings)

    entries = [
        {
            "id": "s1",
            "link": "https://example.com/sponsored-post",
            "title": "Partner Post",
            "summary": "Presented by Example Co.",
            "content": [{"value": "<p>Sponsored by Example Co.</p>"}],
            "tags": [{"term": "Sponsored"}, {"term": "Cloud"}],
        }
    ]
    feed = SimpleNamespace(bozo=False, entries=entries)
    monkeypatch.setattr("feedparser.parse", lambda *_args, **_kwargs: feed)

    articles = await processor.parse_feed("https://example.com/feed.xml")

    assert len(articles) == 1
    assert articles[0].summary == "Presented by Example Co."
    assert articles[0].content == "<p>Sponsored by Example Co.</p>"
    assert articles[0].tags == ["Sponsored", "Cloud"]


@pytest.mark.asyncio
async def test_parse_feed_uses_final_url_as_relative_base(monkeypatch):
    xml = b"""<rss version="2.0"><channel><title>News</title>
    <link>https://example.com/</link><description>News</description><item>
    <title>Story</title><link>/story</link><guid>story-1</guid>
    <enclosure url="audio/episode.mp3" type="audio/mpeg" />
    </item></channel></rss>"""

    async def _fetch(_url, **_kwargs):
        return FetchedResource(
            "https://example.com/feeds/today.xml",
            "application/rss+xml; charset=utf-8",
            "utf-8",
            xml,
        )

    monkeypatch.setattr("app.services.content_processor.fetch_resource", _fetch)
    processor = ContentProcessor(Settings(allow_private_hosts=True))
    articles = await processor.parse_feed("https://example.com/latest")
    assert articles[0].url == "https://example.com/story"
    assert articles[0].content_url == "https://example.com/feeds/audio/episode.mp3"


@pytest.mark.asyncio
async def test_extract_content_uses_fetched_bytes_and_final_url(monkeypatch):
    async def _fetch(_url, **kwargs):
        assert kwargs["kind"] == "html"
        return FetchedResource(
            "https://example.com/final",
            "text/html; charset=utf-8",
            "utf-8",
            b"<html><body><article><h1>Story</h1><p>Useful article text.</p></article></body></html>",
        )

    def _extract(data, **kwargs):
        assert b"Useful article text" in data
        assert kwargs["url"] == "https://example.com/final"
        return "Story Useful article text."

    monkeypatch.setattr("app.services.content_processor.fetch_resource", _fetch)
    monkeypatch.setattr("app.services.content_processor.trafilatura.extract", _extract)
    content = await ContentProcessor(Settings(allow_private_hosts=True)).extract_content(
        "https://example.com/start"
    )
    assert content == "Story Useful article text."


@pytest.mark.asyncio
async def test_extract_content_with_real_trafilatura_from_bounded_bytes(monkeypatch):
    html = b"""<html><head><title>Example Story</title></head><body>
    <article><h1>Example Story</h1><p>This is a useful article about reading
    and saving stories for later. It contains enough detail to extract.</p>
    <p>The second paragraph adds more useful context for the reader.</p></article>
    </body></html>"""

    async def _fetch(_url, **_kwargs):
        return FetchedResource(
            "https://example.com/final", "text/html", "utf-8", html
        )

    monkeypatch.setattr("app.services.content_processor.fetch_resource", _fetch)
    content = await ContentProcessor(Settings(allow_private_hosts=True)).extract_content(
        "https://example.com/start"
    )
    assert content is not None
    assert "useful article about reading" in content
