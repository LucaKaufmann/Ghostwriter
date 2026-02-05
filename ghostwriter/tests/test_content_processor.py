"""Tests for RSS content parsing helpers."""

from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.services.content_processor import ContentProcessor


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
