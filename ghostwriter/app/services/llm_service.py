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

    CHUNK_SUMMARIZE_PROMPT = """You are a concise news editor. You are summarizing part {part}/{total} of a long article or transcript.

Requirements:
- Keep only key facts, events, and decisions
- Keep it concise and avoid repetition
- Maximum 8 bullet points

Content:
{content}"""

    REDUCE_PROMPT = """You are a concise news editor. Combine the following partial summaries into one final digest summary.

Requirements:
- Focus on key facts and main points
- Use neutral, informative tone
- Maximum 3 paragraphs
- Do not include any preamble like "Here's a summary"

Partial summaries:
{content}"""

    DIRECT_SUMMARY_CHAR_LIMIT = 15000
    CHUNK_CHAR_LIMIT = 12000

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
        if len(content) <= self.DIRECT_SUMMARY_CHAR_LIMIT:
            prompt = self.SUMMARIZE_PROMPT.format(content=content)
            direct_summary, direct_failed = await self._run_completion(prompt, model, retries)
            if direct_failed:
                return content, True
            return direct_summary, False

        chunks = self._chunk_text(content, self.CHUNK_CHAR_LIMIT)
        logger.info(
            "Using chunked LLM summarization",
            extra={"char_count": len(content), "chunks": len(chunks)},
        )

        partials: list[str] = []
        total = len(chunks)
        for index, chunk in enumerate(chunks, start=1):
            prompt = self.CHUNK_SUMMARIZE_PROMPT.format(
                part=index,
                total=total,
                content=chunk,
            )
            partial_summary, partial_failed = await self._run_completion(prompt, model, retries)
            if partial_failed:
                return content, True
            partials.append(partial_summary)

        reduce_input = "\n\n".join(partials)
        reduce_prompt = self.REDUCE_PROMPT.format(content=reduce_input)
        final_summary, final_failed = await self._run_completion(reduce_prompt, model, retries)
        if final_failed:
            return content, True
        return final_summary, False

    async def _run_completion(
        self, prompt: str, model: str, retries: int
    ) -> tuple[str, bool]:
        """Run one LLM completion with retries, returning (output, failed)."""
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "timeout": self.settings.ai_timeout_seconds,
        }

        if self.settings.ai_provider == "ollama":
            kwargs["api_base"] = self.settings.ollama_base_url
        elif self.settings.ai_provider == "gemini":
            kwargs["api_key"] = self.settings.gemini_api_key
        elif self.settings.ai_provider == "openai":
            kwargs["api_key"] = self.settings.openai_api_key

        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                logger.debug("LLM completion attempt %s/%s with model %s", attempt + 1, retries + 1, model)
                response = await acompletion(**kwargs)
                text = response.choices[0].message.content
                if text:
                    return text.strip(), False
                logger.warning("Empty response from LLM, retrying...")
            except Exception as e:
                last_error = e
                logger.warning(f"LLM summarize attempt {attempt + 1} failed: {e}")
                if attempt < retries:
                    await asyncio.sleep(2**attempt)

        logger.error(
            f"All LLM summarize attempts failed. Last error: {last_error}. "
            "Falling back to raw content."
        )
        return "", True

    @staticmethod
    def _chunk_text(text: str, chunk_size: int) -> list[str]:
        """Split long text into roughly chunk_size character chunks."""
        source = text.strip()
        if len(source) <= chunk_size:
            return [source]

        chunks: list[str] = []
        start = 0
        end_limit = len(source)
        while start < end_limit:
            end = min(start + chunk_size, end_limit)
            if end < end_limit:
                split = source.rfind("\n\n", start, end)
                if split <= start + chunk_size // 2:
                    split = source.rfind(". ", start, end)
                if split <= start + chunk_size // 2:
                    split = source.rfind(" ", start, end)
                if split > start:
                    end = split + 1
            chunk = source[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end <= start:
                end = min(start + chunk_size, end_limit)
            start = end

        return chunks

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
