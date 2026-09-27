"""Utilities for fetching web articles for in-browser reader mode.

This is intentionally lightweight: we fetch the original HTML and
let the web client run a Readability-style extraction (matching mobile).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.core.config import Settings
from app.services.outbound_fetch import DocumentTooLargeError as DocumentTooLargeError
from app.services.outbound_fetch import NonHtmlContentError as NonHtmlContentError
from app.services.outbound_fetch import fetch_resource

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


async def fetch_html_document(
    url: str,
    *,
    settings: Settings,
    user_agent: str = DEFAULT_USER_AGENT,
    max_bytes: int = MAX_HTML_BYTES,
) -> FetchedHtmlDocument:
    """Fetch bounded HTML after validating each redirect URL."""

    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "DNT": "1",
        "Upgrade-Insecure-Requests": "1",
    }

    fetched = await fetch_resource(
        url,
        settings=settings,
        kind="html",
        headers=headers,
        max_bytes=max_bytes,
    )
    try:
        html = fetched.data.decode(fetched.encoding, errors="replace")
    except LookupError:
        html = fetched.data.decode("utf-8", errors="replace")
    return FetchedHtmlDocument(
        url=url,
        final_url=fetched.final_url,
        content_type=fetched.content_type,
        html=html,
        fetched_at=datetime.utcnow(),
        size_bytes=len(fetched.data),
    )
