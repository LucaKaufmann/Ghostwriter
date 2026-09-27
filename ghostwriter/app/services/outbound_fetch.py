"""Bounded HTTP fetches for feeds and web documents.

URLs are checked before each connection, including every redirect destination.
The transport resolves hosts separately, so this is not a DNS pinning guarantee.
"""

from __future__ import annotations

import asyncio
import threading
import zlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from urllib.parse import urljoin

import httpx

from app.core.config import Settings
from app.core.net import validate_public_url

MAX_DOCUMENT_BYTES = 5_000_000
MAX_REDIRECTS = 5
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
MAX_DNS_VALIDATIONS = 4
_dns_executor = ThreadPoolExecutor(max_workers=MAX_DNS_VALIDATIONS)
_dns_slots = threading.BoundedSemaphore(MAX_DNS_VALIDATIONS)


class NonHtmlContentError(RuntimeError):
    """Raised when a web document response is not HTML."""


class NonFeedContentError(RuntimeError):
    """Raised when a feed response is not XML or a compatible feed MIME type."""


class DocumentTooLargeError(RuntimeError):
    """Raised when a response exceeds the configured byte limit."""


@dataclass(frozen=True)
class FetchedResource:
    final_url: str
    content_type: str | None
    encoding: str
    data: bytes
    content_location: str | None = None


async def _validate_url(url: str, settings: Settings) -> None:
    """Validate off-loop with a fixed bound on queued and live DNS work."""
    # Wait without blocking the loop, within the total deadline. Admission must
    # not turn ordinary concurrency into an immediate upstream failure.
    while not _dns_slots.acquire(blocking=False):
        await asyncio.sleep(0.01)
    try:
        future = _dns_executor.submit(validate_public_url, url, settings)
    except BaseException:
        _dns_slots.release()
        raise
    # Cancellation can stop waiting, but an active getaddrinfo call keeps its
    # slot until the OS returns. A queued, cancelled future releases it here too.
    future.add_done_callback(lambda _future: _dns_slots.release())
    await asyncio.wrap_future(future)


def _check_content_type(content_type: str | None, kind: str) -> None:
    if not content_type:
        return
    mime = content_type.partition(";")[0].strip().lower()
    if kind == "html" and mime not in {"text/html", "application/xhtml+xml"}:
        raise NonHtmlContentError(f"Unsupported content-type: {content_type}")
    if (
        kind == "feed"
        and mime
        not in {
            "application/rss+xml",
            "application/atom+xml",
            "application/xml",
            "text/xml",
            "text/plain",
            "application/octet-stream",
        }
        and not mime.endswith("+xml")
    ):
        raise NonFeedContentError(f"Unsupported feed content-type: {content_type}")


async def _read_bounded(response: httpx.Response, max_bytes: int) -> bytes:
    """Limit wire bytes and gzip expansion before adding decoded bytes."""
    encoding = response.headers.get("content-encoding", "identity").strip().lower()
    if encoding not in {"identity", "gzip"}:
        raise httpx.DecodingError("Unsupported content encoding")
    length = response.headers.get("content-length")
    if length and length.isdecimal() and int(length) > max_bytes:
        raise DocumentTooLargeError(f"Document exceeded max size of {max_bytes} bytes")

    data = bytearray()
    wire_bytes = 0
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS) if encoding == "gzip" else None
    async for raw in response.aiter_raw():
        wire_bytes += len(raw)
        if wire_bytes > max_bytes:
            raise DocumentTooLargeError(
                f"Document exceeded max size of {max_bytes} bytes"
            )
        if decoder is None:
            if len(raw) > max_bytes - len(data):
                raise DocumentTooLargeError(
                    f"Document exceeded max size of {max_bytes} bytes"
                )
            data.extend(raw)
            continue

        pending = raw
        try:
            while pending:
                expanded = decoder.decompress(pending, max_bytes - len(data) + 1)
                if len(expanded) > max_bytes - len(data):
                    raise DocumentTooLargeError(
                        f"Document exceeded max size of {max_bytes} bytes"
                    )
                data.extend(expanded)
                pending = decoder.unconsumed_tail
                if decoder.unused_data:
                    raise httpx.DecodingError("Unexpected data after gzip response")
        except zlib.error as exc:
            raise httpx.DecodingError("Invalid gzip response") from exc
    if decoder is not None and not decoder.eof:
        raise httpx.DecodingError("Incomplete gzip response")
    return bytes(data)


async def fetch_resource(
    url: str,
    *,
    settings: Settings,
    kind: str,
    headers: dict[str, str],
    max_bytes: int = MAX_DOCUMENT_BYTES,
    max_redirects: int = MAX_REDIRECTS,
    transport: httpx.AsyncBaseTransport | None = None,
) -> FetchedResource:
    """Fetch one bounded resource without automatic or unchecked redirects."""
    if kind not in {"html", "feed"}:
        raise ValueError("Unknown document kind")
    timeout = httpx.Timeout(settings.fetch_timeout_seconds)
    try:
        async with asyncio.timeout(settings.fetch_timeout_seconds):
            await _validate_url(url, settings)
            async with httpx.AsyncClient(
                follow_redirects=False,
                timeout=timeout,
                headers={**headers, "Accept-Encoding": "gzip, identity"},
                transport=transport,
                trust_env=True,
            ) as client:
                current_url = url
                visited: set[str] = set()
                for hop in range(max_redirects + 1):
                    if current_url in visited:
                        raise ValueError("Redirect loop")
                    visited.add(current_url)
                    async with client.stream("GET", current_url) as response:
                        if response.status_code in REDIRECT_STATUSES:
                            location = response.headers.get("location")
                            if not location:
                                raise ValueError(
                                    "Redirect response missing Location header"
                                )
                            if hop >= max_redirects:
                                raise ValueError("Too many redirects")
                            next_url = urljoin(str(response.url), location)
                            await _validate_url(next_url, settings)
                            current_url = next_url
                            continue

                        response.raise_for_status()
                        content_type = response.headers.get("content-type")
                        _check_content_type(content_type, kind)
                        data = await _read_bounded(response, max_bytes)
                        content_location = None
                        if response.headers.get("content-location"):
                            try:
                                content_location = urljoin(
                                    str(response.url),
                                    response.headers["content-location"],
                                )
                            except ValueError:
                                pass  # Optional malformed metadata cannot invalidate a body.
                        return FetchedResource(
                            final_url=str(response.url),
                            content_type=content_type,
                            encoding=response.encoding or "utf-8",
                            data=data,
                            content_location=content_location,
                        )
    except TimeoutError as exc:
        raise httpx.ReadTimeout("Outbound fetch timed out") from exc
    raise ValueError("Too many redirects")
