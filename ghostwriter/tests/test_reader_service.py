"""Tests for reader_service."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.services.reader_service import fetch_html_document


@pytest.mark.asyncio
async def test_fetch_html_document_blocks_private_redirect_target(monkeypatch):
    """Redirect targets are validated before the next request is opened."""
    requested_urls: list[str] = []

    class _FakeResponse:
        status_code = 302
        headers = {"location": "http://127.0.0.1/private"}
        url = "http://93.184.216.34/article"
        encoding = "utf-8"

        def raise_for_status(self) -> None:
            return

        async def aiter_bytes(self):
            yield b""

    class _FakeStream:
        async def __aenter__(self):
            return _FakeResponse()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _FakeAsyncClient:
        def __init__(self, *_args, **kwargs) -> None:
            assert kwargs["follow_redirects"] is False

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def stream(self, _method: str, url: str):
            requested_urls.append(url)
            return _FakeStream()

    monkeypatch.setattr(
        "app.services.reader_service.httpx.AsyncClient",
        _FakeAsyncClient,
    )

    with pytest.raises(ValueError, match="Private or local IPs"):
        await fetch_html_document(
            "http://93.184.216.34/article",
            settings=Settings(allow_private_hosts=False),
        )

    assert requested_urls == ["http://93.184.216.34/article"]
