"""Bounded HTTP fetches for feeds and web documents.

URLs are checked before each connection, including every redirect destination.
The transport resolves hosts separately, so this is not a DNS pinning guarantee.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from urllib.parse import urljoin

import httpx

from app.core.config import Settings
from app.core.net import validate_public_url

MAX_DOCUMENT_BYTES = 5_000_000
MAX_REDIRECTS = 5
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


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


def _check_content_type(content_type: str | None, kind: str) -> None:
    if not content_type:
        return
    mime = content_type.partition(";")[0].strip().lower()
    if kind == "html" and mime not in {"text/html", "application/xhtml+xml"}:
        raise NonHtmlContentError(f"Unsupported content-type: {content_type}")
    if kind == "feed" and mime not in {
        "application/rss+xml",
        "application/atom+xml",
        "application/xml",
        "text/xml",
        "text/plain",
        "application/octet-stream",
    } and not mime.endswith("+xml"):
        raise NonFeedContentError(f"Unsupported feed content-type: {content_type}")


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
    validate_public_url(url, settings)
    timeout = httpx.Timeout(settings.fetch_timeout_seconds)
    async with asyncio.timeout(settings.fetch_timeout_seconds):
        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=timeout,
            headers=headers,
            transport=transport,
            trust_env=False,
        ) as client:
            current_url = url
            visited: set[str] = set()
            for hop in range(max_redirects + 1):
                validate_public_url(current_url, settings)
                if current_url in visited:
                    raise ValueError("Redirect loop")
                visited.add(current_url)
                async with client.stream("GET", current_url) as response:
                    if response.status_code in REDIRECT_STATUSES:
                        location = response.headers.get("location")
                        if not location:
                            raise ValueError("Redirect response missing Location header")
                        if hop >= max_redirects:
                            raise ValueError("Too many redirects")
                        next_url = urljoin(str(response.url), location)
                        validate_public_url(next_url, settings)
                        current_url = next_url
                        continue

                    response.raise_for_status()
                    content_type = response.headers.get("content-type")
                    _check_content_type(content_type, kind)
                    length = response.headers.get("content-length")
                    if length and length.isdecimal() and int(length) > max_bytes:
                        raise DocumentTooLargeError(
                            f"Document exceeded max size of {max_bytes} bytes"
                        )
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        data.extend(chunk)
                        if len(data) > max_bytes:
                            raise DocumentTooLargeError(
                                f"Document exceeded max size of {max_bytes} bytes"
                            )
                    return FetchedResource(
                        final_url=str(response.url),
                        content_type=content_type,
                        encoding=response.encoding or "utf-8",
                        data=bytes(data),
                    )
    raise ValueError("Too many redirects")
