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

    SYSTEM_PROMPT = """You are a precise summarization engine for a daily reading digest.
Follow the instructions in <instructions> exactly.
Hard rules:
- Never mention sponsors, ads, promos, or that they were skipped.
- Do not output sponsor/ad/promo language, brand names, or CTA phrases.
- Use straight quotes only (no curly quotes). Apostrophes in contractions are OK.
- If you include exact excerpts, italicize them using single asterisks.
- Never output literal "Title:" or "Summary:" prefixes.
- Do not use emojis."""

    SUMMARIZE_PROMPT = """<instructions>
Summarize this article for a daily reading digest on an e-ink device.

Content guidance:
- Lead with the primary claim or most important finding.
- Include 2-3 key supporting facts, data points, or events.
- Preserve 1-2 short exact excerpts (max 25 words each) when there's a strong, memorable line. Italicize excerpts with *single asterisks*.
- Omit sponsor messages, ads, calls-to-action, and boilerplate. Do not mention or acknowledge them.

Length: Target around 800-1,200 characters. Use 2-3 short paragraphs.

Formatting:
- Write in direct, factual language with a neutral tone.
- Use short paragraphs. Bullet lists only when they improve scanability.
- Keep compact: no extra blank lines between sentences.
- Do not start with preambles like "Here's a summary" or "This article discusses".

Final check: Ensure no sponsor/ad content remains. Verify excerpts are italicized.
</instructions>

<context>
{context}
</context>

<content>
{content}
</content>"""

    CHUNK_SUMMARIZE_PROMPT = """<instructions>
You are summarizing part {part} of {total} of a long article or transcript.

Requirements:
- Extract only key facts, events, decisions, and notable quotes.
- Maximum 8 bullet points.
- Omit sponsor messages, ads, and boilerplate entirely.
- Keep it concise; avoid repetition.
</instructions>

<content>
{content}
</content>"""

    REDUCE_PROMPT = """<instructions>
Combine these partial summaries into one cohesive final summary.

Content guidance:
- Lead with the most important point across all sections.
- Synthesize related points; eliminate redundancy.
- Preserve any strong exact excerpts from the partials.

Length: Target around 800-1,200 characters. Use 2-3 short paragraphs.

Formatting:
- Write in direct, factual language with a neutral tone.
- Keep compact: no extra blank lines.
- Do not start with preambles like "Here's a summary".

Final check: Ensure the summary flows naturally and captures the full scope.
</instructions>

<content>
{content}
</content>"""

    SUMMARIZE_TRANSCRIPT_PROMPT = """<instructions>
Summarize this podcast or video transcript for a daily reading digest on an e-ink device.

Content guidance:
- Lead with a one-sentence overview of what this episode/video covers.
- Organize the summary by topics discussed, in the order they appear.
- For each major topic, include 2-3 key points, arguments, or findings.
- Preserve 2-4 short exact excerpts (max 25 words each) when there's a strong, memorable line. Italicize excerpts with *single asterisks*.
- Note any notable disagreements, surprising claims, or actionable advice.
- Omit sponsor messages, ads, calls-to-action, and boilerplate. Do not mention or acknowledge them.

Length: Target around 3,000-4,000 characters. Use 5-8 short paragraphs.

Formatting:
- Write in direct, factual language with a neutral tone.
- Use short paragraphs. Bullet lists only when they improve scanability.
- Keep compact: no extra blank lines between sentences.
- Do not start with preambles like "Here's a summary" or "In this episode".

Final check: Ensure no sponsor/ad content remains. Verify excerpts are italicized.
</instructions>

<context>
{context}
</context>

<content>
{content}
</content>"""

    CHUNK_SUMMARIZE_TRANSCRIPT_PROMPT = """<instructions>
You are summarizing part {part} of {total} of a long podcast or video transcript.

Requirements:
- Extract key topics discussed, arguments made, and notable quotes.
- Maximum 12 bullet points.
- Omit sponsor messages, ads, and boilerplate entirely.
- Keep it concise; avoid repetition.
</instructions>

<content>
{content}
</content>"""

    REDUCE_TRANSCRIPT_PROMPT = """<instructions>
Combine these partial summaries of a podcast or video transcript into one cohesive final summary.

Content guidance:
- Lead with a one-sentence overview of the episode/video.
- Organize by topics discussed, synthesizing related points across sections.
- For each major topic, include 2-3 key points or arguments.
- Preserve any strong exact excerpts from the partials.
- Note any notable disagreements, surprising claims, or actionable advice.

Length: Target around 3,000-4,000 characters. Use 5-8 short paragraphs.

Formatting:
- Write in direct, factual language with a neutral tone.
- Keep compact: no extra blank lines.
- Do not start with preambles like "Here's a summary".

Final check: Ensure the summary flows naturally and captures the full scope of the discussion.
</instructions>

<content>
{content}
</content>"""

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
        self,
        content: str,
        retries: int | None = None,
        *,
        title: str | None = None,
        url: str | None = None,
        author: str | None = None,
        source: str | None = None,
        content_type: str = "article",
    ) -> tuple[str, bool]:
        """
        Summarize article content using the configured LLM.

        Implements retry logic with exponential backoff. Falls back to
        returning the original content if all retries fail.

        Args:
            content: The article content to summarize.
            retries: Number of retries (defaults to settings.ai_max_retries).
            title: Article title for context.
            url: Source URL for context.
            author: Author name for context.
            source: Source name (feed title, "Newsletter", etc.) for context.
            content_type: "article" or "transcript" — selects prompt style.

        Returns:
            Tuple of (summarized_content, ai_failed).
            ai_failed is True if we fell back to raw content.
        """
        if retries is None:
            retries = self.settings.ai_max_retries

        # Select prompts based on content type
        if content_type == "transcript":
            summarize_prompt = self.SUMMARIZE_TRANSCRIPT_PROMPT
            chunk_prompt = self.CHUNK_SUMMARIZE_TRANSCRIPT_PROMPT
            reduce_prompt_template = self.REDUCE_TRANSCRIPT_PROMPT
        else:
            summarize_prompt = self.SUMMARIZE_PROMPT
            chunk_prompt = self.CHUNK_SUMMARIZE_PROMPT
            reduce_prompt_template = self.REDUCE_PROMPT

        # Build context from metadata
        context_lines = []
        if title:
            context_lines.append(f"Title: {title}")
        if source:
            context_lines.append(f"Source: {source}")
        if author:
            context_lines.append(f"Author: {author}")
        if url:
            context_lines.append(f"URL: {url}")
        context = "\n".join(context_lines) if context_lines else "No metadata available."

        model = self.settings.get_llm_model_string()
        if len(content) <= self.DIRECT_SUMMARY_CHAR_LIMIT:
            prompt = summarize_prompt.format(context=context, content=content)
            direct_summary, direct_failed = await self._run_completion(
                prompt, model, retries, system_prompt=self.SYSTEM_PROMPT
            )
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
            prompt = chunk_prompt.format(
                part=index,
                total=total,
                content=chunk,
            )
            partial_summary, partial_failed = await self._run_completion(
                prompt, model, retries, system_prompt=self.SYSTEM_PROMPT
            )
            if partial_failed:
                return content, True
            partials.append(partial_summary)

        reduce_input = "\n\n".join(partials)
        reduce_prompt = reduce_prompt_template.format(content=reduce_input)
        final_summary, final_failed = await self._run_completion(
            reduce_prompt, model, retries, system_prompt=self.SYSTEM_PROMPT
        )
        if final_failed:
            return content, True
        return final_summary, False

    async def _run_completion(
        self,
        prompt: str,
        model: str,
        retries: int,
        *,
        system_prompt: str | None = None,
    ) -> tuple[str, bool]:
        """Run one LLM completion with retries, returning (output, failed)."""
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
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
