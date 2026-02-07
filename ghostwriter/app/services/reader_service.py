"""Utilities for fetching web articles for in-browser reader mode.

This is intentionally lightweight: we fetch the original HTML (SSRF-safe) and
let the web client run a Readability-style extraction (matching mobile).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import httpx

from app.core.config import Settings
from app.core.net import validate_public_url


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

# Avoid proxying unbounded responses (both for latency and memory safety).
MAX_HTML_BYTES = 5_000_000  # 5 MB


@dataclass(frozen=True)
class FetchedHtmlDocument:
    """Result of fetching an HTML document."""

    url: str
    final_url: str
    content_type: str | None
    html: str
    fetched_at: datetime
    size_bytes: int


class NonHtmlContentError(RuntimeError):
    """Raised when the upstream response is not HTML."""


class DocumentTooLargeError(RuntimeError):
    """Raised when the upstream document exceeds MAX_HTML_BYTES."""


async def fetch_html_document(
    url: str,
    *,
    settings: Settings,
    user_agent: str = DEFAULT_USER_AGENT,
    max_bytes: int = MAX_HTML_BYTES,
) -> FetchedHtmlDocument:
    """Fetch raw HTML for a URL with SSRF protections and size limits."""
    validate_public_url(url, settings)

    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "DNT": "1",
        "Upgrade-Insecure-Requests": "1",
    }

    timeout = httpx.Timeout(settings.fetch_timeout_seconds)
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=timeout,
        headers=headers,
    ) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()

            content_type = response.headers.get("content-type")
            if content_type:
                lowered = content_type.lower()
                if "text/html" not in lowered and "application/xhtml+xml" not in lowered:
                    raise NonHtmlContentError(f"Unsupported content-type: {content_type}")

            data = bytearray()
            async for chunk in response.aiter_bytes():
                data.extend(chunk)
                if len(data) > max_bytes:
                    raise DocumentTooLargeError(
                        f"Document exceeded max size of {max_bytes} bytes"
                    )

            # Prefer httpx's detected encoding if available, otherwise fall back.
            encoding = response.encoding or "utf-8"
            try:
                html = bytes(data).decode(encoding, errors="replace")
            except LookupError:
                html = bytes(data).decode("utf-8", errors="replace")

            return FetchedHtmlDocument(
                url=url,
                final_url=str(response.url),
                content_type=content_type,
                html=html,
                fetched_at=datetime.utcnow(),
                size_bytes=len(data),
            )

