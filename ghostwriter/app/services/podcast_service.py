"""Podcast digest generation service."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import secrets
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
from sqlmodel import Session, select

from app.core.config import Settings, get_settings
from app.core.database import engine
from app.models.article_feedback import ArticleFeedback, ArticleFeedbackUpsert
from app.models.client_config import ClientConfig
from app.models.digest import Digest, DigestArticle
from app.models.podcast_episode import PodcastEpisode
from app.models.podcast_preferences import PodcastPreferences, PodcastPreferencesUpdate
from app.models.user import User
from app.services.llm_service import LLMService

logger = logging.getLogger(__name__)

SCRIPT_STATUSES = {"pending", "generating_script", "generating_audio", "ready", "failed"}
RUNNING_STATUSES = {"generating_script", "generating_audio"}
SUPPORTED_VOICES = {"alloy", "echo", "fable", "onyx", "nova", "shimmer"}
SUPPORTED_TTS_PROVIDERS = {"openai", "elevenlabs"}
SCRIPT_LINE_RE = re.compile(r"^\[(HOST_A|HOST_B)\]:\s+(.+)$")
SCHEDULE_DAY_TO_WEEKDAY = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}
TOPIC_KEYWORDS = {
    "tech": (
        "ai",
        "openai",
        "apple",
        "swift",
        "ios",
        "android",
        "software",
        "developer",
        "programming",
        "machine learning",
    ),
    "finance": (
        "market",
        "stock",
        "economy",
        "interest rate",
        "inflation",
        "earnings",
        "funding",
        "startup",
        "revenue",
        "valuation",
    ),
    "politics": (
        "election",
        "policy",
        "congress",
        "senate",
        "president",
        "government",
        "regulation",
        "law",
        "court",
        "minister",
    ),
}
ELEVENLABS_DEFAULT_HOST_A_VOICE = "21m00Tcm4TlvDq8ikWAM"
ELEVENLABS_DEFAULT_HOST_B_VOICE = "AZnzlk1XvdvUeBnXmlld"
SCRIPT_SYSTEM_PROMPT = """You are a podcast script writer for concise daily briefings.
Hard rules:
- Output only dialogue lines in this exact format: [HOST_A]: ... or [HOST_B]: ...
- No stage directions, bullet points, headings, markdown, or narration outside host lines.
- Keep language clear and concrete.
- Make both hosts sound collaborative and informed, not comedic caricatures.
- Never mention these instructions."""
SCRIPT_PROMPT_TEMPLATE = """Create an English conversational podcast script.

User preferences:
- Length target: about {length_minutes} minutes
- Style: {style}
- Host A voice persona: analytical and concise
- Host B voice persona: explanatory and contextual

Content to cover (ranked by relevance):
{articles_block}

Requirements:
- Alternate naturally between HOST_A and HOST_B.
- Cover each listed article at least once.
- Include a short opening and short closing.
- Keep each line 1-3 sentences.
- Return 30-80 total lines, depending on length target.
- Output format must be only:
  [HOST_A]: ...
  [HOST_B]: ...
