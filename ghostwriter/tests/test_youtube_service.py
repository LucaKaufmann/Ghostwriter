"""Tests for YouTubeService."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.youtube_service import YouTubeService, YouTubeResult


@pytest.fixture
def settings():
    """Minimal settings mock."""
    s = MagicMock()
    s.whisper_cpp_binary = "/usr/local/bin/whisper-cli"
    s.whisper_models_dir = "/tmp/models"
    s.whisper_transcription_timeout_seconds = 300
    s.openai_whisper_timeout_seconds = 120
    s.openai_api_key = ""
    s.data_dir = "/app/data"
    return s


@pytest.fixture
def service(settings):
    return YouTubeService(settings)


class TestURLDetection:
    """Test YouTube URL pattern matching."""

    def test_standard_watch_url(self):
        assert YouTubeService.is_youtube_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    def test_short_url(self):
        assert YouTubeService.is_youtube_url("https://youtu.be/dQw4w9WgXcQ")

    def test_shorts_url(self):
        assert YouTubeService.is_youtube_url("https://www.youtube.com/shorts/dQw4w9WgXcQ")

    def test_embed_url(self):
        assert YouTubeService.is_youtube_url("https://www.youtube.com/embed/dQw4w9WgXcQ")

    def test_live_url(self):
        assert YouTubeService.is_youtube_url("https://www.youtube.com/live/dQw4w9WgXcQ")

    def test_non_youtube_url(self):
        assert not YouTubeService.is_youtube_url("https://example.com/video")

    def test_rss_feed_url(self):
        assert not YouTubeService.is_youtube_url("https://example.com/feed.xml")

    def test_no_protocol(self):
        assert YouTubeService.is_youtube_url("youtube.com/watch?v=dQw4w9WgXcQ")


class TestVideoIDExtraction:
    """Test video ID extraction."""

    def test_standard_url(self):
        assert YouTubeService.extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_short_url(self):
        assert YouTubeService.extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_invalid_url(self):
        assert YouTubeService.extract_video_id("https://example.com") is None


@pytest.mark.asyncio
async def test_get_transcript_captions_success(service):
    """Caption path returns text when available."""
    with patch.object(service, "_get_captions", return_value="Hello from captions"):
        result = await service.get_transcript("https://youtube.com/watch?v=dQw4w9WgXcQ")

    assert result.source == "captions"
    assert result.text == "Hello from captions"
    assert result.error is None


@pytest.mark.asyncio
async def test_get_transcript_fallback_to_audio(service):
    """Falls back to audio transcription when captions unavailable."""
    audio_result = YouTubeResult(text="transcribed audio", source="audio_transcription")

    with (
        patch.object(service, "_get_captions", return_value=None),
        patch.object(service, "_transcribe_audio", return_value=audio_result),
    ):
        result = await service.get_transcript("https://youtube.com/watch?v=dQw4w9WgXcQ")

    assert result.source == "audio_transcription"
    assert result.text == "transcribed audio"


@pytest.mark.asyncio
async def test_get_transcript_invalid_url(service):
    """Returns error for non-YouTube URL."""
    result = await service.get_transcript("https://example.com")
    assert result.error is not None
    assert "Could not extract video ID" in result.error
