"""Offline transport and resolver tests for bounded document fetches."""

from __future__ import annotations

import asyncio
import gzip
import os
import socket
import threading

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


class OneChunk(httpx.AsyncByteStream):
    def __init__(self, data: bytes):
        self.data = data

    async def __aiter__(self):
        yield self.data


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
            stream=OneChunk(b"<rss version='2.0'/>"),
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

    with pytest.raises(httpx.TimeoutException):
        await fetch_resource(
            "https://example.com/article",
            settings=_settings(fetch_timeout_seconds=1),
            kind="html",
            headers={},
            transport=httpx.MockTransport(handler),
        )


@pytest.mark.asyncio
async def test_gzip_output_limit_precedes_expansion(public_dns):
    compressed = gzip.compress(b"x" * 10_000)
    assert len(compressed) < 128
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200,
            stream=OneChunk(compressed),
            headers={"content-type": "text/html", "content-encoding": "gzip"},
        )
    )
    with pytest.raises(DocumentTooLargeError):
        await fetch_resource(
            "https://example.com/article",
            settings=_settings(),
            kind="html",
            headers={},
            max_bytes=128,
            transport=transport,
        )


@pytest.mark.asyncio
async def test_small_gzip_document_decodes_and_unsupported_encoding_rejects(public_dns):
    compressed = gzip.compress(b"<html>hello</html>")

    def handler(request):
        assert request.headers["accept-encoding"] == "gzip, identity"
        return httpx.Response(
            200,
            stream=OneChunk(compressed),
            headers={"content-type": "text/html", "content-encoding": "gzip"},
        )

    fetched = await fetch_resource(
        "https://example.com/article",
        settings=_settings(),
        kind="html",
        headers={},
        transport=httpx.MockTransport(handler),
    )
    assert fetched.data == b"<html>hello</html>"

    unsupported = httpx.MockTransport(
        lambda _request: httpx.Response(
            200,
            stream=OneChunk(b"ignored"),
            headers={"content-type": "text/html", "content-encoding": "br"},
        )
    )
    with pytest.raises(httpx.DecodingError, match="Unsupported content encoding"):
        await fetch_resource(
            "https://example.com/article",
            settings=_settings(),
            kind="html",
            headers={},
            transport=unsupported,
        )


@pytest.mark.asyncio
async def test_relative_content_location_is_resolved_against_final_url(public_dns):
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200,
            stream=OneChunk(b"<rss/>"),
            headers={
                "content-type": "application/rss+xml",
                "content-location": "../archive/feed.xml",
            },
        )
    )
    fetched = await fetch_resource(
        "https://example.com/feeds/today.xml",
        settings=_settings(),
        kind="feed",
        headers={},
        transport=transport,
    )
    assert fetched.content_location == "https://example.com/archive/feed.xml"


@pytest.mark.asyncio
async def test_httpx_environment_configuration_is_preserved(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example:3128")
    monkeypatch.setenv("SSL_CERT_FILE", "/synthetic/test-ca.pem")
    original_client = httpx.AsyncClient
    seen = []

    def client_with_mock_transport(*args, **kwargs):
        seen.append(
            (
                kwargs["trust_env"],
                os.environ["HTTPS_PROXY"],
                os.environ["SSL_CERT_FILE"],
            )
        )
        # The test uses a mock transport; do not configure a real proxy or CA.
        kwargs["trust_env"] = False
        return original_client(*args, **kwargs)

    monkeypatch.setattr(
        "app.services.outbound_fetch.httpx.AsyncClient", client_with_mock_transport
    )
    await fetch_resource(
        "https://example.com/article",
        settings=Settings(allow_private_hosts=True),
        kind="html",
        headers={},
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200, stream=OneChunk(b"<html/>"), headers={"content-type": "text/html"}
            )
        ),
    )
    assert seen == [(True, "http://proxy.example:3128", "/synthetic/test-ca.pem")]


