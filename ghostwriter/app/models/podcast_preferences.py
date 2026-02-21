"""Podcast preferences model and API schemas."""

from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column, String
from sqlmodel import Field, SQLModel

PodcastSchedule = Literal["daily", "weekly", "manual"]
PodcastStyle = Literal["casual", "formal", "deep-dive"]
PodcastTTSProvider = Literal["openai", "elevenlabs"]
PodcastScheduleDay = Literal[
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]


class PodcastPreferencesBase(SQLModel):
    """Base podcast preferences fields."""

    user_id: UUID | None = Field(default=None, foreign_key="users.id", index=True)

    enabled: bool = Field(default=False)
    schedule: str = Field(
        default="manual",
        sa_column=Column(String, nullable=False, server_default="manual"),
    )
    schedule_time: str = Field(default="08:00")
    schedule_day: str = Field(
        default="monday",
        sa_column=Column(String, nullable=False, server_default="monday"),
    )

    topic_weights: dict[str, float] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False, server_default="{}"),
    )
    boost_sources: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False, server_default="[]"),
    )
    boost_keywords: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False, server_default="[]"),
    )
    filter_keywords: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False, server_default="[]"),
    )

    preferred_length_minutes: int = Field(default=15, ge=5, le=60)
    script_model: str | None = Field(default=None)
    script_timeout_seconds: int = Field(default=60, ge=30, le=600)
    style: str = Field(
        default="casual",
        sa_column=Column(String, nullable=False, server_default="casual"),
    )
    tts_provider: str = Field(
        default="openai",
        sa_column=Column(String, nullable=False, server_default="openai"),
    )
    openai_tts_model: str = Field(default="tts-1")
    openai_api_key: str | None = Field(default=None)
    elevenlabs_model_id: str = Field(default="eleven_turbo_v2_5")
    elevenlabs_api_key: str | None = Field(default=None)
    elevenlabs_output_format: str = Field(default="mp3_44100_128")
    host_a_voice: str = Field(default="alloy")
    host_b_voice: str = Field(default="echo")
    host_count: int = Field(default=2, ge=1, le=2)

    podcast_feed_enabled: bool = Field(default=False)
    podcast_feed_title: str = Field(default="My Ghostwriter Digest")
    podcast_feed_description: str = Field(
        default="AI-generated audio digest of your RSS feeds"
    )
    podcast_feed_base_url: str | None = Field(default=None)
    podcast_feed_artwork_path: str | None = Field(default=None)
    podcast_feed_token: str = Field(default="")


class PodcastPreferences(PodcastPreferencesBase, table=True):
    """Podcast preferences persisted in the database."""

    __tablename__ = "podcast_preferences"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class PodcastPreferencesRead(SQLModel):
    """Schema for reading podcast preferences."""

    enabled: bool
    schedule: PodcastSchedule
    schedule_time: str
    schedule_day: PodcastScheduleDay
    topic_weights: dict[str, float]
    boost_sources: list[str]
    boost_keywords: list[str]
    filter_keywords: list[str]
    preferred_length_minutes: int
    script_model: str | None = None
    script_timeout_seconds: int
    style: PodcastStyle
    tts_provider: PodcastTTSProvider
    openai_tts_model: str
    elevenlabs_model_id: str
    elevenlabs_output_format: str
    host_a_voice: str
    host_b_voice: str
    host_count: int
    podcast_feed_enabled: bool
    podcast_feed_title: str
    podcast_feed_description: str
    podcast_feed_base_url: str | None = None
    podcast_feed_artwork_path: str | None = None
    updated_at: datetime


class PodcastPreferencesUpdate(SQLModel):
    """Schema for updating podcast preferences."""

    enabled: bool | None = None
    schedule: PodcastSchedule | None = None
    schedule_time: str | None = None
    schedule_day: PodcastScheduleDay | None = None
    topic_weights: dict[str, float] | None = None
    boost_sources: list[str] | None = None
    boost_keywords: list[str] | None = None
    filter_keywords: list[str] | None = None
    preferred_length_minutes: int | None = Field(default=None, ge=5, le=60)
    script_model: str | None = None
    script_timeout_seconds: int | None = Field(default=None, ge=30, le=600)
    style: PodcastStyle | None = None
    tts_provider: PodcastTTSProvider | None = None
    openai_tts_model: str | None = None
    openai_api_key: str | None = None
    elevenlabs_model_id: str | None = None
    elevenlabs_api_key: str | None = None
    elevenlabs_output_format: str | None = None
    host_a_voice: str | None = None
    host_b_voice: str | None = None
    host_count: int | None = Field(default=None, ge=1, le=2)
    podcast_feed_enabled: bool | None = None
    podcast_feed_title: str | None = None
    podcast_feed_description: str | None = None
    podcast_feed_base_url: str | None = None
