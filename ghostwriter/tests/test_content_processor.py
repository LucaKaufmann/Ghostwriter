import asyncio

import pytest

from app.core.config import Settings
from app.services.content_processor import ContentProcessor


@pytest.mark.asyncio
async def test_parse_feed_rejects_invalid_scheme():
    processor = ContentProcessor(Settings())
    result = await processor.parse_feed("file:///etc/passwd")
    assert result == []


@pytest.mark.asyncio
async def test_extract_content_rejects_invalid_scheme():
    processor = ContentProcessor(Settings())
    result = await processor.extract_content("file:///etc/passwd")
    assert result is None


@pytest.mark.asyncio
async def test_extract_content_timeout(monkeypatch):
    processor = ContentProcessor(Settings())

    async def _fake_wait_for(_task, timeout=None):
        raise asyncio.TimeoutError

    monkeypatch.setattr("app.services.content_processor.asyncio.wait_for", _fake_wait_for)

    result = await processor.extract_content("https://example.com")
    assert result is None
