"""YouTube transcript extraction: captions first, audio transcription fallback."""

from __future__ import annotations

import asyncio
import logging
import re
import tempfile
from dataclasses import dataclass

from app.core.config import Settings, get_settings
from app.services.transcription_service import TranscriptionService

logger = logging.getLogger(__name__)

_YOUTUBE_PATTERNS = [
    re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/watch\?v=(?P<id>[a-zA-Z0-9_-]{11})"),
    re.compile(r"(?:https?://)?youtu\.be/(?P<id>[a-zA-Z0-9_-]{11})"),
    re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/shorts/(?P<id>[a-zA-Z0-9_-]{11})"),
    re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/embed/(?P<id>[a-zA-Z0-9_-]{11})"),
    re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/live/(?P<id>[a-zA-Z0-9_-]{11})"),
]


@dataclass
class YouTubeResult:
    """Result of a YouTube transcript extraction."""

    text: str
    source: str  # "captions" | "audio_transcription"
    error: str | None = None


class YouTubeService:
    """Extract transcripts from YouTube videos."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.transcription_service = TranscriptionService(self.settings)

    @staticmethod
    def is_youtube_url(url: str) -> bool:
        """Check if a URL is a YouTube video URL."""
        return any(pattern.search(url) for pattern in _YOUTUBE_PATTERNS)

    @staticmethod
    def extract_video_id(url: str) -> str | None:
        """Extract the 11-character video ID from a YouTube URL."""
        for pattern in _YOUTUBE_PATTERNS:
            match = pattern.search(url)
            if match:
                return match.group("id")
        return None

    async def _get_captions(self, video_id: str) -> str | None:
        """Try to fetch captions using youtube-transcript-api."""
        try:
            from youtube_transcript_api import YouTubeTranscriptApi

            ytt_api = YouTubeTranscriptApi()

            # Run in thread pool since the library is synchronous
            loop = asyncio.get_event_loop()

            # Try manual English, then auto English, then any language
            try:
                transcript = await loop.run_in_executor(
                    None,
                    lambda: ytt_api.fetch(video_id, languages=["en"]),
                )
            except Exception:
                try:
                    transcript = await loop.run_in_executor(
                        None,
                        lambda: ytt_api.fetch(video_id, languages=["en"]),
                    )
                except Exception:
                    # Try any available language
                    transcript_list = await loop.run_in_executor(
                        None,
                        lambda: ytt_api.list(video_id),
                    )
                    if not transcript_list:
                        return None
                    # Get the first available transcript
                    first = transcript_list[0]
                    transcript = await loop.run_in_executor(
                        None,
                        lambda: first.fetch(),
                    )

            if not transcript:
                return None

            # Join all caption segments
            text = " ".join(
                entry.text for entry in transcript
                if hasattr(entry, "text")
            )
            return text.strip() if text.strip() else None

        except ImportError:
            logger.warning("youtube-transcript-api not installed")
            return None
        except Exception as e:
            logger.warning("Caption fetch failed for %s: %s", video_id, e)
            return None

    async def _transcribe_audio(
        self, url: str, whisper_provider: str, whisper_model: str,
        timeout_seconds: int | None = None,
    ) -> YouTubeResult:
        """Download audio with yt-dlp and transcribe."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = f"{tmpdir}/audio.wav"
            cmd = [
                "yt-dlp",
                "-x",
                "--audio-format", "wav",
                "--postprocessor-args", "ffmpeg:-ar 16000 -ac 1",
                "-o", output_path,
                "--no-playlist",
                url,
            ]

            logger.info("Downloading YouTube audio: %s", url)
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                _, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=120
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.communicate()
                return YouTubeResult(
                    text="", source="audio_transcription",
                    error="yt-dlp timed out after 120s",
                )

            if process.returncode != 0:
                err = stderr.decode("utf-8", errors="ignore").strip()
                return YouTubeResult(
                    text="", source="audio_transcription",
                    error=f"yt-dlp failed: {err[:300]}",
                )

            # yt-dlp may append a different extension; find the file
            import glob
            wav_files = glob.glob(f"{tmpdir}/audio*")
            if not wav_files:
                return YouTubeResult(
                    text="", source="audio_transcription",
                    error="yt-dlp produced no output file",
                )

            result = await self.transcription_service.transcribe(
                wav_files[0], provider=whisper_provider, whisper_model=whisper_model,
                timeout_seconds=timeout_seconds,
            )
            if result.error:
                return YouTubeResult(
                    text="", source="audio_transcription", error=result.error
                )
            return YouTubeResult(text=result.text, source="audio_transcription")

    async def get_transcript(
        self,
        url: str,
        whisper_provider: str = "local",
        whisper_model: str = "base.en",
        timeout_seconds: int | None = None,
    ) -> YouTubeResult:
        """
        Get transcript for a YouTube video.

        Strategy:
        1. Try fetching captions via youtube-transcript-api
        2. On failure: download audio via yt-dlp and transcribe

        Args:
            url: YouTube video URL.
            whisper_provider: "local", "openai", or "auto" for audio fallback.
            whisper_model: whisper.cpp model name for local transcription.

        Returns:
            YouTubeResult with transcript text or error.
        """
        video_id = self.extract_video_id(url)
        if not video_id:
            return YouTubeResult(
                text="", source="captions",
                error=f"Could not extract video ID from: {url}",
            )

        # Try captions first
        captions = await self._get_captions(video_id)
        if captions:
            logger.info("Got YouTube captions for %s (%d words)", video_id, len(captions.split()))
            return YouTubeResult(text=captions, source="captions")

        # Fall back to audio transcription
        logger.info("No captions available for %s, falling back to audio transcription", video_id)
        return await self._transcribe_audio(url, whisper_provider, whisper_model, timeout_seconds)
