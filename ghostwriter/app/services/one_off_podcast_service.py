"""One-off podcast source ingestion service."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlparse
from uuid import UUID

from sqlmodel import Session

from app.core.config import Settings, get_settings
from app.models.digest import Digest, DigestArticle
from app.models.podcast_episode import PodcastEpisode
from app.services.content_processor import ContentProcessor, ExtractedArticle
from app.services.epub_generator import EpubGenerator
from app.services.podcast_service import podcast_service
from app.worker.bindery import get_or_create_synthetic_feed

ONE_OFF_SOURCE_LABEL = "One-off Podcast"
ONE_OFF_MAX_SOURCES = 20
ONE_OFF_MAX_TEXT_CHARS = 120_000
ONE_OFF_MIN_CONTENT_CHARS = 80


class OneOffPodcastError(ValueError):
    """Raised when a one-off podcast request cannot be created."""


@dataclass(frozen=True)
class OneOffPodcastSourceInput:
    """Source supplied by the one-off podcast API."""

    type: Literal["url", "text"]
    title: str | None = None
    url: str | None = None
    content: str | None = None


@dataclass(frozen=True)
class NormalizedOneOffSource:
    """Source ready to persist as a digest article."""

    title: str
    url: str
    content: str
    word_count: int


class OneOffPodcastService:
    """Create digest-backed podcast episodes from ad hoc source bundles."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.content_processor = ContentProcessor(self.settings)

    async def create_episode(
        self,
        session: Session,
        *,
        title: str | None,
        brief: str | None,
        sources: list[OneOffPodcastSourceInput],
        user_id: UUID | None,
    ) -> PodcastEpisode:
        """Create a completed manual digest and queue podcast generation."""
        normalized = await self.normalize_sources(sources)
        if not normalized:
            raise OneOffPodcastError("No usable sources found")

        now = datetime.utcnow()
        filename = self._build_digest_filename(title, now)
        digest = Digest(
            filename=filename,
            period="manual",
            status="processing",
            stage="compiling",
            article_count=len(normalized),
            created_at=now,
            total_feeds=1,
            feeds_fetched=1,
            total_articles=len(normalized),
            articles_enriched=len(normalized),
        )
        session.add(digest)
        session.commit()
        session.refresh(digest)

        feed = get_or_create_synthetic_feed(session, "one_off")
        lead_in = self._build_context_lead_in(title=title, brief=brief)

        articles: list[DigestArticle] = []
        epub_articles: list[ExtractedArticle] = []
        for index, source in enumerate(normalized):
            content = source.content
            if lead_in:
                content = f"{lead_in}\n\n{content}"
            epub_articles.append(
                ExtractedArticle(
                    guid=source.url,
                    url=source.url,
                    title=source.title,
                    content=content,
                    author=None,
                    word_count=source.word_count,
                    is_summary=False,
                    ai_failed=False,
                    processing_ms=0,
                    feed_title=ONE_OFF_SOURCE_LABEL,
                    content_type="article",
                )
            )
            article = DigestArticle(
                digest_id=digest.id,
                feed_id=feed.id,
                title=source.title,
                url=source.url,
                mode="raw",
                word_count=source.word_count,
                ai_failed=False,
                processing_ms=0,
                content=content,
                author=None,
                feed_title=ONE_OFF_SOURCE_LABEL,
                sort_order=index,
                content_type="article",
            )
            session.add(article)
            articles.append(article)

        session.commit()
        for article in articles:
            session.refresh(article)

        try:
            EpubGenerator(self.settings).generate(
                articles=epub_articles,
                period="manual",
                date=now,
                output_filename=filename,
            )
        except Exception as exc:
            digest.status = "failed"
            digest.stage = "failed"
            digest.error_message = f"Failed to generate one-off digest EPUB: {exc}"
            session.add(digest)
            session.commit()
            raise OneOffPodcastError(digest.error_message) from exc

        digest.status = "completed"
        digest.stage = "completed"
        digest.completed_at = datetime.utcnow()
        session.add(digest)
        session.commit()
        session.refresh(digest)

        episode = podcast_service.queue_episode_generation(
            session,
            digest_id=digest.id,
            user_id=user_id,
            force=False,
        )
        episode.trigger = "one_off"
        episode.updated_at = datetime.utcnow()
        session.add(episode)
        session.commit()
        session.refresh(episode)
        return episode

    async def normalize_sources(
        self,
        sources: list[OneOffPodcastSourceInput],
    ) -> list[NormalizedOneOffSource]:
        """Validate, extract, and normalize caller-supplied sources."""
        if not sources:
            raise OneOffPodcastError("At least one source is required")
        if len(sources) > ONE_OFF_MAX_SOURCES:
            raise OneOffPodcastError(
                f"At most {ONE_OFF_MAX_SOURCES} sources are supported"
            )

        normalized: list[NormalizedOneOffSource] = []
        for index, source in enumerate(sources, start=1):
            if source.type == "text":
                item = self._normalize_text_source(source, index)
            elif source.type == "url":
                item = await self._normalize_url_source(source, index)
            else:
                raise OneOffPodcastError(f"Unsupported source type: {source.type}")
            if item is not None:
                normalized.append(item)

        if not normalized:
            raise OneOffPodcastError("No usable sources found")
        return normalized

    def _normalize_text_source(
        self,
        source: OneOffPodcastSourceInput,
        index: int,
    ) -> NormalizedOneOffSource | None:
        content = self._normalize_content(source.content or "")
        if not content:
            raise OneOffPodcastError(f"Text source {index} is empty")
        if len(content) > ONE_OFF_MAX_TEXT_CHARS:
            raise OneOffPodcastError(
                f"Text source {index} exceeds {ONE_OFF_MAX_TEXT_CHARS} characters"
            )
        if len(content) < ONE_OFF_MIN_CONTENT_CHARS:
            return None

        title = self._normalize_title(source.title) or f"Document {index}"
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
        return NormalizedOneOffSource(
            title=title,
            url=f"one-off://source/{digest}",
            content=content,
            word_count=ContentProcessor.count_words(content),
        )

    async def _normalize_url_source(
        self,
        source: OneOffPodcastSourceInput,
        index: int,
    ) -> NormalizedOneOffSource | None:
        url = (source.url or "").strip()
        if not url:
            raise OneOffPodcastError(f"URL source {index} is missing a URL")

        content = await self.content_processor.extract_content(url)
        content = self._normalize_content(content or "")
        if len(content) < ONE_OFF_MIN_CONTENT_CHARS:
            return None

        title = self._normalize_title(source.title) or self._title_from_url(url, index)
        return NormalizedOneOffSource(
            title=title,
            url=url,
            content=content,
            word_count=ContentProcessor.count_words(content),
        )

    @staticmethod
    def _normalize_title(value: str | None) -> str:
        return re.sub(r"\s+", " ", value or "").strip()[:240]

    @staticmethod
    def _normalize_content(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()

    @staticmethod
    def _title_from_url(url: str, index: int) -> str:
        parsed = urlparse(url)
        path = parsed.path.strip("/").split("/")[-1]
        if path:
            title = re.sub(r"[-_]+", " ", path.rsplit(".", 1)[0]).strip()
            if title:
                return title[:240]
        if parsed.hostname:
            return parsed.hostname[:240]
        return f"Source {index}"

    @staticmethod
    def _slugify(value: str | None) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value or "").strip("-").lower()
        return cleaned[:48] or "one-off-podcast"

    def _build_digest_filename(self, title: str | None, created_at: datetime) -> str:
        timestamp = created_at.strftime("%Y-%m-%d_%H%M%S")
        return f"{timestamp}_{self._slugify(title)}.epub"

    @staticmethod
    def _build_context_lead_in(title: str | None, brief: str | None) -> str:
        lines: list[str] = []
        cleaned_title = re.sub(r"\s+", " ", title or "").strip()
        cleaned_brief = re.sub(r"\s+", " ", brief or "").strip()
        if cleaned_title:
            lines.append(f"Episode title: {cleaned_title}")
        if cleaned_brief:
            lines.append(f"Caller brief: {cleaned_brief}")
        return "\n".join(lines)


def one_off_source_from_payload(payload: Any) -> OneOffPodcastSourceInput:
    """Convert API payload objects into service input without coupling to Pydantic."""
    return OneOffPodcastSourceInput(
        type=payload.type,
        title=payload.title,
        url=payload.url,
        content=payload.content,
    )


one_off_podcast_service = OneOffPodcastService()
