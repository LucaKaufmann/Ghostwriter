"""Tests for YouTube channel resolver."""

from __future__ import annotations

import pytest

from app.services.youtube_channel_resolver import resolve_youtube_channel


@pytest.mark.asyncio
async def test_resolve_youtube_channel_rejects_non_youtube_url(monkeypatch):
    """Non-YouTube hosts are rejected before any request is made."""

    def _unexpected_client(*_args, **_kwargs):
        raise AssertionError("HTTP client should not be opened")

    monkeypatch.setattr(
        "app.services.youtube_channel_resolver.httpx.AsyncClient",
        _unexpected_client,
    )

    with pytest.raises(ValueError, match="Only youtube.com URLs are allowed"):
        await resolve_youtube_channel("https://example.com/@ghostwriter")


@pytest.mark.asyncio
async def test_resolve_youtube_channel_blocks_private_redirect_target(monkeypatch):
    """YouTube page redirects are validated before following them."""
    requested_urls: list[str] = []

    class _FakeResponse:
        status_code = 302
        headers = {"location": "http://127.0.0.1/private"}
        url = "https://www.youtube.com/@ghostwriter"
        text = ""

        def raise_for_status(self) -> None:
            return

    class _FakeAsyncClient:
        def __init__(self, *_args, **kwargs) -> None:
            assert kwargs["follow_redirects"] is False

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url: str):
            requested_urls.append(url)
            return _FakeResponse()

    monkeypatch.setattr(
        "app.services.youtube_channel_resolver.httpx.AsyncClient",
        _FakeAsyncClient,
    )

    with pytest.raises(ValueError, match="Only youtube.com URLs are allowed"):
        await resolve_youtube_channel("https://www.youtube.com/@ghostwriter")

    assert requested_urls == ["https://www.youtube.com/@ghostwriter"]
