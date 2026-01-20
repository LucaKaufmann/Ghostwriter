"""LLM Service with provider-agnostic abstraction via LiteLLM."""

import asyncio
import logging
from typing import Any

import litellm
from litellm import acompletion

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class LLMService:
    """
    Provider-agnostic LLM service using LiteLLM.

    Supports OpenAI, Google Gemini, and Ollama through a unified interface.
    Implements retry logic with fallback to raw text on failure.
    """

    SUMMARIZE_PROMPT = """You are a concise news editor. Summarize the following article for a daily digest.

Requirements:
- Focus on key facts and main points
- Use neutral, informative tone
- Maximum 3 paragraphs
- Do not include any preamble like "Here's a summary"

Article:
{content}"""

    def __init__(self, settings: Settings | None = None) -> None:
        """
        Initialize the LLM service.

        Args:
            settings: Application settings. Uses default if not provided.
        """
        self.settings = settings or get_settings()
        self._configure_litellm()

    def _configure_litellm(self) -> None:
        """Configure LiteLLM based on the selected provider."""
        # Set API keys based on provider
        if self.settings.ai_provider == "openai" and self.settings.openai_api_key:
            litellm.openai_key = self.settings.openai_api_key
        elif self.settings.ai_provider == "gemini" and self.settings.gemini_api_key:
            litellm.gemini_key = self.settings.gemini_api_key

        # Disable telemetry
        litellm.telemetry = False

        # Set timeout
        litellm.request_timeout = self.settings.ai_timeout_seconds

    async def summarize(
        self, content: str, retries: int | None = None
    ) -> tuple[str, bool]:
        """
        Summarize article content using the configured LLM.

        Implements retry logic with exponential backoff. Falls back to
        returning the original content if all retries fail.

        Args:
            content: The article content to summarize.
            retries: Number of retries (defaults to settings.ai_max_retries).

        Returns:
            Tuple of (summarized_content, ai_failed).
            ai_failed is True if we fell back to raw content.
        """
        if retries is None:
            retries = self.settings.ai_max_retries

        model = self.settings.get_llm_model_string()
        prompt = self.SUMMARIZE_PROMPT.format(content=content[:15000])  # Truncate long content

        # Build kwargs for LiteLLM
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "timeout": self.settings.ai_timeout_seconds,
        }

        # Add provider-specific config
        if self.settings.ai_provider == "ollama":
            kwargs["api_base"] = self.settings.ollama_base_url
        elif self.settings.ai_provider == "gemini":
            kwargs["api_key"] = self.settings.gemini_api_key
        elif self.settings.ai_provider == "openai":
            kwargs["api_key"] = self.settings.openai_api_key

        last_error: Exception | None = None

        for attempt in range(retries + 1):
            try:
                logger.debug(
                    f"LLM summarize attempt {attempt + 1}/{retries + 1} with model {model}"
                )

                response = await acompletion(**kwargs)
                summary = response.choices[0].message.content

                if summary:
                    logger.info(f"Successfully summarized content with {model}")
                    return summary.strip(), False

                logger.warning("Empty response from LLM, retrying...")

            except Exception as e:
                last_error = e
                logger.warning(
                    f"LLM summarize attempt {attempt + 1} failed: {e}"
                )

                if attempt < retries:
                    # Exponential backoff: 1s, 2s, 4s...
                    wait_time = 2**attempt
                    logger.debug(f"Waiting {wait_time}s before retry...")
                    await asyncio.sleep(wait_time)

        # All retries failed - fall back to raw content
        logger.error(
            f"All LLM summarize attempts failed. Last error: {last_error}. "
            "Falling back to raw content."
        )
        return content, True

    async def health_check(self) -> dict[str, Any]:
        """
        Check if the LLM service is healthy.

        Returns:
            Dict with provider, model, and status.
        """
        model = self.settings.get_llm_model_string()

        try:
            # Simple test completion
            kwargs: dict[str, Any] = {
                "model": model,
                "messages": [{"role": "user", "content": "Say 'OK'"}],
                "timeout": 10,
                "max_tokens": 5,
            }

            if self.settings.ai_provider == "ollama":
                kwargs["api_base"] = self.settings.ollama_base_url
            elif self.settings.ai_provider == "gemini":
                kwargs["api_key"] = self.settings.gemini_api_key
            elif self.settings.ai_provider == "openai":
                kwargs["api_key"] = self.settings.openai_api_key

            await acompletion(**kwargs)

            return {
                "provider": self.settings.ai_provider,
                "model": model,
                "status": "healthy",
            }
        except Exception as e:
            logger.error(f"LLM health check failed: {e}")
            return {
                "provider": self.settings.ai_provider,
                "model": model,
                "status": "unhealthy",
                "error": str(e),
            }
