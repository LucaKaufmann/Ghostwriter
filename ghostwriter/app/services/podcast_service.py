"""Podcast digest generation service."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import secrets
import shutil
import tempfile
from concurrent.futures import Future
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import exists
from sqlmodel import Session, select

from app.core.config import Settings, get_settings
from app.core.database import engine
from app.models.article_feedback import ArticleFeedback, ArticleFeedbackUpsert
from app.models.client_config import ClientConfig
from app.models.digest import Digest, DigestArticle
from app.models.feed import Feed
from app.models.podcast_episode import PodcastEpisode
from app.models.podcast_preferences import PodcastPreferences, PodcastPreferencesUpdate
from app.models.user import User
from app.services.llm_service import LLMService

logger = logging.getLogger(__name__)

SCRIPT_STATUSES = {"pending", "generating_script", "generating_audio", "ready", "failed"}
RUNNING_STATUSES = {"generating_script", "generating_audio"}
ONE_OFF_SYNTHETIC_FEED_URL = "synthetic://one-off"
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
ELEVENLABS_DEFAULT_HOST_A_VOICE = "iP95p4xoKVk53GoZ742B"
ELEVENLABS_DEFAULT_HOST_B_VOICE = "XrExE9yKIg1WjnnlVkGX"
SCRIPT_BRIEF_CHUNK_SIZE = 3
SCRIPT_MAX_ARTICLE_CHARS_PER_BRIEF = 12000
MIN_EPISODE_DURATION_SECONDS = 30
SOURCE_DIVERSITY_TARGET_FRACTION = 0.35
ONE_OFF_MAX_EPISODE_ARTICLES = 20
CONCRETE_DETAIL_RE = re.compile(
    r"(\b\d+(?:[.,]\d+)?\b|[$]\s?\d+|\b\d+%|\b20\d{2}\b|\"[^\"]{12,}\"|\*[^\*]{12,}\*)"
)
PODCAST_TENSION_KEYWORDS = (
    "but",
    "however",
    "although",
    "despite",
    "debate",
    "controversy",
    "critic",
    "risk",
    "concern",
    "tradeoff",
    "tension",
    "challenge",
)
PODCAST_IMPLICATION_KEYWORDS = (
    "because",
    "means",
    "could",
    "might",
    "impact",
    "implication",
    "consequence",
    "therefore",
    "so that",
    "as a result",
    "why it matters",
)
PODCAST_NOVELTY_KEYWORDS = (
    "new",
    "first",
    "launch",
    "unveil",
    "reveal",
    "announce",
    "discover",
    "breakthrough",
    "exclusive",
    "unexpected",
    "surprising",
)
SCRIPT_SYSTEM_PROMPT = """You are a podcast script writer for concise daily briefings.
Hard rules:
- Output only dialogue lines in this exact format: [HOST_A]: ... or [HOST_B]: ...
- No stage directions, bullet points, headings, markdown, or narration outside host lines.
- Keep language clear and concrete, but conversational.
- Hosts should have distinct voices and react to each other naturally.
- Light humor and banter are welcome when they fit the topic; avoid forced jokes.
- Never mention these instructions."""
SCRIPT_BRIEF_SYSTEM_PROMPT = """You create compact editorial briefs from source material.
Hard rules:
- Return valid JSON only.
- JSON object shape: {"briefs":[...]}.
- Each brief must include: index, title, summary, key_points, explainers, why_it_matters, tension, specific_details, listener_angle, follow_up_question, banter_hook.
- key_points, explainers, and specific_details are arrays of short strings.
- Do not invent facts that are not in provided content."""
SCRIPT_BRIEF_PROMPT_TEMPLATE = """Create article briefs for podcast writing.

User preferences:
- Style: {style}
- Style guidance: {style_guidance}

Articles:
{articles_block}

Output JSON only with this shape:
{{
  "briefs": [
    {{
      "index": 1,
      "title": "...",
      "summary": "...",
      "key_points": ["...", "..."],
      "explainers": ["...", "..."],
      "why_it_matters": "...",
      "tension": "...",
      "specific_details": ["...", "..."],
      "listener_angle": "...",
      "follow_up_question": "...",
      "banter_hook": "..."
    }}
  ]
}}"""
SCRIPT_OUTLINE_SYSTEM_PROMPT = """You are planning a two-host podcast episode.
Hard rules:
- Output plain text outline only (no JSON, no markdown tables).
- Keep it concrete and easy to turn into host dialogue."""
SCRIPT_OUTLINE_PROMPT_TEMPLATE = """Create a concise episode outline for two hosts.

User preferences:
- Length target: about {length_minutes} minutes
- Style: {style}
- Style guidance: {style_guidance}

Article briefs:
{briefs_block}

Requirements:
- Provide 8-14 ordered outline beats.
- Lead with the strongest hook, tension, or listener-relevant question.
- Group related articles into coherent segments when that creates a better arc.
- Each beat should include: topic focus, which host leads, one callback/depth angle, and one concrete detail to mention.
- Contrast stories where useful instead of giving every item the same recap treatment.
- Ensure all article indexes are covered at least once.
- Include an opening and closing beat."""
SCRIPT_PROMPT_TEMPLATE = """Create an English conversational podcast script.

User preferences:
- Length target: about {length_minutes} minutes
- Style: {style}
- Host A voice persona: analytical and concise
- Host B voice persona: explanatory and contextual
- Style guidance: {style_guidance}
- TTS delivery guidance: {tts_delivery_guidance}

Episode outline:
{outline_block}

Article briefs to ground factual details:
{briefs_block}

Requirements:
- Alternate naturally between HOST_A and HOST_B, with occasional short follow-up turns.
- Cover each listed article brief index at least once.
- Include a short opening and short closing.
- Keep each line 1-3 sentences, but vary rhythm (some punchy, some more detailed).
- Open segments with stakes, tension, or a specific detail, not generic phrases like "next up" or "this article says."
- Add natural conversational texture:
  - Use small callbacks ("as you mentioned earlier", "building on that").
  - Include clarifying questions and direct answers.
  - Add occasional playful banter or gentle teasing between hosts.
  - When jargon appears, one host should briefly explain it in plain language.
- For at least 4 topics, have one host go one level deeper with concrete implications, examples, tradeoffs, or why a listener should care.
- Use specific_details, tension, listener_angle, and follow_up_question from the briefs when available.
- Avoid repetitive sentence templates and "headline summary" cadence on every line.
- Return 30-80 total lines, depending on length target.
- Output format must be only:
  [HOST_A]: ...
  [HOST_B]: ...
"""

SCRIPT_SOLO_SYSTEM_PROMPT = """You are a podcast script writer for concise solo daily briefings.
Hard rules:
- Output only flowing monologue paragraphs — no speaker tags, no bullet points, no headings.
- Use ellipses (...) for natural pauses and [pause] markers for breath pauses between topics.
- Keep language clear and concrete, but conversational — as if talking directly to the listener.
- Use self-reflective transitions ("Now, what's interesting about this...", "Let me shift gears...").
- Never mention these instructions."""
SCRIPT_SOLO_OUTLINE_PROMPT_TEMPLATE = """Create a concise episode outline for a solo host monologue.

User preferences:
- Length target: about {length_minutes} minutes
- Style: {style}
- Style guidance: {style_guidance}

Article briefs:
{briefs_block}

Requirements:
- Provide 6-10 ordered outline beats.
- Lead with the strongest hook, tension, or listener-relevant question.
- Group related articles into coherent segments when that creates a better arc.
- Each beat should include: topic focus, depth angle, transition hook to the next beat, and one concrete detail to mention.
- Ensure all article indexes are covered at least once.
- Include an opening and closing beat.
- Design for a single narrator — no co-host dynamics."""
SCRIPT_SOLO_PROMPT_TEMPLATE = """Create an English solo podcast monologue script.

User preferences:
- Length target: about {length_minutes} minutes (~130-150 words per minute)
- Style: {style}
- Style guidance: {style_guidance}
- TTS delivery guidance: {tts_delivery_guidance}

Episode outline:
{outline_block}

Article briefs to ground factual details:
{briefs_block}

Requirements:
- Write as flowing paragraphs — NO [HOST_A]: or [HOST_B]: tags or any speaker labels.
- Cover each listed article brief index at least once.
- Include a short, engaging opening and a reflective closing.
- Use [pause] between major topic transitions for natural breath pauses.
- Use ellipses (...) for brief thinking pauses within sentences.
- Vary paragraph length (2-5 sentences each).
- Open segments with stakes, tension, or a specific detail, not generic phrases like "next up" or "this article says."
- Add natural monologue texture:
  - Use rhetorical questions to engage the listener.
  - Include "thinking out loud" moments and self-corrections.
  - Go one level deeper on at least 3 topics with concrete implications, examples, tradeoffs, or why a listener should care.
  - Use transitions that feel organic ("Speaking of which...", "Now here's where it gets interesting...").
