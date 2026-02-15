"""AI cover image generation service."""

import base64
from dataclasses import dataclass
from datetime import datetime
import io
import logging

import httpx
from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError

from app.core.config import Settings, get_settings
from app.services.content_processor import ExtractedArticle

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CoverImage:
    """Binary image payload ready to embed in the EPUB."""

    data: bytes
    media_type: str
    provider: str


@dataclass(frozen=True)
class CoverOverlayMetadata:
    """Deterministic text metadata rendered onto generated cover art."""

    title: str
    subtitle: str
    sources: tuple[str, ...]


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
    _OVERLAY_MARGIN = 40
    _OVERLAY_TOP_PANEL_HEIGHT = 210
    _OVERLAY_BOTTOM_PANEL_HEIGHT = 170
    _OVERLAY_CORNER_RADIUS = 24
    _OVERLAY_BACKGROUND_RGBA = (255, 255, 255, 220)
    _OVERLAY_TEXT_RGBA = (0, 0, 0, 255)
    _SOURCE_LABEL_ORDER = ("News", "Wallabag", "Newsletter", "Podcast", "YouTube")
    _COVER_TITLE = "Epilogue Digest"

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
        overlay_enabled: bool = True,
        cover_openai_api_key: str | None = None,
        cover_gemini_api_key: str | None = None,
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
            raw_cover = await self._generate_openai(
                prompt=prompt,
                quality=normalized_quality,
                api_key_override=cover_openai_api_key,
            )
        elif provider == "nano-banana":
            raw_cover = await self._generate_nano_banana(
                prompt=prompt,
                api_key_override=cover_gemini_api_key,
            )
        else:
            logger.warning("Unsupported cover provider: %s", provider)
            return None

        if raw_cover is None:
            return None

        overlay_metadata: CoverOverlayMetadata | None = None
        if overlay_enabled:
            overlay_metadata = self._build_overlay_metadata(
                period=period,
                date=date,
                articles=articles,
            )
        normalized_cover = self._normalize_cover_image(raw_cover, overlay_metadata=overlay_metadata)
        if normalized_cover is None:
            logger.warning(
                "Generated cover could not be normalized; skipping AI cover embedding",
            )
            return None
        return normalized_cover

    def normalize_for_epub(
        self,
        *,
        data: bytes,
        media_type: str,
        provider: str = "manual",
    ) -> CoverImage | None:
        """Normalize arbitrary image bytes to EPUB-safe 5:8 JPEG."""
        return self._normalize_cover_image(
            CoverImage(data=data, media_type=media_type, provider=provider)
        )

    @staticmethod
    def extension_for_media_type(media_type: str) -> str:
        """Map media type to conventional file extension."""
        if media_type == "image/jpeg":
            return "jpg"
        if media_type == "image/webp":
            return "webp"
        if media_type == "image/gif":
            return "gif"
        return "png"

    def _build_prompt(
        self,
        *,
        period: str,
        date: datetime,
        articles: list[ExtractedArticle],
        prompt_suffix: str,
    ) -> str:
        """Build a content-rich prompt from digest metadata."""
        # Group articles by feed, keeping up to 3 per feed
        feed_groups: dict[str, list[ExtractedArticle]] = {}
        for article in articles:
            feed_title = (article.feed_title or "General").strip()
            if feed_title not in feed_groups:
                feed_groups[feed_title] = []
            if len(feed_groups[feed_title]) < 3:
                feed_groups[feed_title].append(article)

        # Build detailed article metadata lines
        article_details: list[str] = []
        for feed_title, feed_articles in feed_groups.items():
            for article in feed_articles:
                title = article.title.strip() if article.title else "Untitled"
                author = article.author.strip() if article.author else None

                # Identify content type
                content_type = (article.content_type or "article").strip().lower()
                feed_lower = feed_title.lower()

                if content_type == "podcast":
                    type_label = "[Podcast]"
                elif content_type == "youtube":
                    type_label = "[YouTube]"
                elif feed_lower == "wallabag":
                    type_label = "[Wallabag]"
                elif feed_lower == "newsletter":
                    type_label = "[Newsletter]"
                else:
                    type_label = ""

                # Format: "[Type] Title - Author (Feed)"
                detail_parts = []
                if type_label:
                    detail_parts.append(type_label)
                detail_parts.append(title)
                if author:
                    detail_parts.append(f"by {author}")
                if type_label:
                    # For special types, include type in detail
                    detail = " ".join(detail_parts)
                else:
                    # For regular articles, include feed source
                    detail = f"{' '.join(detail_parts)} ({feed_title})"

                article_details.append(detail)

                # Limit total articles in prompt to avoid token bloat
                if len(article_details) >= 15:
                    break
            if len(article_details) >= 15:
                break

        date_label = date.strftime("%Y-%m-%d")
        period_label = period.capitalize()
        source_mix = ", ".join(self._extract_source_labels(articles))
        content_summary = "; ".join(article_details) if article_details else "Mixed content"

        base_prompt = (
            f"Create a magazine-style cover illustration for a news digest edition. "
            f"High contrast, clean composition, no logos, no watermarks, no UI elements. "
            f"Include the digest title prominently at the top: \"{date_label} - {period_label}\". "
            f"Visual style: editorial magazine art, minimalist, monochrome-friendly. "
            f"Compose for a 5:8 portrait book-cover ratio. "
            f"Content types: {source_mix}. "
            f"Articles included: {content_summary}"
        )
        if prompt_suffix.strip():
            base_prompt = f"{base_prompt}. Additional direction: {prompt_suffix.strip()}"
        return base_prompt

    def _extract_source_labels(self, articles: list[ExtractedArticle]) -> list[str]:
        """Resolve deterministic source labels from digest article mix."""
        seen: set[str] = set()
        for article in articles:
            content_type = (article.content_type or "article").strip().lower()
            feed_title = (article.feed_title or "").strip().lower()

            if content_type == "podcast":
                seen.add("Podcast")
                continue
            if content_type == "youtube":
                seen.add("YouTube")
                continue
            if feed_title == "wallabag":
                seen.add("Wallabag")
                continue
            if feed_title == "newsletter":
                seen.add("Newsletter")
                continue
            seen.add("News")

        if not seen:
            seen.add("News")

        return [label for label in self._SOURCE_LABEL_ORDER if label in seen]

    def _build_overlay_metadata(
        self,
        *,
        period: str,
        date: datetime,
        articles: list[ExtractedArticle],
    ) -> CoverOverlayMetadata:
        """Construct deterministic cover text based on digest metadata."""
        subtitle = f"{date.strftime('%Y-%m-%d')} · {period.capitalize()}"
        sources = tuple(self._extract_source_labels(articles))
        return CoverOverlayMetadata(
            title=self._COVER_TITLE,
            subtitle=subtitle,
            sources=sources,
        )

    async def _generate_openai(
        self,
        *,
        prompt: str,
        quality: str,
        api_key_override: str | None = None,
    ) -> CoverImage | None:
        api_key = (api_key_override or self.settings.openai_api_key).strip()
        if not api_key:
            logger.warning(
                "Cover generation skipped: no cover OpenAI key configured "
                "(Covers setting or OPENAI_API_KEY)",
            )
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
        except httpx.HTTPStatusError as exc:
            response_excerpt = exc.response.text.strip().replace("\n", " ")
            if len(response_excerpt) > 500:
                response_excerpt = f"{response_excerpt[:500]}..."
            logger.warning(
                "OpenAI cover generation failed with status %s: %s",
                exc.response.status_code,
                response_excerpt or "<empty body>",
            )
            return None
        except httpx.RequestError:
            logger.exception("OpenAI cover generation request error")
            return None
        except Exception:
            logger.exception("OpenAI cover generation failed")
            return None

        logger.warning("OpenAI image response did not include image bytes")
        return None

    async def _generate_nano_banana(
        self,
        *,
        prompt: str,
        api_key_override: str | None = None,
    ) -> CoverImage | None:
        api_key = (api_key_override or self.settings.gemini_api_key).strip()
        if not api_key:
            logger.warning(
                "Cover generation skipped: no cover Gemini key configured "
                "(Covers setting or GEMINI_API_KEY)",
            )
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

    def _normalize_cover_image(
        self,
        cover: CoverImage,
        overlay_metadata: CoverOverlayMetadata | None = None,
    ) -> CoverImage | None:
        """Normalize generated images to a compact 5:8 JPEG cover."""
        try:
            with Image.open(io.BytesIO(cover.data)) as source:
                image = source.convert("RGB")
                cropped = self._center_crop_to_ratio(image, self._TARGET_RATIO)
                resized = cropped.resize(
                    (self._TARGET_WIDTH, self._TARGET_HEIGHT),
                    Image.Resampling.LANCZOS,
                )
                finalized = resized
                if overlay_metadata:
                    finalized = self._apply_metadata_overlay(resized, overlay_metadata)
                with io.BytesIO() as output:
                    encoded: bytes | None = None
                    for quality in self._JPEG_QUALITY_CANDIDATES:
                        output.seek(0)
                        output.truncate(0)
                        finalized.save(
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

    def _apply_metadata_overlay(
        self,
        image: Image.Image,
        metadata: CoverOverlayMetadata,
    ) -> Image.Image:
        """Render deterministic title/date/source metadata over generated art."""
        composed = image.convert("RGBA")
        draw = ImageDraw.Draw(composed, "RGBA")
        width, height = composed.size
        margin = self._OVERLAY_MARGIN

        top_panel = (
            margin,
            margin,
            width - margin,
            margin + self._OVERLAY_TOP_PANEL_HEIGHT,
        )
        bottom_panel = (
            margin,
            height - margin - self._OVERLAY_BOTTOM_PANEL_HEIGHT,
            width - margin,
            height - margin,
        )

        draw.rounded_rectangle(
            top_panel,
            radius=self._OVERLAY_CORNER_RADIUS,
            fill=self._OVERLAY_BACKGROUND_RGBA,
        )
        draw.rounded_rectangle(
            bottom_panel,
            radius=self._OVERLAY_CORNER_RADIUS,
            fill=self._OVERLAY_BACKGROUND_RGBA,
        )

        text_width = (width - (2 * margin)) - 44
        title_font = self._fit_default_font(draw, metadata.title, text_width, start_size=64, min_size=40)
        subtitle_font = self._fit_default_font(draw, metadata.subtitle, text_width, start_size=36, min_size=24)
        sources_line = "Sources: " + " • ".join(metadata.sources)
        sources_font = self._fit_default_font(draw, sources_line, text_width, start_size=30, min_size=20)

        draw.text(
            (margin + 22, margin + 24),
            metadata.title,
            fill=self._OVERLAY_TEXT_RGBA,
            font=title_font,
        )
        draw.text(
            (margin + 22, margin + 120),
            metadata.subtitle,
            fill=self._OVERLAY_TEXT_RGBA,
            font=subtitle_font,
        )
        draw.text(
            (margin + 22, height - margin - self._OVERLAY_BOTTOM_PANEL_HEIGHT + 62),
            sources_line,
            fill=self._OVERLAY_TEXT_RGBA,
            font=sources_font,
        )

        return composed.convert("RGB")

    @staticmethod
    def _fit_default_font(
        draw: ImageDraw.ImageDraw,
        text: str,
        max_width: int,
        *,
        start_size: int,
        min_size: int,
    ) -> ImageFont.ImageFont:
        """Choose the largest default Pillow font size that fits max width."""
        for size in range(start_size, min_size - 1, -2):
            font = ImageFont.load_default(size=size)
            left, _, right, _ = draw.textbbox((0, 0), text, font=font)
            if right - left <= max_width:
                return font
        return ImageFont.load_default(size=min_size)

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
