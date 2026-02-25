"""LLM Service with provider-agnostic abstraction via LiteLLM."""

import asyncio
import logging
from datetime import datetime
from typing import Any
from uuid import uuid4

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
- Add chapter-like section headlines for major topic shifts.
- Preserve 2-4 short exact excerpts (max 25 words each) when there's a strong, memorable line. Italicize excerpts with *single asterisks*.
- Note any notable disagreements, surprising claims, or actionable advice.
- Omit sponsor messages, ads, calls-to-action, and boilerplate. Do not mention or acknowledge them.

Length: {length_guidance}

Formatting:
- Output in Markdown with:
  1) A short lead paragraph (no heading) as an overview.
  2) 3-8 section headings as Markdown H2 (`## Heading`) for major topics.
  3) 1-2 short paragraphs under each heading (2-4 sentences per paragraph).
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
- Include topic labels in bullets when possible so final reduce step can form section headings.
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

Length: {length_guidance}

Formatting:
- Output in Markdown with:
  1) A short lead paragraph (no heading) as an overview.
  2) 3-8 section headings as Markdown H2 (`## Heading`) for major topics.
  3) 1-2 short paragraphs under each heading (2-4 sentences per paragraph).
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
    _TRANSCRIPT_LENGTH_TIERS = (
        (2500, "Target around 350-500 words (~2,100-3,000 characters). Use 4-6 short paragraphs."),
        (7000, "Target around 500-750 words (~3,000-4,500 characters). Use 5-8 short paragraphs."),
        (14000, "Target around 750-1,050 words (~4,500-6,300 characters). Use 6-10 short paragraphs."),
        (
            float("inf"),
            "Target around 1,000-1,300 words (~6,000-7,800 characters). Use 8-12 short paragraphs.",
        ),
    )

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

        length_guidance = "Target around 800-1,200 characters. Use 2-3 short paragraphs."

        # Select prompts based on content type
        if content_type == "transcript":
            summarize_prompt = self.SUMMARIZE_TRANSCRIPT_PROMPT
            chunk_prompt = self.CHUNK_SUMMARIZE_TRANSCRIPT_PROMPT
            reduce_prompt_template = self.REDUCE_TRANSCRIPT_PROMPT
            length_guidance = self._transcript_length_guidance(content)
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
            prompt = summarize_prompt.format(
                context=context,
                content=content,
                length_guidance=length_guidance,
            )
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
        reduce_prompt = reduce_prompt_template.format(
            content=reduce_input,
            length_guidance=length_guidance,
        )
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
        timeout_seconds: int | None = None,
    ) -> tuple[str, bool]:
        """Run one LLM completion with retries, returning (output, failed)."""
        call_id = str(uuid4())
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "timeout": timeout_seconds or self.settings.ai_timeout_seconds,
        }

        if self.settings.ai_provider == "ollama":
            kwargs["api_base"] = self.settings.ollama_base_url
        elif self.settings.ai_provider == "gemini":
            kwargs["api_key"] = self.settings.gemini_api_key
        elif self.settings.ai_provider == "openai":
            kwargs["api_key"] = self.settings.openai_api_key

        logger.info(
            "LLM call started | call_id=%s provider=%s model=%s retries=%s prompt_chars=%s system_prompt_chars=%s timeout_seconds=%s started_at=%s",
            call_id,
            self.settings.ai_provider,
            model,
            retries,
            len(prompt),
            len(system_prompt or ""),
            timeout_seconds or self.settings.ai_timeout_seconds,
            datetime.utcnow().isoformat() + "Z",
        )
        logger.info(
            "LLM call prompt | call_id=%s system_prompt=%r user_prompt=%r",
            call_id,
            system_prompt or "",
            prompt,
        )

        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                logger.info(
                    "LLM attempt started | call_id=%s attempt=%s attempts_total=%s",
                    call_id,
                    attempt + 1,
                    retries + 1,
                )
                response = await acompletion(**kwargs)
                text = response.choices[0].message.content
                if text:
                    logger.info(
                        "LLM call succeeded | call_id=%s attempt=%s response_chars=%s",
                        call_id,
                        attempt + 1,
                        len(text.strip()),
                    )
                    return text.strip(), False
                logger.warning(
                    "LLM empty response | call_id=%s attempt=%s attempts_total=%s",
                    call_id,
                    attempt + 1,
                    retries + 1,
                )
            except Exception as e:
                last_error = e
                logger.error(
                    "LLM attempt failed | call_id=%s attempt=%s attempts_total=%s error_type=%s error=%s details=%s",
                    call_id,
                    attempt + 1,
                    retries + 1,
                    type(e).__name__,
                    str(e),
                    self._extract_error_details(e),
                    exc_info=True,
                )
                if attempt < retries:
                    await asyncio.sleep(2**attempt)

        logger.error(
            "LLM call failed after retries | call_id=%s provider=%s model=%s retries=%s last_error=%s. Falling back to raw content.",
            call_id,
            self.settings.ai_provider,
            model,
            retries,
            str(last_error),
        )
        return "", True

    @staticmethod
    def _extract_error_details(error: Exception) -> str:
        """Extract provider-specific error details when available for logs."""
        details: list[str] = []
        status_code = getattr(error, "status_code", None)
        if status_code is not None:
            details.append(f"status_code={status_code}")
        response = getattr(error, "response", None)
        if response is not None:
            response_text = getattr(response, "text", None)
            if response_text:
                details.append(f"response_text={response_text}")
            body = getattr(response, "content", None)
            if body:
                details.append(f"response_content={body}")
        if not details:
            return "none"
        return "; ".join(details)

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

    @classmethod
    def _transcript_length_guidance(cls, content: str) -> str:
        """Return transcript summary length target guidance based on source word count."""
        word_count = len(content.split())
        for max_words, guidance in cls._TRANSCRIPT_LENGTH_TIERS:
            if word_count <= max_words:
                return guidance
        return cls._TRANSCRIPT_LENGTH_TIERS[-1][1]

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