- Use specific_details, tension, listener_angle, and follow_up_question from the briefs when available.
- Aim for 6-15 paragraphs depending on length target.
- Do not use any [HOST_A] or [HOST_B] tags — this is a solo show.
"""

_podcast_tasks: set[asyncio.Task[None] | Future[None]] = set()


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


@dataclass(frozen=True)
class PodcastGenerationPreferences:
    """Session-independent preferences used during episode generation."""

    topic_weights: dict[str, float]
    boost_sources: list[str]
    boost_keywords: list[str]
    filter_keywords: list[str]
    preferred_length_minutes: int
    script_model: str | None
    script_timeout_seconds: int
    style: str
    tts_provider: str
    openai_tts_model: str
    openai_api_key: str | None
    elevenlabs_model_id: str
    elevenlabs_api_key: str | None
    elevenlabs_output_format: str
    host_a_voice: str
    host_b_voice: str
    host_count: int


class PodcastDigestService:
    """Service that manages podcast preferences, feedback, and episode generation."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.llm_service = LLMService(self.settings)
        self._main_loop: asyncio.AbstractEventLoop | None = None

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Set the main application event loop for cross-thread task scheduling."""
        self._main_loop = loop

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

    @staticmethod
    def _sanitize_public_base_url(value: str | None) -> str | None:
        """Normalize optional public feed URL; blank values become None."""
        if value is None:
            return None
        cleaned = value.strip().rstrip("/")
        if not cleaned:
            return None
        parsed = urlparse(cleaned)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("podcast_feed_base_url must be an absolute http(s) URL")
        return cleaned

    def _resolve_user_id(self, session: Session) -> UUID | None:
        """Resolve the current singleton user ID if a user exists."""
        user = session.exec(select(User).order_by(User.created_at.asc())).first()
        return user.id if user else None

    def resolve_user_id(self, session: Session) -> UUID | None:
        """Public wrapper for singleton user resolution."""
        return self._resolve_user_id(session)

    def _assign_legacy_preferences_owner(
        self,
        session: Session,
        now: datetime,
    ) -> None:
        """Attach legacy NULL-owner preferences to the singleton owner."""
        owner_id = self._resolve_user_id(session)
        if owner_id is None:
            return

        legacy_rows = session.exec(
            select(PodcastPreferences)
            .where(PodcastPreferences.user_id.is_(None))
            .order_by(PodcastPreferences.created_at.asc())
        ).all()
        if not legacy_rows:
            return

        for prefs in legacy_rows:
            prefs.user_id = owner_id
            prefs.updated_at = now
            if not prefs.podcast_feed_token:
                prefs.podcast_feed_token = self._generate_feed_token()
            session.add(prefs)
        session.commit()

    def get_or_create_preferences(
        self,
        session: Session,
        user_id: UUID | None = None,
    ) -> PodcastPreferences:
        """Get podcast preferences, creating a singleton row when missing."""
        now = datetime.utcnow()

        if user_id is not None:
            self._assign_legacy_preferences_owner(session, now)
            prefs = session.exec(
                select(PodcastPreferences)
                .where(PodcastPreferences.user_id == user_id)
                .order_by(PodcastPreferences.created_at.asc())
            ).first()
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
        else:
            prefs = session.exec(
                select(PodcastPreferences).order_by(PodcastPreferences.created_at.asc())
            ).first()

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
        if update.script_model is not None:
            cleaned_model = update.script_model.strip()
            prefs.script_model = cleaned_model or None
        if update.script_timeout_seconds is not None:
            prefs.script_timeout_seconds = update.script_timeout_seconds
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
        if update.host_count is not None:
            prefs.host_count = max(1, min(2, int(update.host_count)))
        if update.podcast_feed_enabled is not None:
            prefs.podcast_feed_enabled = update.podcast_feed_enabled
        if update.podcast_feed_title is not None:
            prefs.podcast_feed_title = update.podcast_feed_title.strip() or "My Ghostwriter Digest"
        if update.podcast_feed_description is not None:
            cleaned = update.podcast_feed_description.strip()
            prefs.podcast_feed_description = (
                cleaned if cleaned else "AI-generated audio digest of your RSS feeds"
            )
        if update.podcast_feed_base_url is not None:
            prefs.podcast_feed_base_url = self._sanitize_public_base_url(
                update.podcast_feed_base_url
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
                "script_model": prefs.script_model,
                "script_timeout_seconds": prefs.script_timeout_seconds,
                "style": prefs.style,
                "tts_provider": prefs.tts_provider,
                "openai_tts_model": prefs.openai_tts_model,
                "elevenlabs_model_id": prefs.elevenlabs_model_id,
                "elevenlabs_output_format": prefs.elevenlabs_output_format,
                "podcast_feed_enabled": prefs.podcast_feed_enabled,
                "podcast_feed_base_url": prefs.podcast_feed_base_url,
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
        trigger: str = "manual",
    ) -> PodcastEpisode:
        """Queue podcast generation for a single digest (manual trigger)."""
        digest = session.get(Digest, digest_id)
        if digest is None:
            raise ValueError("Digest not found")
        if digest.status != "completed":
            raise ValueError("Digest must be completed before podcast generation")

        digest_id_str = str(digest_id)
        now = datetime.utcnow()

        # Check for existing episode that contains this digest
        all_episodes = session.exec(
            select(PodcastEpisode).order_by(PodcastEpisode.created_at.desc())
        ).all()
        episode = next(
            (ep for ep in all_episodes if digest_id_str in (ep.digest_ids or [])),
            None,
        )

        if episode is not None:
            if episode.trigger == "one_off" and trigger != "one_off":
                trigger = episode.trigger
            if episode.trigger != trigger:
                episode.trigger = trigger
                episode.updated_at = now
                session.add(episode)
                session.commit()
                session.refresh(episode)
            if episode.status in RUNNING_STATUSES:
                logger.info(
                    "Podcast generation already running for digest",
                    extra={"digest_id": digest_id_str, "episode_id": str(episode.id), "status": episode.status},
                )
                return episode
            if episode.status == "ready" and not force:
                logger.info(
                    "Podcast already ready for digest; skipping queue",
                    extra={"digest_id": digest_id_str, "episode_id": str(episode.id)},
                )
                return episode
            if episode.status in {"pending", "failed"} and not force:
                if episode.status == "pending":
                    logger.info(
                        "Podcast generation already pending; ensuring worker task is scheduled",
                        extra={"digest_id": digest_id_str, "episode_id": str(episode.id)},
                    )
                else:
                    self._reset_episode(episode, now)
                    session.add(episode)
                    session.commit()
                    session.refresh(episode)
                    logger.info(
                        "Podcast failed episode re-queued",
                        extra={"digest_id": digest_id_str, "episode_id": str(episode.id)},
                    )
                self._schedule_episode_task(episode.id)
                return episode

            if force:
                self._reset_episode(episode, now)
                session.add(episode)
                session.commit()
                session.refresh(episode)
                logger.info(
                    "Podcast episode reset for forced regeneration",
                    extra={"digest_id": digest_id_str, "episode_id": str(episode.id)},
                )
                self._schedule_episode_task(episode.id)
                return episode

            return episode

        episode = PodcastEpisode(
            digest_ids=[digest_id_str],
            trigger=trigger,
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
            extra={"digest_id": digest_id_str, "episode_id": str(episode.id), "force": force},
        )
        self._schedule_episode_task(episode.id)
        return episode

    @staticmethod
    def exclude_one_off_digests(statement):
        """Exclude digests backed by one-off synthetic-feed articles."""
        one_off_digest_exists = (
            exists()
            .where(DigestArticle.digest_id == Digest.id)
            .where(DigestArticle.feed_id == Feed.id)
            .where(Feed.url == ONE_OFF_SYNTHETIC_FEED_URL)
        )
        return statement.where(~one_off_digest_exists)

    @staticmethod
    def is_one_off_digest(session: Session, digest_id: UUID) -> bool:
        """Return true when a digest contains one-off synthetic-feed articles."""
        statement = (
            select(DigestArticle.id)
            .join(Feed, DigestArticle.feed_id == Feed.id)
            .where(DigestArticle.digest_id == digest_id)
            .where(Feed.url == ONE_OFF_SYNTHETIC_FEED_URL)
            .limit(1)
        )
        return session.exec(statement).first() is not None

    def queue_multi_digest_episode(
        self,
        session: Session,
        digest_ids: list[UUID],
        *,
        user_id: UUID | None = None,
    ) -> PodcastEpisode:
        """Create a scheduled podcast episode from multiple digests."""
        now = datetime.utcnow()
        episode = PodcastEpisode(
            digest_ids=[str(d) for d in digest_ids],
            trigger="scheduled",
            user_id=user_id,
            status="pending",
            created_at=now,
            updated_at=now,
        )
        session.add(episode)
        session.commit()
        session.refresh(episode)
        logger.info(
            "Multi-digest podcast episode queued",
            extra={
                "episode_id": str(episode.id),
                "digest_count": len(digest_ids),
                "digest_ids": [str(d) for d in digest_ids],
            },
        )
        self._schedule_episode_task(episode.id)
        return episode

    @staticmethod
    def _reset_episode(episode: PodcastEpisode, now: datetime) -> None:
        """Reset episode fields for re-generation."""
        if episode.audio_path and os.path.exists(episode.audio_path):
            try:
                os.remove(episode.audio_path)
            except OSError:
                logger.warning("Failed deleting old podcast audio before retry", exc_info=True)
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

    def generate_scheduled_episode(self) -> UUID | None:
        """Generate a podcast episode from recent digests based on schedule config.

        Called by the independent podcast APScheduler job.
        Returns the episode ID if queued, or None if skipped.
        """
        with Session(engine) as session:
            user_id = self._resolve_user_id(session)
            prefs = self.get_or_create_preferences(session, user_id=user_id)
            if not prefs.enabled or prefs.schedule == "manual":
                logger.debug(
                    "Scheduled podcast generation skipped: disabled or manual",
                    extra={"enabled": prefs.enabled, "schedule": prefs.schedule},
                )
                return None

            tz = self._resolve_timezone(session)
            now_local = datetime.now(tz)

            # Determine the time window for collecting digests
            if prefs.schedule == "daily":
                start_local = datetime.combine(now_local.date(), time.min, tzinfo=tz)
                end_local = start_local + timedelta(days=1)
            elif prefs.schedule == "weekly":
                days_back = now_local.weekday()  # Monday=0
                week_start_date = now_local.date() - timedelta(days=days_back)
                start_local = datetime.combine(week_start_date, time.min, tzinfo=tz)
                end_local = start_local + timedelta(days=7)
            else:
                return None

            start_utc = start_local.astimezone(UTC).replace(tzinfo=None)
            end_utc = end_local.astimezone(UTC).replace(tzinfo=None)

            # Deduplicate: skip if a non-failed episode already exists for this window
            existing_statement = select(PodcastEpisode).where(
                PodcastEpisode.created_at >= start_utc,
                PodcastEpisode.created_at < end_utc,
                PodcastEpisode.status != "failed",
                PodcastEpisode.trigger == "scheduled",
            )
            if session.exec(existing_statement).first() is not None:
                logger.info(
                    "Scheduled podcast generation skipped: episode already exists for window",
                    extra={"window_start": start_utc.isoformat(), "window_end": end_utc.isoformat()},
                )
                return None

            # Find completed digests in the time window
            statement = self.exclude_one_off_digests(
                select(Digest).where(
                    Digest.status == "completed",
                    Digest.created_at >= start_utc,
                    Digest.created_at < end_utc,
                )
            )
            digests = session.exec(statement).all()

            if not digests:
                logger.info(
                    "Scheduled podcast generation skipped: no completed digests in window",
                    extra={"window_start": start_utc.isoformat(), "window_end": end_utc.isoformat()},
                )
                return None

            digest_ids = [d.id for d in digests]
            logger.info(
                "Scheduled podcast generation starting",
                extra={
                    "schedule": prefs.schedule,
                    "digest_count": len(digest_ids),
                    "digest_ids": [str(d) for d in digest_ids],
                    "window_start": start_utc.isoformat(),
                    "window_end": end_utc.isoformat(),
                },
            )

            episode = self.queue_multi_digest_episode(
                session,
                digest_ids,
                user_id=prefs.user_id,
            )
            return episode.id

    def generate_episode_for_schedule(self, schedule_id: UUID) -> UUID | None:
        """Generate a podcast episode for a specific podcast schedule.

        Finds completed digests created after the schedule's last_run_at
        (or all time if never run). Returns the episode ID if queued, or
        None if no eligible digests exist.
        """
        from app.models.podcast_schedule import PodcastSchedule

        with Session(engine) as session:
            schedule = session.get(PodcastSchedule, schedule_id)
            if schedule is None:
                logger.warning(
                    "Podcast schedule not found: %s", schedule_id,
                )
                return None

            if not schedule.enabled:
                logger.debug(
                    "Podcast schedule %s is disabled, skipping", schedule_id,
                )
                return None

            # Find digests completed after the schedule's last run
            stmt = self.exclude_one_off_digests(
                select(Digest).where(Digest.status == "completed")
            )
            if schedule.last_run_at is not None:
                stmt = stmt.where(Digest.created_at > schedule.last_run_at)
            stmt = stmt.order_by(Digest.created_at.asc())

            digests = session.exec(stmt).all()

            if not digests:
                logger.info(
                    "Podcast schedule %s: no new digests since last run",
                    schedule.name or str(schedule_id),
                    extra={"schedule_id": str(schedule_id), "last_run_at": str(schedule.last_run_at)},
                )
                return None

            digest_ids = [d.id for d in digests]
            logger.info(
                "Podcast schedule '%s' generating episode from %d digest(s)",
                schedule.name or str(schedule_id),
                len(digest_ids),
                extra={
                    "schedule_id": str(schedule_id),
                    "digest_count": len(digest_ids),
                    "digest_ids": [str(d) for d in digest_ids],
                },
            )

            user_id = schedule.user_id or self._resolve_user_id(session)
            episode = self.queue_multi_digest_episode(
                session,
                digest_ids,
                user_id=user_id,
            )

            # Update the schedule's last run tracking
            now = datetime.utcnow()
            schedule.last_run_at = now
            schedule.last_episode_id = episode.id
            schedule.updated_at = now
            session.add(schedule)
            session.commit()

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

    def _schedule_episode_task(self, episode_id: UUID) -> None:
        """Schedule one podcast generation background task."""
        logger.info("Scheduling podcast generation task", extra={"episode_id": str(episode_id)})
        coroutine = self._run_episode_generation(episode_id)
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        if running_loop is not None:
            task = running_loop.create_task(
                coroutine,
                name=f"podcast_episode_{episode_id}",
            )
            _podcast_tasks.add(task)
            task.add_done_callback(_podcast_tasks.discard)
            return

        if self._main_loop is None or self._main_loop.is_closed():
            raise RuntimeError("Podcast generation scheduler loop unavailable")

        future = asyncio.run_coroutine_threadsafe(coroutine, self._main_loop)
        _podcast_tasks.add(future)
        future.add_done_callback(_podcast_tasks.discard)

    def _snapshot_generation_preferences(
        self,
        prefs: PodcastPreferences,
    ) -> PodcastGenerationPreferences:
        """Create a detached-safe copy of generation-related preferences."""
        return PodcastGenerationPreferences(
            topic_weights=dict(prefs.topic_weights or {}),
            boost_sources=list(prefs.boost_sources or []),
            boost_keywords=list(prefs.boost_keywords or []),
            filter_keywords=list(prefs.filter_keywords or []),
            preferred_length_minutes=int(prefs.preferred_length_minutes),
            script_model=(prefs.script_model or "").strip() or None,
            script_timeout_seconds=max(
                30, min(600, int(prefs.script_timeout_seconds or 60))
            ),
            style=str(prefs.style),
            tts_provider=str(prefs.tts_provider),
            openai_tts_model=str(prefs.openai_tts_model or "tts-1"),
            openai_api_key=prefs.openai_api_key,
            elevenlabs_model_id=str(prefs.elevenlabs_model_id or "eleven_turbo_v2_5"),
            elevenlabs_api_key=prefs.elevenlabs_api_key,
            elevenlabs_output_format=str(prefs.elevenlabs_output_format or "mp3_44100_128"),
            host_a_voice=str(prefs.host_a_voice or "alloy"),
            host_b_voice=str(prefs.host_b_voice or "echo"),
            host_count=int(prefs.host_count or 2),
        )

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
                extra={"episode_id": str(episode_id), "digest_ids": episode.digest_ids},
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

                # Resolve digest UUIDs from the episode
                episode_digest_ids: list[UUID] = []
                for raw in (episode.digest_ids or []):
                    try:
                        episode_digest_ids.append(UUID(raw))
                    except ValueError:
                        continue
                if not episode_digest_ids:
                    raise RuntimeError("No digest IDs on episode")

                # Verify at least one digest exists
                first_digest = session.get(Digest, episode_digest_ids[0])
                if first_digest is None:
                    raise RuntimeError("Primary digest not found for episode")

                user_id = episode.user_id or self._resolve_user_id(session)
                prefs = self.get_or_create_preferences(session, user_id=user_id)
                runtime_prefs = self._snapshot_generation_preferences(prefs)
                selected_articles = self.select_articles_for_episode(
                    session,
                    digest_ids=episode_digest_ids,
                    prefs=runtime_prefs,
                    user_id=user_id,
                    trigger=episode.trigger,
                )
                logger.info(
                    "Podcast article selection complete",
                    extra={
                        "episode_id": str(episode_id),
                        "digest_ids": [str(d) for d in episode_digest_ids],
                        "selected_article_count": len(selected_articles),
                    },
                )

                if not selected_articles:
                    raise RuntimeError("No articles passed podcast scoring")

                is_solo = runtime_prefs.host_count == 1
                if is_solo:
                    script = await self._generate_solo_script(
                        selected_articles,
                        runtime_prefs,
                        episode_id=episode_id,
                        digest_id=episode_digest_ids[0],
                    )
                    solo_text = self.parse_solo_script(script)
                    logger.info(
                        "Podcast solo script generation complete",
                        extra={
                            "episode_id": str(episode_id),
                            "digest_ids": [str(d) for d in episode_digest_ids],
                            "script_chars": len(script),
                        },
                    )
                else:
                    script = await self.generate_script(
                        selected_articles,
                        runtime_prefs,
                        episode_id=episode_id,
                        digest_id=episode_digest_ids[0],
                    )
                    segments = self.parse_script_segments(script)
                    logger.info(
                        "Podcast script generation complete",
                        extra={
                            "episode_id": str(episode_id),
                            "digest_ids": [str(d) for d in episode_digest_ids],
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
                logger.info(
                    "Podcast generation moved to audio synthesis",
                    extra={
                        "episode_id": str(episode_id),
                        "digest_ids": [str(d) for d in episode_digest_ids],
                        "status": episode.status,
                    },
                )

            if is_solo:
                audio_result = await self.generate_solo_audio(
                    episode_id, solo_text, runtime_prefs
                )
            else:
                audio_result = await self.generate_audio(episode_id, segments, runtime_prefs)

            if (
                audio_result.duration_seconds is not None
                and audio_result.duration_seconds < MIN_EPISODE_DURATION_SECONDS
            ):
                # Clean up the too-short audio file
                audio_path = Path(audio_result.audio_path)
                if audio_path.exists():
                    audio_path.unlink()
                raise RuntimeError(
                    f"Generated audio is only {audio_result.duration_seconds}s, "
                    f"below the {MIN_EPISODE_DURATION_SECONDS}s minimum. "
                    f"Most TTS segments likely failed."
                )

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
                        "digest_ids": episode.digest_ids,
                        "audio_size_bytes": audio_result.audio_size_bytes,
                        "duration_seconds": audio_result.duration_seconds,
                        "article_count": episode.article_count,
                        "generation_cost_cents": episode.generation_cost_cents,
                    },
                )
        except Exception as exc:
            logger.exception(
                "Podcast episode generation failed",
                extra={"episode_id": str(episode_id), "error": str(exc)[:300]},
            )
            with Session(engine) as session:
                episode = session.get(PodcastEpisode, episode_id)
                if episode:
                    episode.status = "failed"
                    episode.error_message = str(exc)[:500]
                    episode.updated_at = datetime.utcnow()
                    session.add(episode)
                    session.commit()
                    logger.info(
                        "Podcast generation marked failed",
                        extra={
                            "episode_id": str(episode_id),
                            "digest_ids": episode.digest_ids,
                            "status": episode.status,
                        },
                    )

    def select_articles_for_episode(
        self,
        session: Session,
        *,
        digest_ids: list[UUID],
        prefs: PodcastGenerationPreferences,
        user_id: UUID | None,
        trigger: str | None = None,
    ) -> list[DigestArticle]:
        """Rank articles from one or more digests and pick top items for script generation."""
        articles = session.exec(
            select(DigestArticle)
            .where(DigestArticle.digest_id.in_(digest_ids))
            .order_by(DigestArticle.sort_order.asc())
        ).all()
        if not articles:
            logger.info(
                "Podcast article selection found no digest articles",
                extra={"digest_ids": [str(d) for d in digest_ids]},
            )
            return []

        if trigger == "one_off":
            selected = [
                article
                for article in articles
                if re.sub(r"\s+", " ", article.content or "").strip()
            ][:ONE_OFF_MAX_EPISODE_ARTICLES]
            logger.info(
                "One-off podcast article selection preserved source order",
                extra={
                    "digest_ids": [str(d) for d in digest_ids],
                    "total_article_count": len(articles),
                    "selected_count": len(selected),
                },
            )
            return selected

        # Deduplicate articles by URL across digests
        seen_urls: set[str] = set()
        unique_articles: list[DigestArticle] = []
        for article in articles:
            url_key = (article.url or "").strip().lower()
            if url_key and url_key in seen_urls:
                continue
            if url_key:
                seen_urls.add(url_key)
            unique_articles.append(article)

        feedback_profile = self._build_feedback_profile(session, user_id=user_id)
        scored: list[tuple[float, int, DigestArticle]] = []
        for article in unique_articles:
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
                extra={"digest_ids": [str(d) for d in digest_ids], "digest_article_count": len(unique_articles)},
            )
            return []

        scored.sort(key=lambda row: (-row[0], row[1]))
        target_count = max(8, min(20, prefs.preferred_length_minutes + 4))
        selected = self._select_balanced_articles(scored, target_count)
        logger.info(
            "Podcast article selection summary",
            extra={
                "digest_ids": [str(d) for d in digest_ids],
                "total_article_count": len(articles),
                "unique_article_count": len(unique_articles),
                "scored_article_count": len(scored),
                "target_count": target_count,
                "selected_count": len(selected),
            },
        )
        return selected

    @staticmethod
    def _select_balanced_articles(
        scored_articles: list[tuple[float, int, DigestArticle]],
        target_count: int,
    ) -> list[DigestArticle]:
        """Pick top articles while avoiding one source dominating the episode."""
        if target_count <= 0:
            return []
        source_cap = max(2, int(target_count * SOURCE_DIVERSITY_TARGET_FRACTION))
        selected: list[DigestArticle] = []
        selected_ids: set[UUID] = set()
        source_counts: dict[str, int] = {}

        for _, _, article in scored_articles:
            source = (article.feed_title or "").strip().lower()
            if source and source_counts.get(source, 0) >= source_cap:
                continue
            selected.append(article)
            selected_ids.add(article.id)
            if source:
                source_counts[source] = source_counts.get(source, 0) + 1
            if len(selected) >= target_count:
                return selected

        for _, _, article in scored_articles:
            if article.id in selected_ids:
                continue
            selected.append(article)
            if len(selected) >= target_count:
                break

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
        prefs: PodcastGenerationPreferences,
        feedback_profile: dict[str, tuple[int, int]],
    ) -> float:
        """Score one article against preferences and past feedback."""
        score = 1.0
        topic = self._infer_topic(article)
        default_topic_weight = 0.5 if prefs.topic_weights else 1.0
        topic_weight = prefs.topic_weights.get(
            topic, prefs.topic_weights.get("general", default_topic_weight)
        )
        score *= max(topic_weight, 0.0)

        source = (article.feed_title or "").strip().lower()
        boosted_sources = {value.lower() for value in prefs.boost_sources}
        if source and source in boosted_sources:
            score *= 1.5

        title_text = (article.title or "").lower()
        text = f"{article.title} {article.content[:2200]}".lower()
        for keyword in prefs.filter_keywords:
            if keyword.lower() in text:
                return 0.0

        for keyword in prefs.boost_keywords:
            normalized_keyword = keyword.lower()
            if normalized_keyword in title_text:
                score *= 1.45
            elif normalized_keyword in text:
                score *= 1.3

        score *= self._content_depth_multiplier(article)
        score *= self._podcast_interest_multiplier(article)

        if article.content_type in {"podcast", "youtube"}:
            score *= 1.08
        if article.ai_failed:
            score *= 0.85

        if source and source in feedback_profile:
            up, down = feedback_profile[source]
            total = up + down
            if total:
                bias = (up - down) / total
                score *= max(0.6, min(1.4, 1.0 + (bias * 0.4)))

        return score

    @staticmethod
    def _content_depth_multiplier(article: DigestArticle) -> float:
        """Favor articles with enough source material for a useful spoken segment."""
        content = re.sub(r"\s+", " ", article.content or "").strip()
        word_count = article.word_count or len(content.split())
        char_count = len(content)
        if word_count < 60 or char_count < 300:
            return 0.45
        if word_count < 150 or char_count < 800:
            return 0.75
        if word_count >= 1800 or char_count >= 9000:
            return 1.22
        if word_count >= 700 or char_count >= 3500:
            return 1.12
        return 1.0

    @staticmethod
    def _podcast_interest_multiplier(article: DigestArticle) -> float:
        """Estimate whether a story has details, tension, and implications for audio."""
        text = re.sub(
            r"\s+",
            " ",
            f"{article.title or ''}. {article.content[:3000] or ''}",
        ).lower()
        signals = 0
        if CONCRETE_DETAIL_RE.search(text):
            signals += 1
        if any(keyword in text for keyword in PODCAST_TENSION_KEYWORDS):
            signals += 1
        if any(keyword in text for keyword in PODCAST_IMPLICATION_KEYWORDS):
            signals += 1
        if any(keyword in text for keyword in PODCAST_NOVELTY_KEYWORDS):
            signals += 1
        if "?" in (article.title or "") or ":" in (article.title or ""):
            signals += 1

        if signals == 0:
            return 0.78
        return min(1.55, 0.9 + (signals * 0.14))

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
        prefs: PodcastGenerationPreferences,
        *,
        episode_id: UUID | None = None,
        digest_id: UUID | None = None,
    ) -> str:
        """Generate and validate podcast script from selected articles."""
        if not articles:
            raise RuntimeError("No articles available for script generation")

        model = (prefs.script_model or "").strip() or self.settings.get_llm_model_string()
        timeout_seconds = max(30, min(600, int(prefs.script_timeout_seconds)))
        style_guidance = self._script_style_guidance(prefs.style)
        tts_delivery_guidance = self._tts_script_delivery_guidance(
            provider=prefs.tts_provider,
            elevenlabs_model_id=prefs.elevenlabs_model_id,
        )
        script_system_prompt = self._script_system_prompt_for_tts(
            provider=prefs.tts_provider,
            elevenlabs_model_id=prefs.elevenlabs_model_id,
        )
        debug_path: Path | None = None
        if episode_id is not None:
            debug_dir = Path(self.settings.logs_dir) / "podcast_script_prompts"
            debug_dir.mkdir(parents=True, exist_ok=True)
            debug_path = debug_dir / f"{episode_id}.json"
            if debug_path.exists():
                debug_path.unlink(missing_ok=True)

        article_inputs: list[dict[str, Any]] = []
        for index, article in enumerate(articles, start=1):
            normalized_content = re.sub(r"\s+", " ", article.content).strip()
            if len(normalized_content) > SCRIPT_MAX_ARTICLE_CHARS_PER_BRIEF:
                normalized_content = (
                    normalized_content[:SCRIPT_MAX_ARTICLE_CHARS_PER_BRIEF].strip()
                    + " [TRUNCATED]"
                )
            article_inputs.append(
                {
                    "index": index,
                    "title": article.title,
                    "source": article.feed_title,
                    "url": article.url,
                    "content": normalized_content,
                }
            )

        briefs = await self._generate_article_briefs(
            article_inputs,
            model=model,
            timeout_seconds=timeout_seconds,
            style=prefs.style,
            style_guidance=style_guidance,
            debug_path=debug_path,
            episode_id=episode_id,
            digest_id=digest_id,
        )
        briefs_block = self._render_briefs_block(briefs)

        outline = await self._generate_script_outline(
            briefs_block=briefs_block,
            model=model,
            timeout_seconds=timeout_seconds,
            style=prefs.style,
            style_guidance=style_guidance,
            length_minutes=prefs.preferred_length_minutes,
            debug_path=debug_path,
            episode_id=episode_id,
            digest_id=digest_id,
        )
        prompt = SCRIPT_PROMPT_TEMPLATE.format(
            length_minutes=prefs.preferred_length_minutes,
            style=prefs.style,
            style_guidance=style_guidance,
            tts_delivery_guidance=tts_delivery_guidance,
            outline_block=outline,
            briefs_block=briefs_block,
        )

        if debug_path is not None:
            self._write_script_prompt_debug(
                debug_path,
                {
                    "stage": "final_script",
                    "episode_id": str(episode_id),
                    "digest_id": str(digest_id) if digest_id else None,
                    "model": model,
                    "style": prefs.style,
                    "length_minutes": prefs.preferred_length_minutes,
                    "article_count": len(articles),
                    "timeout_seconds": timeout_seconds,
                    "generated_at_utc": datetime.utcnow().isoformat() + "Z",
                    "system_prompt": script_system_prompt,
                    "user_prompt": prompt,
                },
            )
            logger.info(
                "Podcast script prompt debug saved",
                extra={"episode_id": str(episode_id), "path": str(debug_path)},
            )
        retries = 2
        for attempt in range(retries + 1):
            logger.info(
                "Generating podcast script attempt",
                extra={
                    "attempt": attempt + 1,
                    "attempts_total": retries + 1,
                    "article_count": len(articles),
                    "model": model,
                    "timeout_seconds": timeout_seconds,
                },
            )
            script, failed = await self.llm_service._run_completion(
                prompt,
                model,
                retries=1,
                system_prompt=script_system_prompt,
                timeout_seconds=timeout_seconds,
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

        logger.warning("Chunked script generation failed; trying direct fallback prompt")
        fallback_prompt = self._build_direct_script_prompt(
            articles=articles,
            length_minutes=prefs.preferred_length_minutes,
            style=prefs.style,
            style_guidance=style_guidance,
            tts_delivery_guidance=tts_delivery_guidance,
        )
        for attempt in range(retries + 1):
            script, failed = await self.llm_service._run_completion(
                fallback_prompt,
                model,
                retries=1,
                system_prompt=script_system_prompt,
                timeout_seconds=timeout_seconds,
            )
            if failed or not script.strip():
                continue
            try:
                self.parse_script_segments(script)
                return script.strip()
            except ValueError:
                await asyncio.sleep(0.5 * (attempt + 1))
        raise RuntimeError("Failed to generate valid podcast script")

    async def _generate_solo_script(
        self,
        articles: list[DigestArticle],
        prefs: PodcastGenerationPreferences,
        *,
        episode_id: UUID | None = None,
        digest_id: UUID | None = None,
    ) -> str:
        """Generate and validate a solo monologue podcast script."""
        if not articles:
            raise RuntimeError("No articles available for script generation")

        model = (prefs.script_model or "").strip() or self.settings.get_llm_model_string()
        timeout_seconds = max(30, min(600, int(prefs.script_timeout_seconds)))
        style_guidance = self._script_style_guidance_solo(prefs.style)
        tts_delivery_guidance = self._tts_script_delivery_guidance(
            provider=prefs.tts_provider,
            elevenlabs_model_id=prefs.elevenlabs_model_id,
        )
        script_system_prompt = self._script_system_prompt_for_tts_solo(
            provider=prefs.tts_provider,
            elevenlabs_model_id=prefs.elevenlabs_model_id,
        )
        debug_path: Path | None = None
        if episode_id is not None:
            debug_dir = Path(self.settings.logs_dir) / "podcast_script_prompts"
            debug_dir.mkdir(parents=True, exist_ok=True)
            debug_path = debug_dir / f"{episode_id}.json"
            if debug_path.exists():
                debug_path.unlink(missing_ok=True)

        article_inputs: list[dict[str, Any]] = []
        for index, article in enumerate(articles, start=1):
            normalized_content = re.sub(r"\s+", " ", article.content).strip()
            if len(normalized_content) > SCRIPT_MAX_ARTICLE_CHARS_PER_BRIEF:
                normalized_content = (
                    normalized_content[:SCRIPT_MAX_ARTICLE_CHARS_PER_BRIEF].strip()
                    + " [TRUNCATED]"
                )
            article_inputs.append(
                {
                    "index": index,
                    "title": article.title,
                    "source": article.feed_title,
                    "url": article.url,
                    "content": normalized_content,
                }
            )

        briefs = await self._generate_article_briefs(
            article_inputs,
            model=model,
            timeout_seconds=timeout_seconds,
            style=prefs.style,
            style_guidance=style_guidance,
            debug_path=debug_path,
            episode_id=episode_id,
            digest_id=digest_id,
        )
        briefs_block = self._render_briefs_block(briefs)

        outline = await self._generate_solo_script_outline(
            briefs_block=briefs_block,
            model=model,
            timeout_seconds=timeout_seconds,
            style=prefs.style,
            style_guidance=style_guidance,
            length_minutes=prefs.preferred_length_minutes,
            debug_path=debug_path,
            episode_id=episode_id,
            digest_id=digest_id,
        )
        prompt = SCRIPT_SOLO_PROMPT_TEMPLATE.format(
            length_minutes=prefs.preferred_length_minutes,
            style=prefs.style,
            style_guidance=style_guidance,
            tts_delivery_guidance=tts_delivery_guidance,
            outline_block=outline,
            briefs_block=briefs_block,
        )

        if debug_path is not None:
            self._write_script_prompt_debug(
                debug_path,
                {
                    "stage": "final_solo_script",
                    "episode_id": str(episode_id),
                    "digest_id": str(digest_id) if digest_id else None,
                    "model": model,
                    "style": prefs.style,
                    "length_minutes": prefs.preferred_length_minutes,
                    "article_count": len(articles),
                    "timeout_seconds": timeout_seconds,
                    "generated_at_utc": datetime.utcnow().isoformat() + "Z",
                    "system_prompt": script_system_prompt,
                    "user_prompt": prompt,
                },
            )

        retries = 2
        for attempt in range(retries + 1):
            logger.info(
                "Generating solo podcast script attempt",
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
                system_prompt=script_system_prompt,
                timeout_seconds=timeout_seconds,
            )
            if failed or not script.strip():
                continue
            try:
                self.parse_solo_script(script)
                logger.info(
                    "Solo podcast script generated and validated",
                    extra={
                        "attempt": attempt + 1,
                        "script_chars": len(script.strip()),
                    },
                )
                return script.strip()
            except ValueError as exc:
                logger.warning(
                    "Generated solo script failed validation (attempt %s/%s): %s",
                    attempt + 1,
                    retries + 1,
                    exc,
                )
                await asyncio.sleep(0.5 * (attempt + 1))

        logger.warning("Solo script generation failed; trying direct fallback prompt")
        fallback_prompt = self._build_direct_solo_script_prompt(
            articles=articles,
            length_minutes=prefs.preferred_length_minutes,
            style=prefs.style,
            style_guidance=style_guidance,
            tts_delivery_guidance=tts_delivery_guidance,
        )
        for attempt in range(retries + 1):
            script, failed = await self.llm_service._run_completion(
                fallback_prompt,
                model,
                retries=1,
                system_prompt=script_system_prompt,
                timeout_seconds=timeout_seconds,
            )
            if failed or not script.strip():
                continue
            try:
                self.parse_solo_script(script)
                return script.strip()
            except ValueError:
                await asyncio.sleep(0.5 * (attempt + 1))
        raise RuntimeError("Failed to generate valid solo podcast script")

    async def _generate_solo_script_outline(
        self,
        *,
        briefs_block: str,
        model: str,
        timeout_seconds: int,
        style: str,
        style_guidance: str,
        length_minutes: int,
        debug_path: Path | None,
        episode_id: UUID | None,
        digest_id: UUID | None,
    ) -> str:
        """Generate episode outline for a solo monologue."""
        prompt = SCRIPT_SOLO_OUTLINE_PROMPT_TEMPLATE.format(
            length_minutes=length_minutes,
            style=style,
            style_guidance=style_guidance,
            briefs_block=briefs_block,
        )
        if debug_path is not None:
            self._write_script_prompt_debug(
                debug_path,
                {
                    "stage": "solo_outline",
                    "episode_id": str(episode_id) if episode_id else None,
                    "digest_id": str(digest_id) if digest_id else None,
                    "model": model,
                    "system_prompt": SCRIPT_SOLO_SYSTEM_PROMPT,
                    "user_prompt": prompt,
                },
            )

        for attempt in range(3):
            outline, failed = await self.llm_service._run_completion(
                prompt,
                model,
                retries=1,
                system_prompt=SCRIPT_SOLO_SYSTEM_PROMPT,
                timeout_seconds=timeout_seconds,
            )
            if not failed and outline.strip():
                return outline.strip()
            await asyncio.sleep(0.3 * (attempt + 1))
        return "Opening -> cover top stories -> explain implications -> closing."

    def _build_direct_solo_script_prompt(
        self,
        *,
        articles: list[DigestArticle],
        length_minutes: int,
        style: str,
        style_guidance: str,
        tts_delivery_guidance: str,
    ) -> str:
        """Build one-shot solo prompt as fallback if chunked generation fails."""
        articles_block_lines: list[str] = []
        for index, article in enumerate(articles, start=1):
            clean_snippet = re.sub(r"\s+", " ", article.content).strip()[:1200]
            articles_block_lines.append(
                f"{index}. {article.title}\n"
                f"Source: {article.feed_title}\n"
                f"URL: {article.url}\n"
                f"Source detail for context, stakes, and examples: {clean_snippet}"
            )
        articles_block = "\n\n".join(articles_block_lines)
        return SCRIPT_SOLO_PROMPT_TEMPLATE.format(
            length_minutes=length_minutes,
            style=style,
            style_guidance=style_guidance,
            tts_delivery_guidance=tts_delivery_guidance,
            outline_block="Use this source list directly as outline.",
            briefs_block=articles_block,
        )

    @staticmethod
    def _script_system_prompt_for_tts_solo(*, provider: str, elevenlabs_model_id: str) -> str:
        """Return solo system prompt with provider-specific constraints."""
        normalized_provider = (provider or "openai").strip().lower()
        if normalized_provider != "elevenlabs":
            return SCRIPT_SOLO_SYSTEM_PROMPT

        model_id = (elevenlabs_model_id or "").strip().lower()
        extra = [
            "Additional spoken-delivery rules for ElevenLabs:",
            "- Write text that sounds natural when spoken out loud, not read silently.",
            "- Expand abbreviations, symbols, URLs, and shorthand when practical.",
            "- Use contractions and occasional short interjections to keep rhythm human.",
            "- Avoid overly dense clauses or robotic repeated sentence templates.",
        ]
        if model_id == "eleven_v3":
            extra.extend(
                [
                    "- Keep paragraphs substantial enough for stable prosody.",
                    "- Use punctuation and conversational cadence cues instead of SSML tags.",
                    "- Optional inline audio tags are allowed (for example [laughs], [sighs]).",
                    "- Keep tags sparse and intentional.",
                ]
            )
        return SCRIPT_SOLO_SYSTEM_PROMPT + "\n" + "\n".join(extra)

    @staticmethod
    def _script_style_guidance_solo(style: str) -> str:
        """Return style-specific guidance for solo monologue scripts."""
        if style == "deep-dive":
            return (
                "Prioritize depth, tradeoffs, and context; unpack why stories matter "
                "with concrete examples and thoughtful analysis."
            )
        if style == "formal":
            return (
                "Keep tone professional and composed while still sounding human; "
                "use precise explanations and clear transitions between topics."
            )
        return (
            "Keep tone approachable and lively; include light humor, rhetorical questions, "
            "and natural thinking-out-loud moments without losing factual clarity."
        )

    @staticmethod
    def parse_solo_script(script: str) -> str:
        """Validate and clean a solo monologue script. Returns the cleaned text."""
        text = script.strip()
        if not text:
            raise ValueError("Script is empty")

        # Reject if HOST tags leaked into the script
        if re.search(r"\[HOST_[AB]\]:", text):
            raise ValueError("Solo script contains HOST tags")

        # Split into content paragraphs (skip [pause] markers)
        paragraphs = [
            p.strip()
            for p in text.split("\n\n")
            if p.strip() and p.strip().lower() != "[pause]"
        ]
        # Also count single-newline-separated paragraphs
        if len(paragraphs) < 2:
            paragraphs = [
                p.strip()
                for p in text.split("\n")
                if p.strip()
                and p.strip().lower() != "[pause]"
                and len(p.strip()) > 20
            ]

        if len(paragraphs) < 4:
            raise ValueError(
                f"Solo script must contain at least 4 content paragraphs, got {len(paragraphs)}"
            )

        if len(text) < 200:
            raise ValueError(
                f"Solo script must be at least 200 characters, got {len(text)}"
            )

        return text

    async def generate_solo_audio(
        self,
        episode_id: UUID,
        script: str,
        prefs: PodcastGenerationPreferences,
    ) -> AudioGenerationResult:
        """Synthesize audio from a solo monologue script."""
        if not script.strip():
            raise RuntimeError("No script text for solo audio generation")

        output_dir = Path(self.settings.output_dir) / "podcasts"
        output_dir.mkdir(parents=True, exist_ok=True)
        final_path = output_dir / f"{episode_id}.mp3"
        debug_dir = Path(self.settings.logs_dir) / "podcast_tts_prompts"
        debug_dir.mkdir(parents=True, exist_ok=True)
        debug_path = debug_dir / f"{episode_id}.jsonl"
        debug_path.write_text("", encoding="utf-8")

        provider = (prefs.tts_provider or "openai").strip().lower()
        if provider not in SUPPORTED_TTS_PROVIDERS:
            raise RuntimeError(f"Unsupported podcast TTS provider: {provider}")

        # Clean script: replace [pause] markers with ellipses for natural TTS pauses
        cleaned = re.sub(r"\[pause\]", "...", script, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        voice = prefs.host_a_voice
        if provider == "openai":
            voice = self._ensure_supported_voice(voice, "alloy")
        else:
            voice = voice.strip() or ELEVENLABS_DEFAULT_HOST_A_VOICE

        self._append_tts_debug_entry(
            debug_path,
            {
                "event": "solo_audio_generation_started",
                "episode_id": str(episode_id),
                "provider": provider,
                "voice": voice,
                "script_chars": len(cleaned),
                "timestamp_utc": datetime.utcnow().isoformat() + "Z",
            },
        )

        synthesized_chars = 0

        if provider == "elevenlabs":
            await self._check_elevenlabs_quota(prefs, len(cleaned))
            # ElevenLabs handles long text natively — single API call
            normalized = self._normalize_tts_segment_text(
                cleaned,
                provider=provider,
                elevenlabs_model_id=prefs.elevenlabs_model_id,
            )
            self._append_tts_debug_entry(
                debug_path,
                {
                    "event": "tts_request",
                    "segment_index": 1,
                    "speaker": "solo",
                    "voice": voice,
                    "provider": provider,
                    "text_chars": len(normalized),
                    "timestamp_utc": datetime.utcnow().isoformat() + "Z",
                },
            )
            audio_bytes, tts_error = await self._synthesize_segment_with_retry(
                text=normalized,
                voice=voice,
                provider=provider,
                prefs=prefs,
            )
            if not audio_bytes:
                raise RuntimeError(f"TTS failed for solo script: {tts_error}")
            final_path.write_bytes(audio_bytes)
            synthesized_chars = len(cleaned)
        else:
            # OpenAI: chunk at paragraph boundaries (max ~3900 chars per chunk)
            paragraphs = [p.strip() for p in cleaned.split("\n") if p.strip()]
            if not paragraphs:
                paragraphs = [cleaned]
            chunks = self._chunk_paragraphs_for_openai(paragraphs, max_chars=3900)

            with tempfile.TemporaryDirectory(prefix="podcast_solo_tts_") as tmpdir:
                chunk_paths: list[Path] = []
                for idx, chunk_text in enumerate(chunks, start=1):
                    normalized = self._normalize_tts_segment_text(
                        chunk_text,
                        provider=provider,
                    )
                    self._append_tts_debug_entry(
                        debug_path,
                        {
                            "event": "tts_request",
                            "segment_index": idx,
                            "speaker": "solo",
                            "voice": voice,
                            "provider": provider,
                            "text_chars": len(normalized),
                            "timestamp_utc": datetime.utcnow().isoformat() + "Z",
                        },
                    )
                    audio_bytes, tts_error = await self._synthesize_segment_with_retry(
                        text=normalized,
                        voice=voice,
                        provider=provider,
                        prefs=prefs,
                    )
                    if not audio_bytes:
                        logger.warning("Skipping solo TTS chunk %d after retries: %s", idx, tts_error)
                        continue
                    path = Path(tmpdir) / f"chunk_{idx:04d}.mp3"
                    path.write_bytes(audio_bytes)
                    chunk_paths.append(path)
                    synthesized_chars += len(chunk_text)

                if not chunk_paths:
                    raise RuntimeError("TTS failed for all solo chunks")

                if len(chunk_paths) == 1:
                    shutil.copyfile(chunk_paths[0], final_path)
                else:
                    await self._concat_segments_seamless(chunk_paths, final_path)

        audio_size = final_path.stat().st_size
        duration = await self._probe_audio_duration_seconds(final_path)
        self._append_tts_debug_entry(
            debug_path,
            {
                "event": "solo_audio_generation_completed",
                "episode_id": str(episode_id),
                "audio_size_bytes": audio_size,
                "duration_seconds": duration,
                "synthesized_chars": synthesized_chars,
                "timestamp_utc": datetime.utcnow().isoformat() + "Z",
            },
        )
        logger.info(
            "Solo podcast audio generation complete",
            extra={
                "episode_id": str(episode_id),
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

    @staticmethod
    def _chunk_paragraphs_for_openai(
        paragraphs: list[str],
        max_chars: int = 3900,
    ) -> list[str]:
        """Greedily accumulate paragraphs into chunks under max_chars limit."""
        chunks: list[str] = []
        current: list[str] = []
        current_len = 0

        for para in paragraphs:
            para_len = len(para)
            if para_len > max_chars:
                # Flush current accumulation
                if current:
                    chunks.append("\n\n".join(current))
                    current = []
                    current_len = 0
                # Split oversized paragraph at sentence boundaries
                sentences = re.split(r"(?<=[.!?])\s+", para)
                sent_chunk: list[str] = []
                sent_len = 0
                for sentence in sentences:
                    if sent_len + len(sentence) + 1 > max_chars and sent_chunk:
                        chunks.append(" ".join(sent_chunk))
                        sent_chunk = []
                        sent_len = 0
                    sent_chunk.append(sentence)
                    sent_len += len(sentence) + 1
                if sent_chunk:
                    chunks.append(" ".join(sent_chunk))
                continue

            if current_len + para_len + 2 > max_chars and current:
                chunks.append("\n\n".join(current))
                current = []
                current_len = 0

            current.append(para)
            current_len += para_len + 2

        if current:
            chunks.append("\n\n".join(current))

        return chunks

    async def _concat_segments_seamless(
        self,
        segment_paths: list[Path],
        output_path: Path,
    ) -> None:
        """Concatenate MP3 segments seamlessly without silence gaps."""
        if len(segment_paths) == 1:
            shutil.copyfile(segment_paths[0], output_path)
            return

        with tempfile.TemporaryDirectory(prefix="podcast_concat_") as tmpdir:
            concat_list_path = Path(tmpdir) / "concat.txt"
            concat_lines = [
                f"file '{self._ffmpeg_quote(path)}'" for path in segment_paths
            ]
            concat_list_path.write_text("\n".join(concat_lines), encoding="utf-8")

            cmd = [
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
            await self._run_subprocess(cmd, "failed to concatenate solo podcast audio")

    async def _generate_article_briefs(
        self,
        article_inputs: list[dict[str, Any]],
        *,
        model: str,
        timeout_seconds: int,
        style: str,
        style_guidance: str,
        debug_path: Path | None,
        episode_id: UUID | None,
        digest_id: UUID | None,
    ) -> list[dict[str, Any]]:
        """Generate concise briefs from full article content using chunked prompts."""
        indexed_briefs: dict[int, dict[str, Any]] = {}
        chunks = [
            article_inputs[i : i + SCRIPT_BRIEF_CHUNK_SIZE]
            for i in range(0, len(article_inputs), SCRIPT_BRIEF_CHUNK_SIZE)
        ]
        for chunk_num, chunk in enumerate(chunks, start=1):
            articles_block = "\n\n".join(
                (
                    f"Index: {item['index']}\n"
                    f"Title: {item['title']}\n"
                    f"Source: {item['source']}\n"
                    f"URL: {item['url']}\n"
                    f"Full content:\n{item['content']}"
                )
                for item in chunk
            )
            prompt = SCRIPT_BRIEF_PROMPT_TEMPLATE.format(
                style=style,
                style_guidance=style_guidance,
                articles_block=articles_block,
            )
            if debug_path is not None:
                self._write_script_prompt_debug(
                    debug_path,
                    {
                        "stage": "brief_chunk",
                        "chunk_index": chunk_num,
                        "chunk_size": len(chunk),
                        "episode_id": str(episode_id) if episode_id else None,
                        "digest_id": str(digest_id) if digest_id else None,
                        "model": model,
                        "system_prompt": SCRIPT_BRIEF_SYSTEM_PROMPT,
                        "user_prompt": prompt,
                    },
                )

            parsed_briefs: list[dict[str, Any]] = []
            for attempt in range(3):
                completion, failed = await self.llm_service._run_completion(
                    prompt,
                    model,
                    retries=1,
                    system_prompt=SCRIPT_BRIEF_SYSTEM_PROMPT,
                    timeout_seconds=timeout_seconds,
                )
                if failed or not completion.strip():
                    await asyncio.sleep(0.3 * (attempt + 1))
                    continue
                parsed_briefs = self._parse_chunk_briefs_json(completion)
                if parsed_briefs:
                    break
                await asyncio.sleep(0.3 * (attempt + 1))

            if not parsed_briefs:
                parsed_briefs = [self._fallback_brief(item) for item in chunk]

            for brief in parsed_briefs:
                index = int(brief["index"])
                indexed_briefs[index] = brief

            for item in chunk:
                index = int(item["index"])
                if index not in indexed_briefs:
                    indexed_briefs[index] = self._fallback_brief(item)

        return [indexed_briefs[idx] for idx in sorted(indexed_briefs)]

    @staticmethod
    def _parse_chunk_briefs_json(raw_text: str) -> list[dict[str, Any]]:
        """Parse chunk brief JSON response and return normalized brief objects."""
        start = raw_text.find("{")
        end = raw_text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return []
        try:
            parsed = json.loads(raw_text[start : end + 1])
        except json.JSONDecodeError:
            return []
        briefs = parsed.get("briefs")
        if not isinstance(briefs, list):
            return []

        normalized: list[dict[str, Any]] = []
        for item in briefs:
            if not isinstance(item, dict):
                continue
            try:
                index = int(item.get("index"))
            except Exception:
                continue
            title = str(item.get("title", "")).strip()
            summary = str(item.get("summary", "")).strip()
            key_points = [
                str(point).strip()
                for point in item.get("key_points", [])
                if isinstance(point, str) and point.strip()
            ][:4]
            explainers = [
                str(point).strip()
                for point in item.get("explainers", [])
                if isinstance(point, str) and point.strip()
            ][:3]
            specific_details = [
                str(point).strip()
                for point in item.get("specific_details", [])
                if isinstance(point, str) and point.strip()
            ][:4]
            why_it_matters = str(item.get("why_it_matters", "")).strip()
            tension = str(item.get("tension", "")).strip()
            listener_angle = str(item.get("listener_angle", "")).strip()
            follow_up_question = str(item.get("follow_up_question", "")).strip()
            banter_hook = str(item.get("banter_hook", "")).strip()
            if not summary:
                continue
            normalized.append(
                {
                    "index": index,
                    "title": title,
                    "summary": summary,
                    "key_points": key_points,
                    "explainers": explainers,
                    "why_it_matters": why_it_matters,
                    "tension": tension,
                    "specific_details": specific_details,
                    "listener_angle": listener_angle,
                    "follow_up_question": follow_up_question,
                    "banter_hook": banter_hook,
                }
            )
        return normalized

    @staticmethod
    def _fallback_brief(article_input: dict[str, Any]) -> dict[str, Any]:
        """Generate a deterministic fallback brief when JSON parsing fails."""
        content = str(article_input.get("content", "")).strip()
        summary = content[:420] if content else "No content summary available."
        return {
            "index": int(article_input["index"]),
            "title": str(article_input.get("title", "")),
            "summary": summary,
            "key_points": [],
            "explainers": [],
            "why_it_matters": "",
            "tension": "",
            "specific_details": [],
            "listener_angle": "",
            "follow_up_question": "",
            "banter_hook": "",
        }

    @staticmethod
    def _render_briefs_block(briefs: list[dict[str, Any]]) -> str:
        """Render brief objects into compact text for outline/final prompts."""
        lines: list[str] = []
        for brief in briefs:
            key_points = "; ".join(brief.get("key_points") or [])
            explainers = "; ".join(brief.get("explainers") or [])
            specific_details = "; ".join(brief.get("specific_details") or [])
            lines.append(
                f"[{brief['index']}] {brief.get('title','')}\n"
                f"Summary: {brief.get('summary','')}\n"
                f"Key points: {key_points}\n"
                f"Explainers: {explainers}\n"
                f"Why it matters: {brief.get('why_it_matters','')}\n"
                f"Tension: {brief.get('tension','')}\n"
                f"Specific details: {specific_details}\n"
                f"Listener angle: {brief.get('listener_angle','')}\n"
                f"Follow-up question: {brief.get('follow_up_question','')}\n"
                f"Banter hook: {brief.get('banter_hook','')}"
            )
        return "\n\n".join(lines)

    async def _generate_script_outline(
        self,
        *,
        briefs_block: str,
        model: str,
        timeout_seconds: int,
        style: str,
        style_guidance: str,
        length_minutes: int,
        debug_path: Path | None,
        episode_id: UUID | None,
        digest_id: UUID | None,
    ) -> str:
        """Generate episode outline from chunked article briefs."""
        prompt = SCRIPT_OUTLINE_PROMPT_TEMPLATE.format(
            length_minutes=length_minutes,
            style=style,
            style_guidance=style_guidance,
            briefs_block=briefs_block,
        )
        if debug_path is not None:
            self._write_script_prompt_debug(
                debug_path,
                {
                    "stage": "outline",
                    "episode_id": str(episode_id) if episode_id else None,
                    "digest_id": str(digest_id) if digest_id else None,
                    "model": model,
                    "system_prompt": SCRIPT_OUTLINE_SYSTEM_PROMPT,
                    "user_prompt": prompt,
                },
            )

        for attempt in range(3):
            outline, failed = await self.llm_service._run_completion(
                prompt,
                model,
                retries=1,
                system_prompt=SCRIPT_OUTLINE_SYSTEM_PROMPT,
                timeout_seconds=timeout_seconds,
            )
            if not failed and outline.strip():
                return outline.strip()
            await asyncio.sleep(0.3 * (attempt + 1))
        return "Opening -> cover top stories -> explain implications -> closing."

    def _build_direct_script_prompt(
        self,
        *,
        articles: list[DigestArticle],
        length_minutes: int,
        style: str,
        style_guidance: str,
        tts_delivery_guidance: str,
    ) -> str:
        """Build legacy one-shot prompt as fallback if chunked generation fails."""
        articles_block_lines: list[str] = []
        for index, article in enumerate(articles, start=1):
            clean_snippet = re.sub(r"\s+", " ", article.content).strip()[:1200]
            articles_block_lines.append(
                f"{index}. {article.title}\n"
                f"Source: {article.feed_title}\n"
                f"URL: {article.url}\n"
                f"Source detail for context, stakes, and examples: {clean_snippet}"
            )
        articles_block = "\n\n".join(articles_block_lines)
        return SCRIPT_PROMPT_TEMPLATE.format(
            length_minutes=length_minutes,
            style=style,
            style_guidance=style_guidance,
            tts_delivery_guidance=tts_delivery_guidance,
            outline_block="Use this source list directly as outline.",
            briefs_block=articles_block,
        )

    @staticmethod
    def _script_system_prompt_for_tts(*, provider: str, elevenlabs_model_id: str) -> str:
        """Return system prompt with provider-specific spoken-delivery constraints."""
        normalized_provider = (provider or "openai").strip().lower()
        if normalized_provider != "elevenlabs":
            return SCRIPT_SYSTEM_PROMPT

        model_id = (elevenlabs_model_id or "").strip().lower()
        extra = [
            "Additional spoken-delivery rules for ElevenLabs:",
            "- Write text that sounds natural when spoken out loud, not read silently.",
            "- Expand abbreviations, symbols, URLs, and shorthand when practical.",
            "- Use contractions and occasional short interjections to keep rhythm human.",
            "- Avoid overly dense clauses or robotic repeated sentence templates.",
        ]
        if model_id == "eleven_v3":
            extra.extend(
                [
                    "- Avoid ultra-short lines; most turns should be substantial enough for stable prosody.",
                    "- Use punctuation and conversational cadence cues instead of SSML tags.",
                    "- Optional inline audio tags are allowed inside host lines (for example [laughs], [sighs], [whispers]).",
                    "- Keep tags sparse and intentional; avoid tag-heavy delivery.",
                ]
            )
        return SCRIPT_SYSTEM_PROMPT + "\n" + "\n".join(extra)

    @staticmethod
    def _tts_script_delivery_guidance(*, provider: str, elevenlabs_model_id: str) -> str:
        """Return prompt guidance that improves natural TTS delivery for selected provider."""
        normalized_provider = (provider or "openai").strip().lower()
        if normalized_provider != "elevenlabs":
            return (
                "Keep delivery clean and spoken. Avoid awkward punctuation chains and spell out only when needed."
            )

        model_id = (elevenlabs_model_id or "").strip().lower()
        if model_id == "eleven_v3":
            return (
                "Optimize for Eleven v3 natural dialogue: keep most lines around 12-40 words, "
                "avoid ultra-short one-liners, vary pacing with punctuation, use occasional conversational "
                "asides, and ensure numbers/dates/currency/abbreviations are spoken naturally. "
                "Use sparse inline audio/emotion tags within host lines (e.g. [laughs], [sighs], [whispers], "
                "[excited], [thoughtful]) only where they add realism. Do not overuse tags: target about one "
                "tag every 4-8 lines, never more than one tag in a line, and avoid repeating the same tag in "
                "adjacent turns."
            )
        return (
            "Optimize for ElevenLabs TTS clarity: expand symbols, dates, times, currency, and abbreviations "
            "into spoken forms where needed; keep sentence rhythm varied and conversational."
        )

    @staticmethod
    def _write_script_prompt_debug(path: Path, payload: dict[str, Any]) -> None:
        """Persist one script-generation prompt payload for debugging."""
        try:
            existing_events: list[dict[str, Any]] = []
            if path.exists():
                try:
                    current = json.loads(path.read_text(encoding="utf-8"))
                    if isinstance(current, dict) and isinstance(current.get("events"), list):
                        existing_events = [event for event in current["events"] if isinstance(event, dict)]
                except Exception:
                    existing_events = []
            existing_events.append(payload)
            path.write_text(
                json.dumps({"events": existing_events}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            logger.warning("Failed writing podcast script prompt debug file", exc_info=True)

    @staticmethod
    def _script_style_guidance(style: str) -> str:
        """Return style-specific conversation guidance for script generation."""
        if style == "deep-dive":
            return (
                "Prioritize depth, tradeoffs, and context; let hosts unpack why stories matter "
                "with concrete examples and occasional friendly debate."
            )
        if style == "formal":
            return (
                "Keep tone professional and composed while still sounding human; banter should be subtle, "
                "with precise explanations and clear transitions."
            )
        return (
            "Keep tone approachable and lively; include light humor, quick reactions, and natural back-and-forth "
            "without losing factual clarity."
        )

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
        prefs: PodcastGenerationPreferences,
    ) -> AudioGenerationResult:
        """Synthesize audio for script segments and stitch into one MP3."""
        if not segments:
            raise RuntimeError("No script segments for audio generation")

        output_dir = Path(self.settings.output_dir) / "podcasts"
        output_dir.mkdir(parents=True, exist_ok=True)
        final_path = output_dir / f"{episode_id}.mp3"
        debug_dir = Path(self.settings.logs_dir) / "podcast_tts_prompts"
        debug_dir.mkdir(parents=True, exist_ok=True)
        debug_path = debug_dir / f"{episode_id}.jsonl"
        debug_path.write_text("", encoding="utf-8")
        logger.info(
            "Podcast audio generation started",
            extra={
                "episode_id": str(episode_id),
                "segment_count": len(segments),
                "output_path": str(final_path),
                "tts_debug_path": str(debug_path),
            },
        )
        self._append_tts_debug_entry(
            debug_path,
            {
                "event": "audio_generation_started",
                "episode_id": str(episode_id),
                "segment_count": len(segments),
                "provider": (prefs.tts_provider or "openai").strip().lower(),
                "timestamp_utc": datetime.utcnow().isoformat() + "Z",
            },
        )

        synthesized_chars = 0
        with tempfile.TemporaryDirectory(prefix="podcast_tts_") as tmpdir:
            segment_paths: list[Path] = []
            provider = (prefs.tts_provider or "openai").strip().lower()
            if provider not in SUPPORTED_TTS_PROVIDERS:
                raise RuntimeError(f"Unsupported podcast TTS provider: {provider}")
            normalized_segment_texts = [
                self._normalize_tts_segment_text(
                    segment.text,
                    provider=provider,
                    elevenlabs_model_id=prefs.elevenlabs_model_id,
                )
                for segment in segments
            ]
            total_chars = sum(len(t) for t in normalized_segment_texts)
            if provider == "elevenlabs":
                await self._check_elevenlabs_quota(prefs, total_chars)
            for index, segment in enumerate(segments, start=1):
                normalized_text = normalized_segment_texts[index - 1]
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

                self._append_tts_debug_entry(
                    debug_path,
                    {
                        "event": "tts_request",
                        "segment_index": index,
                        "speaker": segment.speaker,
                        "voice": voice,
                        "provider": provider,
                        "text": segment.text,
                        "normalized_text": normalized_text,
                        "text_chars": len(segment.text),
                        "normalized_text_chars": len(normalized_text),
                        "timestamp_utc": datetime.utcnow().isoformat() + "Z",
                    },
                )
                audio_bytes, tts_error = await self._synthesize_segment_with_retry(
                    text=normalized_text,
                    voice=voice,
                    provider=provider,
                    prefs=prefs,
                    previous_text=(
                        normalized_segment_texts[index - 2] if index > 1 else None
                    ),
                    next_text=(
                        normalized_segment_texts[index] if index < len(normalized_segment_texts) else None
                    ),
                )
                if not audio_bytes:
                    logger.warning("Skipping TTS segment after retries: %s", segment.speaker)
                    self._append_tts_debug_entry(
                        debug_path,
                        {
                            "event": "tts_segment_failed",
                            "segment_index": index,
                            "speaker": segment.speaker,
                            "voice": voice,
                            "provider": provider,
                            "error": tts_error,
                            "timestamp_utc": datetime.utcnow().isoformat() + "Z",
                        },
                    )
                    # Abort early on quota exhaustion — retrying won't help
                    if tts_error and "quota_exceeded" in tts_error:
                        raise RuntimeError(
                            f"ElevenLabs quota exhausted during audio generation: {tts_error}"
                        )
                    continue
                path = Path(tmpdir) / f"segment_{index:04d}.mp3"
                path.write_bytes(audio_bytes)
                segment_paths.append(path)
                synthesized_chars += len(segment.text)
                self._append_tts_debug_entry(
                    debug_path,
                    {
                        "event": "tts_segment_synthesized",
                        "segment_index": index,
                        "speaker": segment.speaker,
                        "voice": voice,
                        "provider": provider,
                        "audio_bytes": len(audio_bytes),
                        "timestamp_utc": datetime.utcnow().isoformat() + "Z",
                    },
                )

            if not segment_paths:
                self._append_tts_debug_entry(
                    debug_path,
                    {
                        "event": "audio_generation_failed",
                        "reason": "TTS failed for all segments",
                        "timestamp_utc": datetime.utcnow().isoformat() + "Z",
                    },
                )
                raise RuntimeError("TTS failed for all segments")

            await self._stitch_segments(segment_paths, final_path)

        audio_size = final_path.stat().st_size
        duration = await self._probe_audio_duration_seconds(final_path)
        self._append_tts_debug_entry(
            debug_path,
            {
                "event": "audio_generation_completed",
                "episode_id": str(episode_id),
                "synthesized_segment_count": len(segment_paths),
                "audio_size_bytes": audio_size,
                "duration_seconds": duration,
                "synthesized_chars": synthesized_chars,
                "timestamp_utc": datetime.utcnow().isoformat() + "Z",
            },
        )
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

    async def _check_elevenlabs_quota(
        self,
        prefs: PodcastGenerationPreferences,
        required_chars: int,
    ) -> None:
        """Pre-flight check: verify ElevenLabs account has enough character quota."""
        api_key = (prefs.elevenlabs_api_key or "").strip()
        if not api_key:
            return  # Will fail later with a clear missing-key error
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
                response = await client.get(
                    "https://api.elevenlabs.io/v1/user/subscription",
                    headers={"xi-api-key": api_key},
                )
                if response.status_code != 200:
                    logger.warning(
                        "ElevenLabs quota check failed (HTTP %s), proceeding anyway",
                        response.status_code,
                    )
                    return
                data = response.json()
                limit = data.get("character_limit", 0)
                used = data.get("character_count", 0)
                remaining = max(0, limit - used)
                if required_chars > remaining:
                    raise RuntimeError(
                        f"ElevenLabs quota insufficient: {remaining} credits remaining, "
                        f"~{required_chars} required for this episode. "
                        f"Quota resets at the start of the next billing cycle."
                    )
                logger.info(
                    "ElevenLabs quota check passed: %d remaining, ~%d required",
                    remaining,
                    required_chars,
                )
        except RuntimeError:
            raise
        except Exception as exc:
            logger.warning("ElevenLabs quota pre-check failed: %s, proceeding anyway", exc)

    async def _synthesize_segment_with_retry(
        self,
        *,
        text: str,
        voice: str,
        provider: str,
        prefs: PodcastGenerationPreferences,
        previous_text: str | None = None,
        next_text: str | None = None,
    ) -> tuple[bytes, str | None]:
        """Generate one TTS segment with bounded retries.

        Returns (audio_bytes, error_message). On success error_message is None.
        On failure audio_bytes is empty and error_message describes the last error.
        """
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                audio = await self._synthesize_segment(
                    text=text,
                    voice=voice,
                    provider=provider,
                    prefs=prefs,
                    previous_text=previous_text,
                    next_text=next_text,
                )
                return audio, None
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
        error_msg = str(last_error)[:300] if last_error else "unknown error"
        logger.error("%s TTS failed after retries: %s", provider, last_error)
        return b"", error_msg

    @staticmethod
    def _append_tts_debug_entry(path: Path, payload: dict[str, Any]) -> None:
        """Append one JSONL entry to per-episode TTS debug trace."""
        try:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception:
            logger.warning("Failed writing podcast TTS debug entry", exc_info=True)

    async def _synthesize_segment(
        self,
        *,
        text: str,
        voice: str,
        provider: str,
        prefs: PodcastGenerationPreferences,
        previous_text: str | None = None,
        next_text: str | None = None,
    ) -> bytes:
        """Call selected TTS provider API."""
        if provider == "openai":
            return await self._synthesize_segment_openai(text=text, voice=voice, prefs=prefs)
        if provider == "elevenlabs":
            return await self._synthesize_segment_elevenlabs(
                text=text,
                voice=voice,
                prefs=prefs,
                previous_text=previous_text,
                next_text=next_text,
            )
        raise RuntimeError(f"Unsupported podcast TTS provider: {provider}")

    async def _synthesize_segment_openai(
        self,
        *,
        text: str,
        voice: str,
        prefs: PodcastGenerationPreferences,
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
        prefs: PodcastGenerationPreferences,
        previous_text: str | None = None,
        next_text: str | None = None,
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
            "apply_text_normalization": self._elevenlabs_text_normalization_mode(model_id),
        }
        if self._elevenlabs_supports_context_window(model_id):
            if previous_text:
                payload["previous_text"] = previous_text[:800]
            if next_text:
                payload["next_text"] = next_text[:800]
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

    @staticmethod
    def _elevenlabs_text_normalization_mode(model_id: str) -> str:
        """Return safe normalization mode supported by chosen ElevenLabs model."""
        normalized = (model_id or "").strip().lower()
        # Keep broad compatibility for non-v3 models.
        if normalized != "eleven_v3":
            return "auto"
        return "on"

    @staticmethod
    def _elevenlabs_supports_context_window(model_id: str) -> bool:
        """Whether previous/next text context parameters are supported."""
        return (model_id or "").strip().lower() != "eleven_v3"

    @staticmethod
    def _normalize_tts_segment_text(
        text: str,
        *,
        provider: str,
        elevenlabs_model_id: str | None = None,
    ) -> str:
        """Normalize script lines into more speakable text for TTS engines."""
        normalized = re.sub(r"\s+", " ", (text or "")).strip()
        if not normalized:
            return normalized

        normalized = normalized.replace("&", " and ")
        normalized = re.sub(r"\s+", " ", normalized).strip()

        if provider.strip().lower() != "elevenlabs":
            return normalized

        # Light-weight spoken-form normalization guided by ElevenLabs best practices.
        replacements = {
            r"\bDr\.": "Doctor",
            r"\bMr\.": "Mister",
            r"\bMrs\.": "Missus",
            r"\bMs\.": "Miss",
            r"\bProf\.": "Professor",
            r"\bAve\.": "Avenue",
            r"\bBlvd\.": "Boulevard",
            r"\bvs\.": "versus",
            r"\be\.g\.": "for example",
            r"\bi\.e\.": "that is",
        }
        for pattern, value in replacements.items():
            normalized = re.sub(pattern, value, normalized, flags=re.IGNORECASE)

        # Expand common symbol usage.
        normalized = re.sub(r"(\d)\s*%\b", r"\1 percent", normalized)
        normalized = re.sub(r"\bCtrl\s*\+\s*([A-Za-z])\b", r"control \1", normalized)

        # Convert simple ISO dates to spoken-friendly month/day/year.
        def _replace_iso_date(match: re.Match[str]) -> str:
            raw = match.group(0)
            try:
                parsed = datetime.strptime(raw, "%Y-%m-%d")
                return parsed.strftime("%B %d, %Y").replace(" 0", " ")
            except ValueError:
                return raw

        normalized = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", _replace_iso_date, normalized)

        # Convert 24h time to 12h spoken form when obvious.
        def _replace_time(match: re.Match[str]) -> str:
            raw = match.group(0)
            try:
                parsed = datetime.strptime(raw, "%H:%M")
                spoken = parsed.strftime("%I:%M %p").lstrip("0")
                return spoken
            except ValueError:
                return raw

        normalized = re.sub(r"\b([01]?\d|2[0-3]):[0-5]\d\b", _replace_time, normalized)

        # Expand simple monetary amounts for clearer readout.
        def _replace_dollars(match: re.Match[str]) -> str:
            raw_amount = match.group(1).replace(",", "")
            try:
                amount = float(raw_amount)
            except ValueError:
                return match.group(0)
            dollars = int(amount)
            cents = int(round((amount - dollars) * 100))
            if cents:
                return f"{dollars} dollars and {cents} cents"
            return f"{dollars} dollars"

        normalized = re.sub(r"\$(\d[\d,]*(?:\.\d{1,2})?)", _replace_dollars, normalized)

        # Make URLs and domains easier to pronounce.
        normalized = re.sub(
            r"https?://([A-Za-z0-9.-]+)(/[^\s]*)?",
            lambda m: (
                f"{m.group(1).replace('.', ' dot ')}"
                + (
                    f" slash {m.group(2).strip('/').replace('/', ' slash ')}"
                    if m.group(2)
                    else ""
                )
            ),
            normalized,
        )
        normalized = re.sub(
            r"\b([A-Za-z0-9-]+\.[A-Za-z]{2,})(/[^\s]*)?\b",
            lambda m: (
                f"{m.group(1).replace('.', ' dot ')}"
                + (
                    f" slash {m.group(2).strip('/').replace('/', ' slash ')}"
                    if m.group(2)
                    else ""
                )
            ),
            normalized,
        )

        # v3 behaves better with richer turns; avoid ultra-short fragments.
        model_id = (elevenlabs_model_id or "").strip().lower()
        if model_id == "eleven_v3" and len(normalized) < 18 and not normalized.endswith("."):
            normalized += "."

        return re.sub(r"\s+", " ", normalized).strip()

    async def _stitch_segments(self, segment_paths: list[Path], output_path: Path) -> None:
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
            await self._run_subprocess(silence_cmd, "failed to generate silence padding")

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
            await self._run_subprocess(stitch_cmd, "failed to stitch podcast audio")

    @staticmethod
    def _ffmpeg_quote(path: Path) -> str:
        """Escape a file path for ffmpeg concat list syntax."""
        return str(path).replace("'", "'\\''")

    @staticmethod
    async def _run_subprocess(cmd: list[str], error_prefix: str) -> None:
        """Run subprocess command and raise a concise RuntimeError on failure."""
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr_bytes = await process.communicate()
        if process.returncode != 0:
            stderr = stderr_bytes.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"{error_prefix}: {stderr[:300]}")

    @staticmethod
    async def _probe_audio_duration_seconds(path: Path) -> int | None:
        """Get MP3 duration in whole seconds via ffprobe."""
        process = await asyncio.create_subprocess_exec(
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, _ = await process.communicate()
        if process.returncode != 0:
            return None
        try:
            return max(0, int(float(stdout_bytes.decode("utf-8", errors="replace").strip())))
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
