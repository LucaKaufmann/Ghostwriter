"""YouTube channel URL resolver — resolves various YouTube channel URL formats to RSS feed URLs."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

_YOUTUBE_RSS_BASE = "https://www.youtube.com/feeds/videos.xml?channel_id="

# Pattern: already a YouTube RSS feed URL
_RSS_FEED_PATTERN = re.compile(
    r"youtube\.com/feeds/videos\.xml\?channel_id=(?P<id>UC[\w-]+)"
)

# Pattern: /channel/UC... URL
_CHANNEL_ID_PATTERN = re.compile(
    r"youtube\.com/channel/(?P<id>UC[\w-]+)"
)


@dataclass
class ResolvedChannel:
    """Result of resolving a YouTube channel URL."""

    rss_feed_url: str
    channel_id: str
    channel_title: str | None = None


async def resolve_youtube_channel(url: str) -> ResolvedChannel:
    """
    Resolve a YouTube channel URL to its RSS feed URL.

    Accepts:
    - youtube.com/@handle
    - youtube.com/channel/UC...
    - youtube.com/c/Name
    - youtube.com/user/Name
    - youtube.com/feeds/videos.xml?channel_id=UC...

    Returns:
        ResolvedChannel with RSS feed URL and channel metadata.

    Raises:
        ValueError: If the URL cannot be resolved.
    """
    url = url.strip()

    # If it's already an RSS feed URL, extract channel_id directly
    rss_match = _RSS_FEED_PATTERN.search(url)
    if rss_match:
        channel_id = rss_match.group("id")
        return ResolvedChannel(
            rss_feed_url=f"{_YOUTUBE_RSS_BASE}{channel_id}",
            channel_id=channel_id,
        )

    # If it's a /channel/UC... URL, extract directly
    channel_match = _CHANNEL_ID_PATTERN.search(url)
    if channel_match:
        channel_id = channel_match.group("id")
        return await _fetch_channel_metadata(channel_id)

    # For @handle, /c/Name, /user/Name — scrape the page to find canonical channel_id
    if not url.startswith("http"):
        url = f"https://www.youtube.com/{url}" if url.startswith("@") else f"https://{url}"

    return await _resolve_from_page(url)


async def _resolve_from_page(url: str) -> ResolvedChannel:
    """Scrape a YouTube page to find the canonical channel ID."""
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=15,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; Ghostwriter/1.0)",
                "Accept-Language": "en-US,en;q=0.9",
            },
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            html = response.text
    except httpx.HTTPError as e:
        raise ValueError(f"Failed to fetch YouTube page: {e}") from e

    # Look for canonical channel URL in meta tags or page content
    # Pattern: <meta itemprop="channelId" content="UC...">
    channel_id_match = re.search(
        r'<meta\s+itemprop=["\']channelId["\']\s+content=["\'](?P<id>UC[\w-]+)["\']',
        html,
    )
    if not channel_id_match:
        # Fallback: look for /channel/UC... in any link
        channel_id_match = re.search(r'/channel/(?P<id>UC[\w-]+)', html)

    if not channel_id_match:
        # Fallback: look for "externalId":"UC..."
        channel_id_match = re.search(r'"externalId"\s*:\s*"(?P<id>UC[\w-]+)"', html)

    if not channel_id_match:
        raise ValueError(
            f"Could not find channel ID on page: {url}. "
            "Try using the channel's /channel/UC... URL instead."
        )

    channel_id = channel_id_match.group("id")

    # Try to extract channel title from <title> tag
    title_match = re.search(r"<title>(?P<title>[^<]+)</title>", html)
    channel_title = None
    if title_match:
        raw_title = title_match.group("title").strip()
        # YouTube titles end with " - YouTube"
        channel_title = re.sub(r"\s*-\s*YouTube\s*$", "", raw_title).strip() or None

    return ResolvedChannel(
        rss_feed_url=f"{_YOUTUBE_RSS_BASE}{channel_id}",
        channel_id=channel_id,
        channel_title=channel_title,
    )


async def _fetch_channel_metadata(channel_id: str) -> ResolvedChannel:
    """Fetch channel title from the RSS feed itself."""
    rss_url = f"{_YOUTUBE_RSS_BASE}{channel_id}"
    channel_title = None

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(rss_url)
            if response.status_code == 200:
                # Extract <title> from Atom feed
                title_match = re.search(
                    r"<title>(?P<title>[^<]+)</title>", response.text
                )
                if title_match:
                    channel_title = title_match.group("title").strip() or None
    except httpx.HTTPError:
        pass  # Non-fatal, we already have the channel_id

    return ResolvedChannel(
        rss_feed_url=rss_url,
        channel_id=channel_id,
        channel_title=channel_title,
    )