@pytest.mark.asyncio
async def test_expired_dns_jobs_remain_bounded_until_workers_finish(monkeypatch):
    from app.services import outbound_fetch

    release = threading.Event()
    started = threading.Event()
    lock = threading.Lock()
    active = 0

    def stalled_resolver(_hostname):
        nonlocal active
        with lock:
            active += 1
            if active == outbound_fetch.MAX_DNS_VALIDATIONS:
                started.set()
        release.wait(10)
        with lock:
            active -= 1
        return ["93.184.216.34"]

    monkeypatch.setattr("app.core.net._resolve_host", stalled_resolver)
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(200, stream=OneChunk(b"<html/>"))
    )
    tasks = [
        asyncio.create_task(
            fetch_resource(
                "https://example.com/article",
                settings=_settings(fetch_timeout_seconds=1),
                kind="html",
                headers={},
                transport=transport,
            )
        )
        for _ in range(outbound_fetch.MAX_DNS_VALIDATIONS)
    ]
    try:
        assert await asyncio.to_thread(started.wait, 0.5)
        for task in tasks:
            with pytest.raises(httpx.ReadTimeout):
                await task

        async def extra_fetch():
            with pytest.raises(httpx.ReadTimeout):
                await fetch_resource(
                    "https://example.com/extra",
                    settings=_settings(fetch_timeout_seconds=1),
                    kind="html",
                    headers={},
                    transport=transport,
                )

        await asyncio.gather(*(extra_fetch() for _ in range(3)))
        with lock:
            assert active == outbound_fetch.MAX_DNS_VALIDATIONS
    finally:
        release.set()
    # Once OS calls finish, the waiting caller proceeds without extra threads.
    recovered = await fetch_resource(
        "https://example.com/recovered",
        settings=_settings(),
        kind="html",
        headers={},
        transport=transport,
    )
    assert recovered.data == b"<html/>"


@pytest.mark.asyncio
async def test_dns_validation_is_off_loop_and_inside_total_deadline(monkeypatch):
    started = threading.Event()
    release = threading.Event()
    requested = []

    def stalled_resolver(_hostname):
        started.set()
        release.wait(3)
        return ["93.184.216.34"]

    monkeypatch.setattr("app.core.net._resolve_host", stalled_resolver)

    def handler(request):
        requested.append(str(request.url))
        return httpx.Response(200, content=b"<html/>")

    task = asyncio.create_task(
        fetch_resource(
            "https://example.com/article",
            settings=_settings(fetch_timeout_seconds=1),
            kind="html",
            headers={},
            transport=httpx.MockTransport(handler),
        )
    )
    try:
        assert await asyncio.to_thread(started.wait, 0.3)
        await asyncio.wait_for(asyncio.sleep(0.02), timeout=0.3)
        with pytest.raises(httpx.TimeoutException):
            await task
        assert requested == []
    finally:
        release.set()


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
            "https://example.com/feed",
            settings=_settings(),
            kind="feed",
            headers={},
            transport=html,
        )
    with pytest.raises(NonHtmlContentError):
        await fetch_resource(
            "https://example.com/article",
            settings=_settings(),
            kind="html",
            headers={},
            transport=xml,
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
        return httpx.Response(
            200, stream=OneChunk(b"<html/>"), headers={"content-type": "text/html"}
        )

    result = await fetch_resource(
        "http://127.0.0.1/article",
        settings=Settings(allow_private_hosts=True),
        kind="html",
        headers={},
        transport=httpx.MockTransport(handler),
    )
    assert result.data == b"<html/>"
    assert requested == ["http://127.0.0.1/article"]


@pytest.mark.asyncio
async def test_healthy_concurrency_waits_for_dns_admission(monkeypatch):
    import time

    from app.services import outbound_fetch

    def healthy_resolver(_hostname):
        time.sleep(0.03)
        return ["93.184.216.34"]

    monkeypatch.setattr("app.core.net._resolve_host", healthy_resolver)
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(200, stream=OneChunk(b"<html/>"))
    )
    results = await asyncio.gather(
        *(
            fetch_resource(
                "https://example.com/article",
                settings=_settings(fetch_timeout_seconds=1),
                kind="html",
                headers={},
                transport=transport,
            )
            for _ in range(outbound_fetch.MAX_DNS_VALIDATIONS * 2)
        )
    )
    assert all(result.data == b"<html/>" for result in results)


