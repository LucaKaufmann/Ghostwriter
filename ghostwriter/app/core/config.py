"""Application configuration via environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    All configuration is done via ENV vars for Docker compatibility.
    """

    # General
    log_level: str = Field(default="INFO", description="Logging level")
    timezone: str = Field(default="UTC", description="IANA timezone identifier")
    api_key: str = Field(default="", description="Legacy API key (deprecated, use user accounts)")

    # Authentication
    jwt_secret: str = Field(default="", description="Secret key for JWT tokens (auto-generated if empty)")

    # AI Provider Configuration
    ai_provider: Literal["openai", "gemini", "ollama"] = Field(
        default="ollama", description="AI provider selection"
    )

    # OpenAI
    openai_api_key: str = Field(default="", description="OpenAI API key")
    openai_model: str = Field(default="gpt-5-nano", description="OpenAI model")

    # Gemini
    gemini_api_key: str = Field(default="", description="Google Gemini API key")
    gemini_model: str = Field(default="gemini-2.0-flash-lite", description="Gemini model")

    # Ollama
    ollama_base_url: str = Field(
        default="http://ollama:11434", description="Ollama server URL"
    )
    ollama_model: str = Field(default="llama3.2", description="Ollama model")

    # AI Behavior
    ai_timeout_seconds: int = Field(default=60, description="Per-article AI timeout")
    ai_max_retries: int = Field(default=2, description="Retries before fallback")
    cover_generation_timeout_seconds: int = Field(
        default=60,
        description="Timeout for digest cover image generation",
    )

    # Transcription (whisper.cpp / OpenAI Whisper API)
    whisper_cpp_binary: str = Field(
        default="/usr/local/bin/whisper-cli",
        description="Path to whisper.cpp binary",
    )
    whisper_models_dir: str = Field(
        default="/app/data/models/whisper",
        description="Directory for whisper.cpp models",
    )
    whisper_transcription_timeout_seconds: int = Field(
        default=300, description="Local whisper.cpp transcription timeout"
    )
    openai_whisper_timeout_seconds: int = Field(
        default=120, description="OpenAI Whisper API timeout"
    )

    # Scheduling
    schedule_morning: str = Field(default="07:00", description="Morning schedule (24h)")
    schedule_noon: str = Field(default="12:00", description="Noon schedule (24h)")
    schedule_evening: str = Field(default="18:00", description="Evening schedule (24h)")
    schedule_enabled: bool = Field(default=True, description="Enable scheduled runs")

    # Rate Limiting & Caps
    fetch_delay_ms: int = Field(default=500, description="Delay between feed fetches")
    fetch_timeout_seconds: int = Field(default=30, description="Per-feed fetch timeout")
    max_articles_per_feed: int = Field(default=10, description="Cap per feed per run")
    max_articles_per_digest: int = Field(default=50, description="Overall cap per digest")
    max_concurrent_fetches: int = Field(default=3, description="Parallel feed fetches")

    # Retention & Cleanup
    digest_retention_days: int = Field(default=7, description="Auto-delete old EPUBs")
    seen_article_retention_days: int = Field(
        default=30, description="Deduplication window"
    )

    # Notifications
    webhook_url: str = Field(default="", description="Webhook URL for notifications")
    webhook_on_complete: bool = Field(default=True, description="Notify on success")
    webhook_on_failure: bool = Field(default=True, description="Notify on failure")

    # Wallabag
    wallabag_url: str = Field(default="", description="Wallabag instance URL")
    wallabag_client_id: str = Field(default="", description="Wallabag OAuth client ID")
    wallabag_client_secret: str = Field(default="", description="Wallabag OAuth client secret")
    wallabag_username: str = Field(default="", description="Wallabag username")
    wallabag_password: str = Field(default="", description="Wallabag password")
    wallabag_mode: str = Field(default="raw", description="Processing mode: raw or summarize")
    wallabag_max_articles: int = Field(default=20, description="Max Wallabag articles per digest")
    wallabag_tag_on_process: str = Field(default="ghostwriter", description="Tag added after processing")

    # Gmail Newsletters
    gmail_client_id: str = Field(default="", description="Google OAuth client ID")
    gmail_client_secret: str = Field(default="", description="Google OAuth client secret")
    gmail_label: str = Field(default="Ghostwriter", description="Gmail label to fetch newsletters from")
    gmail_max_articles: int = Field(default=20, description="Max newsletter emails per digest")

    # Network safety
    allow_private_hosts: bool = Field(default=False, description="Allow private/localhost outbound URLs")

    # CORS
    cors_allow_origins: str = Field(
        default="",
        description="Comma-separated list of allowed CORS origins (empty disables CORS)",
    )
    cors_allow_credentials: bool = Field(default=False, description="Allow credentials for CORS requests")

    # Docs and proxy trust
    enable_api_docs: bool = Field(default=False, description="Enable OpenAPI docs endpoints")
    trusted_proxy_hosts: str = Field(
        default="",
        description="Comma-separated list of trusted proxy IPs/CIDRs for forwarded headers",
    )
    podcast_public_base_url: str = Field(
        default="",
        description=(
            "Public base URL used in podcast RSS links/enclosures "
            "(e.g. https://ghostwriter.example.com)"
        ),
    )

    # Rate limiting
    auth_rate_limit_enabled: bool = Field(default=True, description="Enable auth rate limiting")
    auth_rate_limit_max: int = Field(default=10, description="Max auth requests per window")
    auth_rate_limit_window_seconds: int = Field(default=60, description="Auth rate limit window (seconds)")

    # Paths
    data_dir: str = Field(default="/app/data", description="Database directory")
    output_dir: str = Field(default="/app/output", description="EPUB output directory")
    logs_dir: str = Field(default="/app/logs", description="Digest activity logs directory")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    def get_llm_model_string(self) -> str:
        """
        Get the LiteLLM model string based on the configured provider.

        Returns:
            The model string in LiteLLM format (e.g., 'gemini/gemini-1.5-flash').
        """
        if self.ai_provider == "openai":
            return self.openai_model
        elif self.ai_provider == "gemini":
            return f"gemini/{self.gemini_model}"
        elif self.ai_provider == "ollama":
            return f"ollama/{self.ollama_model}"
        else:
            raise ValueError(f"Unknown AI provider: {self.ai_provider}")

    def get_llm_api_key(self) -> str | None:
        """
        Get the API key for the configured provider.

        Returns:
            The API key or None for local providers.
        """
        if self.ai_provider == "openai":
            return self.openai_api_key or None
        elif self.ai_provider == "gemini":
            return self.gemini_api_key or None
        return None

    def get_llm_base_url(self) -> str | None:
        """
        Get the base URL for providers that need it (Ollama).

        Returns:
            The base URL or None.
        """
        if self.ai_provider == "ollama":
            return self.ollama_base_url
        return None


@lru_cache
def get_settings() -> Settings:
    """
    Get cached application settings.

    Returns:
        Singleton Settings instance.
    """
    return Settings()
