"""Media processor: routes URLs to YouTube or audio transcription services."""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from dataclasses import dataclass

import httpx

from app.core.config import Settings, get_settings
from app.services.transcription_service import TranscriptionService
from app.services.youtube_service import YouTubeService

logger = logging.getLogger(__name__)

_AUDIO_EXTENSIONS = frozenset({
    ".mp3", ".m4a", ".ogg", ".opus", ".wav", ".flac", ".aac", ".wma",
})


@dataclass
class MediaResult:
    """Result of media processing."""

    text: str
    source: str  # "youtube_captions" | "youtube_audio" | "podcast_audio" | "not_media"
    is_media: bool
    error: str | None = None


class MediaProcessor:
    """Orchestrator for media content extraction (YouTube, podcasts)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.youtube_service = YouTubeService(self.settings)
        self.transcription_service = TranscriptionService(self.settings)

    @staticmethod
    def quick_check(url: str, content_url: str | None = None) -> bool:
        """
        Quickly determine if a URL is a media source (YouTube or podcast audio)
        without performing any processing.

        Args:
            url: The article/page URL.
            content_url: Optional enclosure URL (e.g., podcast audio).

        Returns:
            True if the URL is a media source that should be handled by
            the media pipeline instead of inline extraction.
        """
        if YouTubeService.is_youtube_url(url):
            return True
        if MediaProcessor._is_audio_url(content_url):
            return True
        return False

    @staticmethod
    def _is_audio_url(url: str | None) -> bool:
        """Check if a URL points to an audio file."""
        if not url:
            return False
        # Strip query params for extension check
        path = url.split("?")[0].split("#")[0]
        _, ext = os.path.splitext(path)
        return ext.lower() in _AUDIO_EXTENSIONS

    async def process(
        self,
        url: str,
        content_url: str | None = None,
        whisper_provider: str = "local",
        whisper_model: str = "base.en",
        timeout_seconds: int | None = None,
    ) -> MediaResult:
        """
        Process a URL for media content.

        Args:
            url: The article/page URL.
            content_url: Optional enclosure URL (e.g., podcast audio).
            whisper_provider: "local", "openai", or "auto".
            whisper_model: whisper.cpp model name for local transcription.

        Returns:
            MediaResult. If is_media is False, the caller should use
            trafilatura for standard article extraction.
        """
        # Check YouTube first
        if YouTubeService.is_youtube_url(url):
            logger.info("YouTube URL detected: %s", url)
            result = await self.youtube_service.get_transcript(
                url, whisper_provider, whisper_model, timeout_seconds
            )
            source = f"youtube_{result.source}"
            return MediaResult(
                text=result.text,
                source=source,
                is_media=True,
                error=result.error,
            )

        # Check for audio enclosure
        if self._is_audio_url(content_url):
            logger.info("Audio enclosure detected: %s", content_url)
            return await self._process_audio(
                content_url, whisper_provider, whisper_model, timeout_seconds
            )

        # Not media — caller should use trafilatura
        return MediaResult(text="", source="not_media", is_media=False)

    async def _process_audio(
        self,
        audio_url: str,
        whisper_provider: str,
        whisper_model: str,
        timeout_seconds: int | None = None,
    ) -> MediaResult:
        """Download and transcribe a podcast/audio URL."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Download the audio file
            download_path = os.path.join(tmpdir, "audio_download")
            try:
                async with httpx.AsyncClient(
                    follow_redirects=True, timeout=120
                ) as client:
                    async with client.stream("GET", audio_url) as response:
                        if response.status_code != 200:
                            return MediaResult(
                                text="", source="podcast_audio", is_media=True,
                                error=f"Audio download failed: HTTP {response.status_code}",
                            )
                        with open(download_path, "wb") as f:
                            async for chunk in response.aiter_bytes(chunk_size=65536):
                                f.write(chunk)
            except Exception as e:
                return MediaResult(
                    text="", source="podcast_audio", is_media=True,
                    error=f"Audio download failed: {e!r}",
                )

            # Convert to WAV with ffmpeg
            wav_path = os.path.join(tmpdir, "audio.wav")
            cmd = [
                "ffmpeg", "-i", download_path,
                "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
                wav_path,
                "-y", "-loglevel", "error",
            ]
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await process.communicate()
            if process.returncode != 0:
                return MediaResult(
                    text="", source="podcast_audio", is_media=True,
                    error=f"ffmpeg conversion failed: {stderr.decode()[:300]}",
                )

            # Transcribe
            result = await self.transcription_service.transcribe(
                wav_path, provider=whisper_provider, whisper_model=whisper_model,
                timeout_seconds=timeout_seconds,
            )
            if result.error:
                return MediaResult(
                    text="", source="podcast_audio", is_media=True,
                    error=result.error,
                )
            return MediaResult(
                text=result.text, source="podcast_audio", is_media=True
            )