@pytest.mark.asyncio
async def test_dns_admission_wakes_one_waiter_in_fifo_order(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    from app.services import outbound_fetch

    started = {host: threading.Event() for host in ("first.example", "second.example", "third.example")}
    release = {host: threading.Event() for host in started}
    order = []

    def resolve(host):
        order.append(host)
        started[host].set()
        assert release[host].wait(3)
        return ["93.184.216.34"]

    monkeypatch.setattr("app.core.net._resolve_host", resolve)
    monkeypatch.setattr(outbound_fetch, "_dns_slots", threading.BoundedSemaphore(1))
    with ThreadPoolExecutor(max_workers=1) as executor:
        monkeypatch.setattr(outbound_fetch, "_dns_executor", executor)
        tasks = []
        try:
            for host in started:
                tasks.append(asyncio.create_task(outbound_fetch.validate_public_url_bounded(
                    f"https://{host}/rss", _settings(fetch_timeout_seconds=3),
                )))
                if host == "first.example":
                    assert await asyncio.to_thread(started[host].wait, 1)
                else:
                    await asyncio.sleep(0)
            assert not started["second.example"].is_set()
            release["first.example"].set()
            assert await asyncio.to_thread(started["second.example"].wait, 1)
            assert not started["third.example"].is_set()
            release["second.example"].set()
            assert await asyncio.to_thread(started["third.example"].wait, 1)
            release["third.example"].set()
            await asyncio.gather(*tasks)
            assert order == list(started)
        finally:
            for event in release.values():
                event.set()


@pytest.mark.asyncio
async def test_cancelled_dns_waiter_passes_slot_to_next_caller(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    from app.services import outbound_fetch

    started = threading.Event()
    release = threading.Event()
    called = []

    def resolve(host):
        called.append(host)
        if host == "first.example":
            started.set()
            assert release.wait(3)
        return ["93.184.216.34"]

    monkeypatch.setattr("app.core.net._resolve_host", resolve)
    monkeypatch.setattr(outbound_fetch, "_dns_slots", threading.BoundedSemaphore(1))
    with ThreadPoolExecutor(max_workers=1) as executor:
        monkeypatch.setattr(outbound_fetch, "_dns_executor", executor)
        first = asyncio.create_task(outbound_fetch.validate_public_url_bounded(
            "https://first.example/rss", _settings(fetch_timeout_seconds=3),
        ))
        try:
            assert await asyncio.to_thread(started.wait, 1)
            cancelled = asyncio.create_task(outbound_fetch.validate_public_url_bounded(
                "https://cancelled.example/rss", _settings(fetch_timeout_seconds=3),
            ))
            await asyncio.sleep(0)
            last = asyncio.create_task(outbound_fetch.validate_public_url_bounded(
                "https://last.example/rss", _settings(fetch_timeout_seconds=3),
            ))
            await asyncio.sleep(0)
            cancelled.cancel()
            with pytest.raises(asyncio.CancelledError):
                await cancelled
            release.set()
            await asyncio.gather(first, last)
            assert called == ["first.example", "last.example"]
        finally:
            release.set()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["html", "feed"])
async def test_malformed_content_location_does_not_invalidate_body(public_dns, kind):
    fetched = await fetch_resource(
        "https://example.com/body",
        settings=_settings(),
        kind=kind,
        headers={},
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                stream=OneChunk(b"<body/>"),
                headers={"Content-Location": "http://[bad"},
            )
        ),
    )
    assert fetched.data == b"<body/>"
    assert fetched.content_location is None
    assert fetched.final_url == "https://example.com/body"
