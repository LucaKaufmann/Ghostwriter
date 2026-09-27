"""Offline transport and resolver tests for bounded document fetches."""

from __future__ import annotations

import asyncio
import socket

import httpx
import pytest

from app.core.config import Settings
from app.core.net import validate_public_url
from app.services.outbound_fetch import (
    DocumentTooLargeError,
    NonFeedContentError,
    NonHtmlContentError,
    fetch_resource,
)


@pytest.fixture
def public_dns(monkeypatch):
    monkeypatch.setattr("app.core.net._resolve_host", lambda _host: ["93.184.216.34"])


def _settings(**kwargs):
    return Settings(allow_private_hosts=False, **kwargs)


@pytest.mark.asyncio
async def test_public_relative_redirect_chain_and_feed_xml(public_dns):
    requested = []

    def handler(request):
        requested.append(str(request.url))
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "/feed/today.xml"})
        if request.url.path == "/feed/today.xml":
            return httpx.Response(301, headers={"location": "next.xml"})
        return httpx.Response(
            200,
            content=b"<rss version='2.0'/>",
            headers={"content-type": "application/rss+xml; charset=utf-8"},
        )

    result = await fetch_resource(
        "https://example.com/start",
        settings=_settings(),
        kind="feed",
        headers={},
        transport=httpx.MockTransport(handler),
    )
    assert requested == [
        "https://example.com/start",
        "https://example.com/feed/today.xml",
        "https://example.com/feed/next.xml",
    ]
    assert result.final_url == requested[-1]
    assert result.data.startswith(b"<rss")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "location",
    [
        "http://127.0.0.1/private",
        "http://169.254.1.2/private",
        "http://[::1]/private",
        "http://[fe80::1]/private",
        "https://name:secret@example.com/private",
    ],
)
async def test_unsafe_redirect_is_rejected_before_transport(public_dns, location):
    requested = []

    def handler(request):
        requested.append(str(request.url))
        return httpx.Response(302, headers={"location": location})

    with pytest.raises(ValueError):
        await fetch_resource(
            "https://example.com/start",
            settings=_settings(),
            kind="html",
            headers={},
            transport=httpx.MockTransport(handler),
        )
    assert requested == ["https://example.com/start"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/private",
        "http://169.254.1.2/private",
        "http://[::1]/private",
        "http://[fe80::1]/private",
        "https://:secret@example.com/private",
    ],
)
async def test_unsafe_initial_url_is_rejected_before_transport(public_dns, url):
    def fail(_request):
        raise AssertionError("The unsafe URL must not reach the transport")

    with pytest.raises(ValueError):
        await fetch_resource(
            url,
            settings=_settings(),
            kind="html",
            headers={},
            transport=httpx.MockTransport(fail),
        )


@pytest.mark.asyncio
async def test_private_dns_answer_blocks_redirect_before_transport(monkeypatch):
    answers = {"example.com": ["93.184.216.34"], "private.example": ["10.0.0.5"]}
    monkeypatch.setattr("app.core.net._resolve_host", lambda host: answers[host])
    requested = []

    def handler(request):
        requested.append(str(request.url))
        return httpx.Response(302, headers={"location": "https://private.example/x"})

    with pytest.raises(ValueError, match="Private or local"):
        await fetch_resource(
            "https://example.com/start",
            settings=_settings(),
            kind="html",
            headers={},
            transport=httpx.MockTransport(handler),
        )
    assert requested == ["https://example.com/start"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "error"),
    [
        (httpx.Response(302), "missing Location"),
        (httpx.Response(302, headers={"location": "/start"}), "Redirect loop"),
    ],
)
async def test_bad_redirects_fail(public_dns, response, error):
    with pytest.raises(ValueError, match=error):
        await fetch_resource(
            "https://example.com/start",
            settings=_settings(),
            kind="html",
            headers={},
            transport=httpx.MockTransport(lambda _request: response),
        )


@pytest.mark.asyncio
async def test_redirect_hop_limit(public_dns):
    def handler(request):
        number = int(request.url.path.removeprefix("/"))
        return httpx.Response(302, headers={"location": f"/{number + 1}"})

    with pytest.raises(ValueError, match="Too many redirects"):
        await fetch_resource(
            "https://example.com/0",
            settings=_settings(),
            kind="html",
            headers={},
            max_redirects=2,
            transport=httpx.MockTransport(handler),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("length_header", [True, False])
async def test_byte_limit(public_dns, length_header):
    headers = {"content-type": "text/html"}

    class TwoChunks(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"abc"
            yield b"def"

    if length_header:
        headers["content-length"] = "6"
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(200, stream=TwoChunks(), headers=headers)
    )
    with pytest.raises(DocumentTooLargeError):
        await fetch_resource(
            "https://example.com/article",
            settings=_settings(),
            kind="html",
            headers={},
            max_bytes=5,
            transport=transport,
        )


@pytest.mark.asyncio
async def test_total_timeout(public_dns):
    async def handler(_request):
        await asyncio.sleep(2)
        return httpx.Response(200, content=b"ok")

    with pytest.raises(TimeoutError):
        await fetch_resource(
            "https://example.com/article",
            settings=_settings(fetch_timeout_seconds=1),
            kind="html",
            headers={},
            transport=httpx.MockTransport(handler),
        )


@pytest.mark.asyncio
async def test_html_and_xml_content_types_are_distinct(public_dns):
    html = httpx.MockTransport(
        lambda _request: httpx.Response(
            200, content=b"<html/>", headers={"content-type": "text/html"}
        )
    )
    xml = httpx.MockTransport(
        lambda _request: httpx.Response(
            200, content=b"<rss/>", headers={"content-type": "application/rss+xml"}
        )
    )
    with pytest.raises(NonFeedContentError):
        await fetch_resource(
            "https://example.com/feed", settings=_settings(), kind="feed",
            headers={}, transport=html,
        )
    with pytest.raises(NonHtmlContentError):
        await fetch_resource(
            "https://example.com/article", settings=_settings(), kind="html",
            headers={}, transport=xml,
        )


def test_dns_failure_is_safe_value_error(monkeypatch):
    def fail(_hostname):
        raise socket.gaierror("resolver secret")

    monkeypatch.setattr("app.core.net._resolve_host", fail)
    with pytest.raises(ValueError, match="Hostname could not be resolved") as error:
        validate_public_url("https://example.com/feed", _settings())
    assert "secret" not in str(error.value)


@pytest.mark.asyncio
async def test_explicit_private_host_opt_in_uses_mock_transport():
    requested = []

    def handler(request):
        requested.append(str(request.url))
        return httpx.Response(200, content=b"<html/>", headers={"content-type": "text/html"})

    result = await fetch_resource(
        "http://127.0.0.1/article",
        settings=Settings(allow_private_hosts=True),
        kind="html",
        headers={},
        transport=httpx.MockTransport(handler),
    )
    assert result.data == b"<html/>"
    assert requested == ["http://127.0.0.1/article"]
