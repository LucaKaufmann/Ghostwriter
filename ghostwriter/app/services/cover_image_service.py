"""AI cover image generation service."""

import base64
from dataclasses import dataclass
from datetime import datetime
import io
import logging

import httpx
from PIL import Image, UnidentifiedImageError

from app.core.config import Settings, get_settings
from app.services.content_processor import ExtractedArticle

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CoverImage:
    """Binary image payload ready to embed in the EPUB."""

    data: bytes
    media_type: str
    provider: str


class CoverImageService:
    """Generate digest cover images using configured external providers."""

    _OPENAI_ENDPOINT = "https://api.openai.com/v1/images/generations"
    _GEMINI_MODEL = "gemini-2.5-flash-image"
    _GEMINI_ENDPOINT = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{_GEMINI_MODEL}:generateContent"
    )
    _OPENAI_QUALITY_VALUES = {"low", "medium", "high"}
    _TARGET_WIDTH = 960
    _TARGET_HEIGHT = 1536
    _TARGET_RATIO = _TARGET_WIDTH / _TARGET_HEIGHT
    _JPEG_QUALITY_CANDIDATES = (80, 75, 70, 65)
    _MAX_OUTPUT_BYTES = 500 * 1024

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def generate_cover(
        self,
        *,
        period: str,
        date: datetime,
        articles: list[ExtractedArticle],
        provider: str,
        quality: str,
        prompt_suffix: str = "",
    ) -> CoverImage | None:
        """Generate a cover image for a digest."""
        prompt = self._build_prompt(
            period=period,
            date=date,
            articles=articles,
            prompt_suffix=prompt_suffix,
        )

        raw_cover: CoverImage | None = None
        if provider == "gpt-image-1":
            normalized_quality = quality if quality in self._OPENAI_QUALITY_VALUES else "low"
            raw_cover = await self._generate_openai(prompt=prompt, quality=normalized_quality)
        elif provider == "nano-banana":
            raw_cover = await self._generate_nano_banana(prompt=prompt)
        else:
            logger.warning("Unsupported cover provider: %s", provider)
            return None

        if raw_cover is None:
            return None

        normalized_cover = self._normalize_cover_image(raw_cover)
        if normalized_cover is None:
            logger.warning(
                "Generated cover could not be normalized; skipping AI cover embedding",
            )
            return None
        return normalized_cover

    def _build_prompt(
        self,
        *,
        period: str,
        date: datetime,
        articles: list[ExtractedArticle],
        prompt_suffix: str,
    ) -> str:
        """Build a concise, high-signal prompt from digest metadata."""
        feed_titles: list[str] = []
        seen_feeds: set[str] = set()
        for article in articles:
            feed_title = (article.feed_title or "").strip()
            if not feed_title:
                continue
            lowered = feed_title.lower()
            if lowered in seen_feeds:
                continue
            seen_feeds.add(lowered)
            feed_titles.append(feed_title)
            if len(feed_titles) >= 6:
                break

        article_titles = [
            a.title.strip()
            for a in articles
            if a.title.strip()
        ][:8]

        date_label = date.strftime("%Y-%m-%d")
        period_label = period.capitalize()
        feeds_line = ", ".join(feed_titles) if feed_titles else "General news"
        headlines_line = "; ".join(article_titles) if article_titles else "No headline list available"

        base_prompt = (
            "Create an original portrait ebook cover illustration for an e-ink digest. "
            "High contrast, clean composition, no text, no letters, no logos, no watermarks, "
            "no UI elements. Visual style: editorial, minimalist, monochrome-friendly. "
            "Compose for a 5:8 portrait book-cover ratio. "
            f"Digest date: {date_label}. Edition: {period_label}. "
            f"Primary sources/topics: {feeds_line}. "
            f"Headline themes: {headlines_line}."
        )
        if prompt_suffix.strip():
            base_prompt = f"{base_prompt} Additional direction: {prompt_suffix.strip()}."
        return base_prompt

    async def _generate_openai(self, *, prompt: str, quality: str) -> CoverImage | None:
        api_key = self.settings.openai_api_key.strip()
        if not api_key:
            logger.warning("Cover generation skipped: OPENAI_API_KEY is not configured")
            return None

        timeout = httpx.Timeout(self.settings.cover_generation_timeout_seconds)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "gpt-image-1",
            "prompt": prompt,
            "size": "1024x1536",
            "quality": quality,
            "response_format": "b64_json",
        }

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    self._OPENAI_ENDPOINT,
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                image_data = data.get("data", [])
                if not image_data:
                    logger.warning("OpenAI image API returned no images")
                    return None

                first = image_data[0]
                b64_json = first.get("b64_json")
                if b64_json:
                    return CoverImage(
                        data=base64.b64decode(b64_json),
                        media_type="image/png",
                        provider="gpt-image-1",
                    )

                image_url = first.get("url")
                if image_url:
                    image_response = await client.get(image_url)
                    image_response.raise_for_status()
                    media_type = image_response.headers.get("content-type", "image/png").split(";")[0]
                    return CoverImage(
                        data=image_response.content,
                        media_type=media_type,
                        provider="gpt-image-1",
                    )
        except Exception:
            logger.exception("OpenAI cover generation failed")
            return None

        logger.warning("OpenAI image response did not include image bytes")
        return None

    async def _generate_nano_banana(self, *, prompt: str) -> CoverImage | None:
        api_key = self.settings.gemini_api_key.strip()
        if not api_key:
            logger.warning("Cover generation skipped: GEMINI_API_KEY is not configured")
            return None

        timeout = httpx.Timeout(self.settings.cover_generation_timeout_seconds)
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
        }

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    self._GEMINI_ENDPOINT,
                    params={"key": api_key},
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
        except Exception:
            logger.exception("Nano Banana cover generation failed")
            return None

        for candidate in data.get("candidates", []):
            content = candidate.get("content", {})
            for part in content.get("parts", []):
                inline_data = part.get("inlineData") or part.get("inline_data")
                if not inline_data:
                    continue
                encoded = inline_data.get("data")
                mime_type = inline_data.get("mimeType") or inline_data.get("mime_type") or "image/png"
                if not encoded:
                    continue
                try:
                    return CoverImage(
                        data=base64.b64decode(encoded),
                        media_type=mime_type,
                        provider="nano-banana",
                    )
                except Exception:
                    logger.exception("Failed to decode Nano Banana image payload")
                    return None

        logger.warning("Nano Banana response did not include an image part")
        return None

    def _normalize_cover_image(self, cover: CoverImage) -> CoverImage | None:
        """Normalize generated images to a compact 5:8 JPEG cover."""
        try:
            with Image.open(io.BytesIO(cover.data)) as source:
                image = source.convert("RGB")
                cropped = self._center_crop_to_ratio(image, self._TARGET_RATIO)
                resized = cropped.resize(
                    (self._TARGET_WIDTH, self._TARGET_HEIGHT),
                    Image.Resampling.LANCZOS,
                )
                with io.BytesIO() as output:
                    encoded: bytes | None = None
                    for quality in self._JPEG_QUALITY_CANDIDATES:
                        output.seek(0)
                        output.truncate(0)
                        resized.save(
                            output,
                            format="JPEG",
                            quality=quality,
                            optimize=True,
                        )
                        encoded = output.getvalue()
                        if len(encoded) <= self._MAX_OUTPUT_BYTES:
                            break
        except UnidentifiedImageError:
            logger.warning("Generated cover payload is not a valid image")
            return None
        except Exception:
            logger.exception("Failed to normalize generated cover image")
            return None

        if encoded is None:
            return None

        return CoverImage(
            data=encoded,
            media_type="image/jpeg",
            provider=cover.provider,
        )

    def _center_crop_to_ratio(self, image: Image.Image, ratio: float) -> Image.Image:
        """Center-crop image to target width/height ratio."""
        width, height = image.size
        if width <= 0 or height <= 0:
            return image

        current_ratio = width / height
        if current_ratio > ratio:
            target_width = max(1, int(height * ratio))
            left = (width - target_width) // 2
            return image.crop((left, 0, left + target_width, height))

        if current_ratio < ratio:
            target_height = max(1, int(width / ratio))
            top = (height - target_height) // 2
            return image.crop((0, top, width, top + target_height))

        return image
