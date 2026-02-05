"""Content extraction and processing using Trafilatura."""

import asyncio
import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import feedparser
import trafilatura
from trafilatura.settings import use_config

from app.core.config import Settings, get_settings
from app.core.net import validate_public_url

logger = logging.getLogger(__name__)

# Configure trafilatura for better extraction
trafilatura_config = use_config()
trafilatura_config.set("DEFAULT", "EXTRACTION_TIMEOUT", "30")


@dataclass
class ParsedArticle:
    """Represents a parsed article from an RSS feed."""

    guid: str
    url: str
    title: str
    content_url: str | None = None
    published: str | None = None
    author: str | None = None


@dataclass
class ExtractedArticle:
    """Represents an extracted and optionally summarized article."""

    guid: str
    url: str
    title: str
    content: str
    author: str | None = None
    word_count: int = 0
    is_summary: bool = False
    ai_failed: bool = False
    processing_ms: int = 0


class ContentProcessor:
    """
    Content extraction and RSS parsing service.

    Uses Trafilatura for article extraction and feedparser for RSS parsing.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        """
        Initialize the content processor.

        Args:
            settings: Application settings. Uses default if not provided.
        """
        self.settings = settings or get_settings()
        self._executor = ThreadPoolExecutor(max_workers=4)

    async def parse_feed(
        self, feed_url: str, max_entries: int | None = None
    ) -> list[ParsedArticle]:
        """
        Parse an RSS/Atom feed and return article metadata.

        Args:
            feed_url: URL of the RSS feed.
            max_entries: Optional cap on number of entries to parse.

        Returns:
            List of ParsedArticle objects.
        """
        try:
            validate_public_url(feed_url, self.settings)
            loop = asyncio.get_event_loop()
            feed = await loop.run_in_executor(
                self._executor,
                lambda: feedparser.parse(
                    feed_url,
                    request_headers={"User-Agent": "Ghostwriter/1.0"},
                ),
            )

            if feed.bozo and not feed.entries:
                logger.error(f"Failed to parse feed {feed_url}: {feed.bozo_exception}")
                return []

            def _is_media_type(value: str | None) -> bool:
                if not value:
                    return False
                lowered = value.lower()
                return (
                    lowered.startswith("audio/")
                    or lowered.startswith("video/")
                    or lowered in {"application/octet-stream"}
                )

            def _looks_like_media_url(value: str | None) -> bool:
                if not value:
                    return False
                lowered = value.lower()
                return lowered.endswith(
                    (
                        ".mp3",
                        ".m4a",
                        ".aac",
                        ".ogg",
                        ".opus",
                        ".wav",
                        ".flac",
                        ".mp4",
                        ".m4v",
                        ".mov",
                        ".webm",
                        ".mkv",
                    )
                )

            def _extract_media_url(entry: dict) -> str | None:
                media_content = entry.get("media_content") or []
                for item in media_content:
                    if not isinstance(item, dict):
                        continue
                    url_value = item.get("url") or item.get("href")
                    if url_value and (_is_media_type(item.get("type")) or _looks_like_media_url(url_value)):
                        return url_value

                enclosures = entry.get("enclosures") or []
                for item in enclosures:
                    if not isinstance(item, dict):
                        continue
                    url_value = item.get("url") or item.get("href")
                    if url_value and (_is_media_type(item.get("type")) or _looks_like_media_url(url_value)):
                        return url_value

                links = entry.get("links") or []
                for item in links:
                    if not isinstance(item, dict):
                        continue
                    if item.get("rel") != "enclosure":
                        continue
                    url_value = item.get("href") or item.get("url")
                    if url_value and (_is_media_type(item.get("type")) or _looks_like_media_url(url_value)):
                        return url_value

                for collection in (media_content, enclosures, links):
                    for item in collection:
                        if not isinstance(item, dict):
                            continue
                        url_value = item.get("url") or item.get("href")
                        if url_value:
                            return url_value

                return None

            limit = self.settings.max_articles_per_feed
            if max_entries is not None:
                limit = max_entries

            articles = []
            for entry in feed.entries[:limit]:
                # Use GUID if available, otherwise hash the URL
                guid = entry.get("id") or entry.get("guid")
                url = entry.get("link", "")
                content_url = _extract_media_url(entry)

                if not guid:
                    guid = hashlib.sha256(url.encode()).hexdigest()[:16]

                articles.append(
                    ParsedArticle(
                        guid=guid,
                        url=url,
                        content_url=content_url,
                        title=entry.get("title", "Untitled"),
                        published=entry.get("published"),
                        author=entry.get("author"),
                    )
                )

            logger.info(f"Parsed {len(articles)} articles from {feed_url}")
            return articles

        except ValueError as e:
            logger.warning(f"Blocked feed URL (unsafe): {feed_url} - {e}")
            return []
        except Exception as e:
            logger.error(f"Error parsing feed {feed_url}: {e}")
            return []

    async def extract_content(self, url: str) -> str | None:
        """
        Extract main article content from a URL using Trafilatura.

        Args:
            url: The article URL.

        Returns:
            Extracted text content or None if extraction failed.
        """
        try:
            validate_public_url(url, self.settings)
            loop = asyncio.get_event_loop()

            # Fetch and extract in executor to avoid blocking
            def _extract() -> str | None:
                downloaded = trafilatura.fetch_url(url)
                if not downloaded:
                    return None

                return trafilatura.extract(
                    downloaded,
                    config=trafilatura_config,
                    include_comments=False,
                    include_tables=True,
                    favor_precision=True,
                    output_format="txt",
                )

            content = await asyncio.wait_for(
                loop.run_in_executor(self._executor, _extract),
                timeout=self.settings.fetch_timeout_seconds,
            )

            if content:
                logger.debug(f"Extracted {len(content)} chars from {url}")
            else:
                logger.warning(f"No content extracted from {url}")

            return content

        except ValueError as e:
            logger.warning(f"Blocked URL fetch (unsafe): {url} - {e}")
            return None
        except asyncio.TimeoutError:
            logger.error(f"Timeout extracting content from {url}")
            return None
        except Exception as e:
            logger.error(f"Error extracting content from {url}: {e}")
            return None

    @staticmethod
    def count_words(text: str) -> int:
        """
        Count words in text.

        Args:
            text: The text to count.

        Returns:
            Word count.
        """
        return len(text.split())
