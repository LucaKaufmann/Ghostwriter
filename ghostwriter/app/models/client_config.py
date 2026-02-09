"""Client configuration model for shared settings sync."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class ClientConfigBase(SQLModel):
    """Base client config model with shared fields."""

    # Content settings
    min_word_count: int = Field(default=0, ge=0, description="Minimum word count filter for articles")

    # Schedule times (shared across devices)
    morning_hour: int = Field(default=7, ge=0, le=23, description="Morning digest hour (24h)")
    morning_minute: int = Field(default=0, ge=0, le=59, description="Morning digest minute")
    noon_hour: int = Field(default=12, ge=0, le=23, description="Noon digest hour (24h)")
    noon_minute: int = Field(default=0, ge=0, le=59, description="Noon digest minute")
    evening_hour: int = Field(default=18, ge=0, le=23, description="Evening digest hour (24h)")
    evening_minute: int = Field(default=0, ge=0, le=59, description="Evening digest minute")
    timezone: str = Field(default="UTC", description="IANA timezone identifier")

    # Integration toggles
    newsletters_enabled: bool = Field(default=True, description="Enable newsletter integration")
    newsletter_mode: str = Field(default="summarize", description="Newsletter processing mode: raw or summarize")
    whisper_provider: str = Field(
        default="local",
        description="Transcription provider: local, openai, auto",
    )
    whisper_model: str = Field(
        default="base.en",
        description="whisper.cpp model name for local transcription",
    )
    whisper_timeout_minutes: int = Field(
        default=30,
        ge=1,
        le=120,
        description="Transcription timeout in minutes",
    )


class ClientConfig(ClientConfigBase, table=True):
    """
    Client configuration stored in the database.

    This is a singleton table - only one row exists, representing the
    shared configuration that syncs across all client devices.
    """

    __tablename__ = "client_config"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ClientConfigUpdate(SQLModel):
    """Schema for updating client configuration."""

    min_word_count: int | None = Field(default=None, ge=0, description="Minimum word count filter")
    morning_hour: int | None = Field(default=None, ge=0, le=23, description="Morning hour (24h)")
    morning_minute: int | None = Field(default=None, ge=0, le=59, description="Morning minute")
    noon_hour: int | None = Field(default=None, ge=0, le=23, description="Noon hour (24h)")
    noon_minute: int | None = Field(default=None, ge=0, le=59, description="Noon minute")
    evening_hour: int | None = Field(default=None, ge=0, le=23, description="Evening hour (24h)")
    evening_minute: int | None = Field(default=None, ge=0, le=59, description="Evening minute")
    timezone: str | None = Field(default=None, description="IANA timezone")
    newsletters_enabled: bool | None = Field(default=None, description="Enable newsletter integration")
    newsletter_mode: str | None = Field(default=None, description="Newsletter processing mode: raw or summarize")
    whisper_provider: str | None = Field(
        default=None, description="Transcription provider: local, openai, auto"
    )
    whisper_model: str | None = Field(
        default=None, description="whisper.cpp model name for local transcription"
    )
    whisper_timeout_minutes: int | None = Field(
        default=None, ge=1, le=120, description="Transcription timeout in minutes"
    )


class ClientConfigRead(SQLModel):
    """Schema for reading client configuration."""

    min_word_count: int
    morning_hour: int
    morning_minute: int
    noon_hour: int
    noon_minute: int
    evening_hour: int
    evening_minute: int
    timezone: str
    newsletters_enabled: bool
    newsletter_mode: str
    whisper_provider: str
    whisper_model: str
    whisper_timeout_minutes: int
    updated_at: datetime