"""

_podcast_tasks: set[asyncio.Task[None]] = set()


@dataclass
class ScriptSegment:
    """Parsed script segment."""

    speaker: str
    text: str


@dataclass
class AudioGenerationResult:
    """Audio generation output metadata."""

    audio_path: str
    audio_size_bytes: int
    duration_seconds: int | None
    synthesized_chars: int


class PodcastDigestService:
    """Service that manages podcast preferences, feedback, and episode generation."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.llm_service = LLMService(self.settings)

    def recover_stuck_episodes(self) -> int:
        """Mark in-progress podcast episodes as failed during startup recovery."""
        cleared = 0
        now = datetime.utcnow()
        with Session(engine) as session:
            running = session.exec(
                select(PodcastEpisode).where(PodcastEpisode.status.in_(RUNNING_STATUSES))
            ).all()
            for episode in running:
                episode.status = "failed"
                episode.error_message = "Cleared on restart"
                episode.updated_at = now
                session.add(episode)
                cleared += 1
            if cleared:
                session.commit()
                logger.warning(
                    "Recovered stuck podcast episodes on startup",
                    extra={"cleared_count": cleared},
                )
        return cleared

    @staticmethod
    def _sanitize_string_list(values: list[str] | None) -> list[str]:
        """Trim, deduplicate, and drop empty strings from list input."""
        if not values:
            return []
        seen: set[str] = set()
        cleaned: list[str] = []
        for raw in values:
            value = raw.strip()
            if not value:
                continue
            key = value.lower()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(value)
        return cleaned

    @staticmethod
    def _parse_schedule_time(value: str) -> tuple[int, int]:
        """Parse HH:MM schedule times and raise ValueError on bad input."""
        parts = value.strip().split(":")
        if len(parts) != 2:
            raise ValueError("schedule_time must be in HH:MM format")
        hour, minute = int(parts[0]), int(parts[1])
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("schedule_time must be in HH:MM format")
        return hour, minute

    @staticmethod
    def _ensure_supported_voice(voice: str, fallback: str) -> str:
        """Return a valid OpenAI voice or fallback."""
        normalized = voice.strip().lower()
        if normalized in SUPPORTED_VOICES:
            return normalized
        return fallback

    @staticmethod
    def _sanitize_optional_secret(value: str | None) -> str | None:
        """Normalize optional secret fields, keeping None when empty."""
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned if cleaned else None

    def _resolve_user_id(self, session: Session) -> UUID | None:
        """Resolve the current singleton user ID if a user exists."""
        user = session.exec(select(User).order_by(User.created_at.asc())).first()
        return user.id if user else None

    def resolve_user_id(self, session: Session) -> UUID | None:
        """Public wrapper for singleton user resolution."""
        return self._resolve_user_id(session)

    def get_or_create_preferences(
        self,
        session: Session,
        user_id: UUID | None = None,
    ) -> PodcastPreferences:
        """Get podcast preferences, creating a singleton row when missing."""
        prefs = session.exec(
            select(PodcastPreferences).order_by(PodcastPreferences.created_at.asc())
        ).first()
        now = datetime.utcnow()

        if prefs is None:
            prefs = PodcastPreferences(
                user_id=user_id,
                podcast_feed_token=self._generate_feed_token(),
                created_at=now,
                updated_at=now,
            )
            session.add(prefs)
            session.commit()
            session.refresh(prefs)
            return prefs

        if prefs.user_id is None and user_id is not None:
            prefs.user_id = user_id
            prefs.updated_at = now
            session.add(prefs)
            session.commit()
            session.refresh(prefs)
            return prefs

        if not prefs.podcast_feed_token:
            prefs.podcast_feed_token = self._generate_feed_token()
            prefs.updated_at = now
            session.add(prefs)
            session.commit()
            session.refresh(prefs)
        return prefs

    def update_preferences(
        self,
        session: Session,
        update: PodcastPreferencesUpdate,
        user_id: UUID | None = None,
    ) -> PodcastPreferences:
        """Update podcast preferences."""
        prefs = self.get_or_create_preferences(session, user_id=user_id)
        now = datetime.utcnow()

        if update.enabled is not None:
            prefs.enabled = update.enabled
        if update.schedule is not None:
            prefs.schedule = update.schedule
        if update.schedule_time is not None:
            hour, minute = self._parse_schedule_time(update.schedule_time)
            prefs.schedule_time = f"{hour:02d}:{minute:02d}"
        if update.schedule_day is not None:
            prefs.schedule_day = update.schedule_day
        if update.topic_weights is not None:
            prefs.topic_weights = {
                key.strip().lower(): float(value)
                for key, value in update.topic_weights.items()
                if key.strip()
            }
        if update.boost_sources is not None:
            prefs.boost_sources = self._sanitize_string_list(update.boost_sources)
        if update.boost_keywords is not None:
            prefs.boost_keywords = self._sanitize_string_list(update.boost_keywords)
        if update.filter_keywords is not None:
            prefs.filter_keywords = self._sanitize_string_list(update.filter_keywords)
        if update.preferred_length_minutes is not None:
            prefs.preferred_length_minutes = update.preferred_length_minutes
        if update.style is not None:
            prefs.style = update.style
        if update.tts_provider is not None:
            provider = update.tts_provider.strip().lower()
            if provider not in SUPPORTED_TTS_PROVIDERS:
                raise ValueError("tts_provider must be 'openai' or 'elevenlabs'")
            prefs.tts_provider = provider
        if update.openai_tts_model is not None:
            prefs.openai_tts_model = update.openai_tts_model.strip() or "tts-1"
        if update.openai_api_key is not None:
            prefs.openai_api_key = self._sanitize_optional_secret(update.openai_api_key)
        if update.elevenlabs_model_id is not None:
            prefs.elevenlabs_model_id = (
                update.elevenlabs_model_id.strip() or "eleven_turbo_v2_5"
            )
        if update.elevenlabs_api_key is not None:
            prefs.elevenlabs_api_key = self._sanitize_optional_secret(update.elevenlabs_api_key)
        if update.elevenlabs_output_format is not None:
            prefs.elevenlabs_output_format = (
                update.elevenlabs_output_format.strip() or "mp3_44100_128"
            )
        if update.host_a_voice is not None:
            voice_value = update.host_a_voice.strip()
            if prefs.tts_provider == "openai":
                prefs.host_a_voice = self._ensure_supported_voice(voice_value, "alloy")
            else:
                prefs.host_a_voice = voice_value or ELEVENLABS_DEFAULT_HOST_A_VOICE
        if update.host_b_voice is not None:
            voice_value = update.host_b_voice.strip()
            if prefs.tts_provider == "openai":
                prefs.host_b_voice = self._ensure_supported_voice(voice_value, "echo")
            else:
                prefs.host_b_voice = voice_value or ELEVENLABS_DEFAULT_HOST_B_VOICE
        if update.podcast_feed_enabled is not None:
            prefs.podcast_feed_enabled = update.podcast_feed_enabled
        if update.podcast_feed_title is not None:
            prefs.podcast_feed_title = update.podcast_feed_title.strip() or "My Ghostwriter Digest"
        if update.podcast_feed_description is not None:
            cleaned = update.podcast_feed_description.strip()
            prefs.podcast_feed_description = (
                cleaned if cleaned else "AI-generated audio digest of your RSS feeds"
            )

        if not prefs.podcast_feed_token:
            prefs.podcast_feed_token = self._generate_feed_token()

        prefs.updated_at = now
        session.add(prefs)
        session.commit()
        session.refresh(prefs)
        logger.info(
            "Podcast preferences updated",
            extra={
                "enabled": prefs.enabled,
                "schedule": prefs.schedule,
                "schedule_time": prefs.schedule_time,
                "schedule_day": prefs.schedule_day,
                "preferred_length_minutes": prefs.preferred_length_minutes,
                "style": prefs.style,
                "tts_provider": prefs.tts_provider,
                "openai_tts_model": prefs.openai_tts_model,
                "elevenlabs_model_id": prefs.elevenlabs_model_id,
                "elevenlabs_output_format": prefs.elevenlabs_output_format,
                "podcast_feed_enabled": prefs.podcast_feed_enabled,
            },
        )
        return prefs

    def get_preferences_by_feed_token(
        self,
        session: Session,
        token: str,
    ) -> PodcastPreferences | None:
        """Resolve preferences row by feed token."""
        if not token.strip():
            return None
        return session.exec(
            select(PodcastPreferences)
            .where(PodcastPreferences.podcast_feed_enabled == True)  # noqa: E712
            .where(PodcastPreferences.podcast_feed_token == token)
        ).first()

    def _generate_feed_token(self) -> str:
        """Create a private feed token."""
        return f"gwpod_{secrets.token_urlsafe(32)}"

    def upsert_feedback(
        self,
        session: Session,
        article: DigestArticle,
        payload: ArticleFeedbackUpsert,
        user_id: UUID | None = None,
    ) -> ArticleFeedback:
        """Create or update article feedback."""
        statement = select(ArticleFeedback).where(ArticleFeedback.article_id == article.id)
        if user_id is None:
            statement = statement.where(ArticleFeedback.user_id == None)  # noqa: E711
        else:
            statement = statement.where(ArticleFeedback.user_id == user_id)
        feedback = session.exec(statement).first()

        now = datetime.utcnow()
        if feedback is None:
            feedback = ArticleFeedback(
                user_id=user_id,
                article_id=article.id,
                digest_id=article.digest_id,
                created_at=now,
                updated_at=now,
            )
        feedback.rating = payload.rating
        feedback.read_duration_sec = payload.read_duration_sec
        if payload.bookmarked is not None:
            feedback.bookmarked = payload.bookmarked
        if payload.shared is not None:
            feedback.shared = payload.shared
        feedback.updated_at = now

        session.add(feedback)
        session.commit()
        session.refresh(feedback)
        return feedback

    def delete_feedback(
        self,
        session: Session,
        article_id: UUID,
        user_id: UUID | None = None,
    ) -> bool:
        """Delete feedback row for one article."""
        statement = select(ArticleFeedback).where(ArticleFeedback.article_id == article_id)
        if user_id is None:
            statement = statement.where(ArticleFeedback.user_id == None)  # noqa: E711
        else:
            statement = statement.where(ArticleFeedback.user_id == user_id)
        feedback = session.exec(statement).first()
        if feedback is None:
            return False
        session.delete(feedback)
        session.commit()
        return True

    def queue_episode_generation(
        self,
        session: Session,
        digest_id: UUID,
        *,
        user_id: UUID | None = None,
        force: bool = False,
    ) -> PodcastEpisode:
        """Queue podcast generation for a digest and schedule a background task."""
        digest = session.get(Digest, digest_id)
        if digest is None:
            raise ValueError("Digest not found")
        if digest.status != "completed":
            raise ValueError("Digest must be completed before podcast generation")

        now = datetime.utcnow()
        episode = session.exec(
            select(PodcastEpisode).where(PodcastEpisode.digest_id == digest_id)
        ).first()

        if episode is not None:
            if episode.status in RUNNING_STATUSES:
                logger.info(
                    "Podcast generation already running for digest",
                    extra={"digest_id": str(digest_id), "episode_id": str(episode.id), "status": episode.status},
                )
                return episode
            if episode.status == "ready" and not force:
                logger.info(
                    "Podcast already ready for digest; skipping queue",
                    extra={"digest_id": str(digest_id), "episode_id": str(episode.id)},
                )
                return episode
            if episode.status in {"pending", "failed"} and not force:
                if episode.status == "pending":
                    logger.info(
                        "Podcast generation already pending; ensuring worker task is scheduled",
                        extra={"digest_id": str(digest_id), "episode_id": str(episode.id)},
                    )
                    self._schedule_episode_task(episode.id)
                return episode

            if force:
                if episode.audio_path and os.path.exists(episode.audio_path):
                    try:
                        os.remove(episode.audio_path)
                    except OSError:
                        logger.warning("Failed deleting old podcast audio for retry", exc_info=True)
                episode.script = None
                episode.audio_path = None
                episode.audio_size_bytes = None
                episode.duration_seconds = None
                episode.generation_cost_cents = None
                episode.article_ids = []
                episode.article_count = 0
                episode.status = "pending"
                episode.error_message = None
                episode.started_at = None
                episode.completed_at = None
                episode.updated_at = now
                session.add(episode)
                session.commit()
                session.refresh(episode)
                logger.info(
                    "Podcast episode reset for forced regeneration",
                    extra={"digest_id": str(digest_id), "episode_id": str(episode.id)},
                )
                self._schedule_episode_task(episode.id)
                return episode

            return episode

        episode = PodcastEpisode(
            digest_id=digest_id,
            user_id=user_id,
            status="pending",
            created_at=now,
            updated_at=now,
        )
        session.add(episode)
        session.commit()
        session.refresh(episode)
        logger.info(
            "Podcast episode queued",
            extra={"digest_id": str(digest_id), "episode_id": str(episode.id), "force": force},
        )
        self._schedule_episode_task(episode.id)
        return episode

    def maybe_auto_generate_for_digest(self, digest_id: UUID) -> UUID | None:
        """Run schedule checks and auto-generate a podcast episode when eligible."""
        with Session(engine) as session:
            user_id = self._resolve_user_id(session)
            prefs = self.get_or_create_preferences(session, user_id=user_id)
            if not prefs.enabled or prefs.schedule == "manual":
                logger.debug(
                    "Podcast auto-generation skipped: disabled or manual schedule",
                    extra={
                        "digest_id": str(digest_id),
                        "enabled": prefs.enabled,
                        "schedule": prefs.schedule,
                    },
                )
                return None

            digest = session.get(Digest, digest_id)
            if digest is None or digest.status != "completed" or digest.completed_at is None:
                logger.debug(
                    "Podcast auto-generation skipped: digest not eligible",
                    extra={
                        "digest_id": str(digest_id),
                        "digest_found": digest is not None,
                        "digest_status": getattr(digest, "status", None),
                    },
                )
                return None

            if not self._schedule_window_allows_generation(
                session,
                prefs=prefs,
                completed_at=digest.completed_at,
            ):
                logger.debug(
                    "Podcast auto-generation skipped: schedule window not matched",
                    extra={
                        "digest_id": str(digest_id),
                        "schedule": prefs.schedule,
                        "schedule_time": prefs.schedule_time,
                        "schedule_day": prefs.schedule_day,
                    },
                )
                return None

            episode = self.queue_episode_generation(
                session,
                digest_id,
                user_id=prefs.user_id,
                force=False,
            )
            logger.info(
                "Podcast auto-generation queued",
                extra={"digest_id": str(digest_id), "episode_id": str(episode.id)},
            )
            return episode.id

    def _resolve_timezone(self, session: Session) -> ZoneInfo:
        """Resolve schedule timezone from client config or global settings."""
        config = session.exec(select(ClientConfig)).first()
        timezone_name = config.timezone if config and config.timezone else self.settings.timezone
        try:
            return ZoneInfo(timezone_name)
        except Exception:
            logger.warning("Invalid timezone '%s', using UTC", timezone_name)
            return ZoneInfo("UTC")

    def _schedule_window_allows_generation(
        self,
        session: Session,
        *,
        prefs: PodcastPreferences,
        completed_at: datetime,
    ) -> bool:
        """Check if digest completion matches user schedule and dedupe window."""
        tz = self._resolve_timezone(session)
        scheduled_hour, scheduled_minute = self._parse_schedule_time(prefs.schedule_time)
        completed_local = completed_at.replace(tzinfo=timezone.utc).astimezone(tz)

        if (completed_local.hour, completed_local.minute) < (
            scheduled_hour,
            scheduled_minute,
        ):
            return False

        if prefs.schedule == "daily":
            start_local = datetime.combine(completed_local.date(), time.min, tzinfo=tz)
            end_local = start_local + timedelta(days=1)
        elif prefs.schedule == "weekly":
            expected_weekday = SCHEDULE_DAY_TO_WEEKDAY.get(prefs.schedule_day, 0)
            if completed_local.weekday() != expected_weekday:
                return False
            week_start_date = completed_local.date() - timedelta(days=completed_local.weekday())
            start_local = datetime.combine(week_start_date, time.min, tzinfo=tz)
            end_local = start_local + timedelta(days=7)
        else:
            return False

        start_utc = start_local.astimezone(timezone.utc).replace(tzinfo=None)
        end_utc = end_local.astimezone(timezone.utc).replace(tzinfo=None)

        existing_statement = select(PodcastEpisode).where(
            PodcastEpisode.created_at >= start_utc,
            PodcastEpisode.created_at < end_utc,
            PodcastEpisode.status != "failed",
        )
        if prefs.user_id is None:
            existing_statement = existing_statement.where(PodcastEpisode.user_id == None)  # noqa: E711
        else:
            existing_statement = existing_statement.where(PodcastEpisode.user_id == prefs.user_id)
        existing = session.exec(existing_statement).first()
        return existing is None

    def _schedule_episode_task(self, episode_id: UUID) -> None:
        """Schedule one podcast generation background task."""
        logger.info("Scheduling podcast generation task", extra={"episode_id": str(episode_id)})
        task = asyncio.create_task(
            self._run_episode_generation(episode_id),
            name=f"podcast_episode_{episode_id}",
        )
        _podcast_tasks.add(task)
        task.add_done_callback(_podcast_tasks.discard)

    async def _run_episode_generation(self, episode_id: UUID) -> None:
        """Run end-to-end script and audio generation for one episode."""
        now = datetime.utcnow()
        with Session(engine) as session:
            episode = session.get(PodcastEpisode, episode_id)
            if episode is None:
                return
            if episode.status in RUNNING_STATUSES:
                return
            logger.info(
                "Podcast generation started",
                extra={"episode_id": str(episode_id), "digest_id": str(episode.digest_id)},
            )
            episode.status = "generating_script"
            episode.error_message = None
            episode.started_at = now
            episode.updated_at = now
            session.add(episode)
            session.commit()

        try:
            with Session(engine) as session:
                episode = session.get(PodcastEpisode, episode_id)
                if episode is None:
                    return
                digest = session.get(Digest, episode.digest_id)
                if digest is None:
                    raise RuntimeError("Digest not found for episode")
                user_id = episode.user_id or self._resolve_user_id(session)
                prefs = self.get_or_create_preferences(session, user_id=user_id)
                selected_articles = self.select_articles_for_episode(
                    session,
                    digest_id=digest.id,
                    prefs=prefs,
                    user_id=user_id,
                )
                logger.info(
                    "Podcast article selection complete",
                    extra={
                        "episode_id": str(episode_id),
                        "digest_id": str(digest.id),
                        "selected_article_count": len(selected_articles),
                    },
                )

                if not selected_articles:
                    raise RuntimeError("No articles passed podcast scoring")

                script = await self.generate_script(selected_articles, prefs)
                segments = self.parse_script_segments(script)
                logger.info(
                    "Podcast script generation complete",
                    extra={
                        "episode_id": str(episode_id),
                        "digest_id": str(digest.id),
                        "script_chars": len(script),
                        "segment_count": len(segments),
                    },
                )

                episode.script = script
                episode.article_ids = [str(article.id) for article in selected_articles]
                episode.article_count = len(selected_articles)
                episode.status = "generating_audio"
                episode.updated_at = datetime.utcnow()
                session.add(episode)
                session.commit()

            audio_result = await self.generate_audio(episode_id, segments, prefs)

            with Session(engine) as session:
                episode = session.get(PodcastEpisode, episode_id)
                if episode is None:
                    return
                episode.audio_path = audio_result.audio_path
                episode.audio_size_bytes = audio_result.audio_size_bytes
                episode.duration_seconds = audio_result.duration_seconds
                episode.generation_cost_cents = self._estimate_generation_cost_cents(
                    script_chars=len(episode.script or ""),
                    tts_chars=audio_result.synthesized_chars,
                )
                episode.status = "ready"
                episode.error_message = None
                episode.updated_at = datetime.utcnow()
                episode.completed_at = datetime.utcnow()
                session.add(episode)
                session.commit()
                logger.info(
                    "Podcast generation completed",
                    extra={
                        "episode_id": str(episode_id),
                        "digest_id": str(episode.digest_id),
                        "audio_size_bytes": audio_result.audio_size_bytes,
                        "duration_seconds": audio_result.duration_seconds,
                        "article_count": episode.article_count,
                        "generation_cost_cents": episode.generation_cost_cents,
                    },
                )
        except Exception as exc:
            logger.exception("Podcast episode generation failed: %s", exc)
            with Session(engine) as session:
                episode = session.get(PodcastEpisode, episode_id)
                if episode:
                    episode.status = "failed"
                    episode.error_message = str(exc)[:500]
                    episode.updated_at = datetime.utcnow()
                    session.add(episode)
                    session.commit()

    def select_articles_for_episode(
        self,
        session: Session,
        *,
        digest_id: UUID,
        prefs: PodcastPreferences,
        user_id: UUID | None,
    ) -> list[DigestArticle]:
        """Rank digest articles and pick top items for script generation."""
        articles = session.exec(
            select(DigestArticle)
            .where(DigestArticle.digest_id == digest_id)
            .order_by(DigestArticle.sort_order.asc())
        ).all()
        if not articles:
            logger.info(
                "Podcast article selection found no digest articles",
                extra={"digest_id": str(digest_id)},
            )
            return []

        feedback_profile = self._build_feedback_profile(session, user_id=user_id)
        scored: list[tuple[float, int, DigestArticle]] = []
        for article in articles:
            score = self.score_article(
                article=article,
                prefs=prefs,
                feedback_profile=feedback_profile,
            )
            if score <= 0:
                continue
            scored.append((score, article.sort_order, article))

        if not scored:
            logger.info(
                "Podcast article selection scored no eligible articles",
                extra={"digest_id": str(digest_id), "digest_article_count": len(articles)},
            )
            return []

        scored.sort(key=lambda row: (-row[0], row[1]))
        target_count = max(8, min(20, prefs.preferred_length_minutes + 4))
        selected = [row[2] for row in scored[:target_count]]
        logger.info(
            "Podcast article selection summary",
            extra={
                "digest_id": str(digest_id),
                "digest_article_count": len(articles),
                "scored_article_count": len(scored),
                "target_count": target_count,
                "selected_count": len(selected),
            },
        )
        return selected

    def _build_feedback_profile(
        self,
        session: Session,
        *,
        user_id: UUID | None,
    ) -> dict[str, tuple[int, int]]:
        """Build per-source (up_count, down_count) profile from past feedback."""
        statement = select(ArticleFeedback).where(ArticleFeedback.rating != None)  # noqa: E711
        if user_id is None:
            statement = statement.where(ArticleFeedback.user_id == None)  # noqa: E711
        else:
            statement = statement.where(ArticleFeedback.user_id == user_id)
        feedback_rows = session.exec(statement).all()

        profile: dict[str, tuple[int, int]] = {}
        for feedback in feedback_rows:
            article = session.get(DigestArticle, feedback.article_id)
            if not article:
                continue
            source = (article.feed_title or "").strip().lower()
            if not source:
                continue
            up, down = profile.get(source, (0, 0))
            if feedback.rating == "up":
                up += 1
            elif feedback.rating == "down":
                down += 1
            profile[source] = (up, down)
        return profile

    def score_article(
        self,
        *,
        article: DigestArticle,
        prefs: PodcastPreferences,
        feedback_profile: dict[str, tuple[int, int]],
    ) -> float:
        """Score one article against preferences and past feedback."""
        score = 1.0
        topic = self._infer_topic(article)
        topic_weight = prefs.topic_weights.get(topic, prefs.topic_weights.get("general", 0.5))
        score *= max(topic_weight, 0.0)

        source = (article.feed_title or "").strip().lower()
        boosted_sources = {value.lower() for value in prefs.boost_sources}
        if source and source in boosted_sources:
            score *= 1.5

        text = f"{article.title} {article.content[:800]}".lower()
        for keyword in prefs.boost_keywords:
            if keyword.lower() in text:
                score *= 1.3

        for keyword in prefs.filter_keywords:
            if keyword.lower() in text:
                score *= 0.1

        if source and source in feedback_profile:
            up, down = feedback_profile[source]
            total = up + down
            if total:
                bias = (up - down) / total
                score *= max(0.6, min(1.4, 1.0 + (bias * 0.4)))

        return score

    def _infer_topic(self, article: DigestArticle) -> str:
        """Infer a rough topic category from title/content keywords."""
        text = f"{article.title} {article.content[:1000]}".lower()
        best_topic = "general"
        best_count = 0
        for topic, keywords in TOPIC_KEYWORDS.items():
            count = sum(1 for keyword in keywords if keyword in text)
            if count > best_count:
                best_topic = topic
                best_count = count
        return best_topic

    async def generate_script(
        self,
        articles: list[DigestArticle],
        prefs: PodcastPreferences,
    ) -> str:
        """Generate and validate podcast script from selected articles."""
        if not articles:
            raise RuntimeError("No articles available for script generation")

        articles_block_lines: list[str] = []
        for index, article in enumerate(articles, start=1):
            clean_snippet = re.sub(r"\s+", " ", article.content).strip()[:500]
            articles_block_lines.append(
                f"{index}. {article.title}\n"
                f"Source: {article.feed_title}\n"
                f"URL: {article.url}\n"
                f"Key points: {clean_snippet}"
            )
        articles_block = "\n\n".join(articles_block_lines)
        prompt = SCRIPT_PROMPT_TEMPLATE.format(
            length_minutes=prefs.preferred_length_minutes,
            style=prefs.style,
            articles_block=articles_block,
        )

        model = self.settings.get_llm_model_string()
        retries = 2
        for attempt in range(retries + 1):
            logger.info(
                "Generating podcast script attempt",
                extra={
                    "attempt": attempt + 1,
                    "attempts_total": retries + 1,
                    "article_count": len(articles),
                    "model": model,
                },
            )
            script, failed = await self.llm_service._run_completion(
                prompt,
                model,
                retries=1,
                system_prompt=SCRIPT_SYSTEM_PROMPT,
            )
            if failed or not script.strip():
                continue
            try:
                self.parse_script_segments(script)
                logger.info(
                    "Podcast script generated and validated",
                    extra={
                        "attempt": attempt + 1,
                        "script_chars": len(script.strip()),
                    },
                )
                return script.strip()
            except ValueError as exc:
                logger.warning(
                    "Generated podcast script failed validation (attempt %s/%s): %s",
                    attempt + 1,
                    retries + 1,
                    exc,
                )
                await asyncio.sleep(0.5 * (attempt + 1))

        raise RuntimeError("Failed to generate valid podcast script")

    @staticmethod
    def parse_script_segments(script: str) -> list[ScriptSegment]:
        """Parse script text into [HOST_A]/[HOST_B] segments."""
        lines = [line.strip() for line in script.splitlines() if line.strip()]
        if not lines:
            raise ValueError("Script is empty")

        segments: list[ScriptSegment] = []
        speakers: set[str] = set()
        for line in lines:
            match = SCRIPT_LINE_RE.match(line)
            if not match:
                raise ValueError("Script contains non-speaker lines")
            speaker = match.group(1)
            text = match.group(2).strip()
            if not text:
                raise ValueError("Script contains empty segments")
            speakers.add(speaker)
            segments.append(ScriptSegment(speaker=speaker, text=text))

        if len(segments) < 6:
            raise ValueError("Script must contain at least 6 host lines")
        if speakers != {"HOST_A", "HOST_B"}:
            raise ValueError("Script must include both HOST_A and HOST_B")
        return segments

    async def generate_audio(
        self,
        episode_id: UUID,
        segments: list[ScriptSegment],
        prefs: PodcastPreferences,
    ) -> AudioGenerationResult:
        """Synthesize audio for script segments and stitch into one MP3."""
        if not segments:
            raise RuntimeError("No script segments for audio generation")

        output_dir = Path(self.settings.output_dir) / "podcasts"
        output_dir.mkdir(parents=True, exist_ok=True)
        final_path = output_dir / f"{episode_id}.mp3"
        logger.info(
            "Podcast audio generation started",
            extra={
                "episode_id": str(episode_id),
                "segment_count": len(segments),
                "output_path": str(final_path),
            },
        )

        synthesized_chars = 0
        with tempfile.TemporaryDirectory(prefix="podcast_tts_") as tmpdir:
            segment_paths: list[Path] = []
            provider = (prefs.tts_provider or "openai").strip().lower()
            if provider not in SUPPORTED_TTS_PROVIDERS:
                raise RuntimeError(f"Unsupported podcast TTS provider: {provider}")
            for index, segment in enumerate(segments, start=1):
                preferred_voice = (
                    prefs.host_a_voice if segment.speaker == "HOST_A" else prefs.host_b_voice
                )
                if provider == "openai":
                    fallback = "alloy" if segment.speaker == "HOST_A" else "echo"
                    voice = self._ensure_supported_voice(preferred_voice, fallback)
                else:
                    fallback = (
                        ELEVENLABS_DEFAULT_HOST_A_VOICE
                        if segment.speaker == "HOST_A"
                        else ELEVENLABS_DEFAULT_HOST_B_VOICE
                    )
                    voice = preferred_voice.strip() or fallback

                audio_bytes = await self._synthesize_segment_with_retry(
                    text=segment.text,
                    voice=voice,
                    provider=provider,
                    prefs=prefs,
                )
                if not audio_bytes:
                    logger.warning("Skipping TTS segment after retries: %s", segment.speaker)
                    continue
                path = Path(tmpdir) / f"segment_{index:04d}.mp3"
                path.write_bytes(audio_bytes)
                segment_paths.append(path)
                synthesized_chars += len(segment.text)

            if not segment_paths:
                raise RuntimeError("TTS failed for all segments")

            self._stitch_segments(segment_paths, final_path)

        audio_size = final_path.stat().st_size
        duration = self._probe_audio_duration_seconds(final_path)
        logger.info(
            "Podcast audio generation complete",
            extra={
                "episode_id": str(episode_id),
                "synthesized_segment_count": len(segment_paths),
                "audio_size_bytes": audio_size,
                "duration_seconds": duration,
                "synthesized_chars": synthesized_chars,
            },
        )
        return AudioGenerationResult(
            audio_path=str(final_path),
            audio_size_bytes=audio_size,
            duration_seconds=duration,
            synthesized_chars=synthesized_chars,
        )

    async def _synthesize_segment_with_retry(
        self,
        *,
        text: str,
        voice: str,
        provider: str,
        prefs: PodcastPreferences,
    ) -> bytes:
        """Generate one TTS segment with bounded retries."""
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                return await self._synthesize_segment(
                    text=text,
                    voice=voice,
                    provider=provider,
                    prefs=prefs,
                )
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "%s TTS segment failed (%s/3): %s",
                    provider,
                    attempt + 1,
                    exc,
                )
                if attempt < 2:
                    await asyncio.sleep(0.5 * (attempt + 1))
        logger.error("%s TTS failed after retries: %s", provider, last_error)
        return b""

    async def _synthesize_segment(
        self,
        *,
        text: str,
        voice: str,
        provider: str,
        prefs: PodcastPreferences,
    ) -> bytes:
        """Call selected TTS provider API."""
        if provider == "openai":
            return await self._synthesize_segment_openai(text=text, voice=voice, prefs=prefs)
        if provider == "elevenlabs":
            return await self._synthesize_segment_elevenlabs(text=text, voice=voice, prefs=prefs)
        raise RuntimeError(f"Unsupported podcast TTS provider: {provider}")

    async def _synthesize_segment_openai(
        self,
        *,
        text: str,
        voice: str,
        prefs: PodcastPreferences,
    ) -> bytes:
        """Call OpenAI audio speech API."""
        api_key = (prefs.openai_api_key or "").strip() or self.settings.openai_api_key.strip()
        if not api_key:
            raise RuntimeError("OpenAI API key is required for OpenAI podcast TTS")

        endpoint = "https://api.openai.com/v1/audio/speech"
        payload: dict[str, Any] = {
            "model": (prefs.openai_tts_model or "tts-1").strip() or "tts-1",
            "voice": voice,
            "input": text,
            "response_format": "mp3",
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        timeout = httpx.Timeout(120.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(endpoint, json=payload, headers=headers)
            if response.status_code >= 400:
                raise RuntimeError(
                    f"OpenAI TTS error {response.status_code}: {response.text[:200]}"
                )
            return response.content

    async def _synthesize_segment_elevenlabs(
        self,
        *,
        text: str,
        voice: str,
        prefs: PodcastPreferences,
    ) -> bytes:
        """Call ElevenLabs text-to-speech API."""
        api_key = (prefs.elevenlabs_api_key or "").strip()
        if not api_key:
            raise RuntimeError("ElevenLabs API key is required for ElevenLabs podcast TTS")

        model_id = (prefs.elevenlabs_model_id or "eleven_turbo_v2_5").strip()
        output_format = (
            (prefs.elevenlabs_output_format or "mp3_44100_128").strip()
            or "mp3_44100_128"
        )
        endpoint = f"https://api.elevenlabs.io/v1/text-to-speech/{voice}"
        payload: dict[str, Any] = {
            "text": text,
            "model_id": model_id,
        }
        headers = {
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        timeout = httpx.Timeout(120.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                endpoint,
                params={"output_format": output_format},
                json=payload,
                headers=headers,
            )
            if response.status_code >= 400:
                raise RuntimeError(
                    f"ElevenLabs TTS error {response.status_code}: {response.text[:200]}"
                )
            return response.content

    def _stitch_segments(self, segment_paths: list[Path], output_path: Path) -> None:
        """Stitch MP3 segments with short silence padding using ffmpeg."""
        if len(segment_paths) == 1:
            shutil.copyfile(segment_paths[0], output_path)
            return

        with tempfile.TemporaryDirectory(prefix="podcast_stitch_") as tmpdir:
            tmp_path = Path(tmpdir)
            silence_path = tmp_path / "silence.mp3"
            concat_list_path = tmp_path / "concat.txt"

            silence_cmd = [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=24000:cl=mono",
                "-t",
                "0.3",
                str(silence_path),
            ]
            self._run_subprocess(silence_cmd, "failed to generate silence padding")

            concat_lines: list[str] = []
            for index, segment_path in enumerate(segment_paths):
                concat_lines.append(f"file '{self._ffmpeg_quote(segment_path)}'")
                if index < len(segment_paths) - 1:
                    concat_lines.append(f"file '{self._ffmpeg_quote(silence_path)}'")
            concat_list_path.write_text("\n".join(concat_lines), encoding="utf-8")

            stitch_cmd = [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_list_path),
                "-c:a",
                "libmp3lame",
                "-b:a",
                "96k",
                str(output_path),
            ]
            self._run_subprocess(stitch_cmd, "failed to stitch podcast audio")

    @staticmethod
    def _ffmpeg_quote(path: Path) -> str:
        """Escape a file path for ffmpeg concat list syntax."""
        return str(path).replace("'", "'\\''")

    @staticmethod
    def _run_subprocess(cmd: list[str], error_prefix: str) -> None:
        """Run subprocess command and raise a concise RuntimeError on failure."""
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            raise RuntimeError(f"{error_prefix}: {stderr[:300]}")

    @staticmethod
    def _probe_audio_duration_seconds(path: Path) -> int | None:
        """Get MP3 duration in whole seconds via ffprobe."""
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return None
        try:
            return max(0, int(float((result.stdout or "").strip())))
        except ValueError:
            return None

    @staticmethod
    def _estimate_generation_cost_cents(*, script_chars: int, tts_chars: int) -> int:
        """Estimate generation cost in cents (LLM baseline + OpenAI TTS character pricing)."""
        if script_chars <= 0 and tts_chars <= 0:
            return 0
        script_cost = 20  # Approximate Sonnet/GPT script cost baseline from PRD.
        tts_cost = int(round((tts_chars / 1000.0) * 1.5))  # ~$0.015 / 1k chars.
        return max(1, script_cost + max(0, tts_cost))


podcast_service = PodcastDigestService()
