"""Tests for MediaProcessor."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.media_processor import MediaProcessor, MediaResult
from app.services.youtube_service import YouTubeResult


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
def processor(settings):
    return MediaProcessor(settings)


class TestAudioURLDetection:
    """Test audio file extension detection."""

    def test_mp3(self):
        assert MediaProcessor._is_audio_url("https://example.com/episode.mp3")

    def test_m4a(self):
        assert MediaProcessor._is_audio_url("https://example.com/audio.m4a")

    def test_ogg(self):
        assert MediaProcessor._is_audio_url("https://example.com/audio.ogg")

    def test_wav(self):
        assert MediaProcessor._is_audio_url("https://example.com/audio.wav")

    def test_mp3_with_query(self):
        assert MediaProcessor._is_audio_url("https://cdn.example.com/ep.mp3?token=abc")

    def test_html(self):
        assert not MediaProcessor._is_audio_url("https://example.com/article.html")

    def test_none(self):
        assert not MediaProcessor._is_audio_url(None)

    def test_empty(self):
        assert not MediaProcessor._is_audio_url("")


@pytest.mark.asyncio
async def test_process_youtube_url(processor):
    """YouTube URL is routed to YouTubeService."""
    yt_result = YouTubeResult(text="video transcript", source="captions")

    with patch.object(
        processor.youtube_service, "get_transcript", return_value=yt_result
    ):
        result = await processor.process("https://youtube.com/watch?v=dQw4w9WgXcQ")

    assert result.is_media is True
    assert result.source == "youtube_captions"
    assert result.text == "video transcript"


@pytest.mark.asyncio
async def test_process_audio_enclosure(processor):
    """Audio enclosure URL is routed to download+transcribe."""
    mock_result = MediaResult(text="podcast text", source="podcast_audio", is_media=True)

    with patch.object(processor, "_process_audio", return_value=mock_result):
        result = await processor.process(
            "https://example.com/podcast",
            content_url="https://cdn.example.com/episode.mp3",
        )

    assert result.is_media is True
    assert result.source == "podcast_audio"
    assert result.text == "podcast text"


@pytest.mark.asyncio
async def test_process_non_media(processor):
    """Non-media URL returns is_media=False."""
    result = await processor.process("https://example.com/article")

    assert result.is_media is False
    assert result.source == "not_media"
    assert result.text == ""


@pytest.mark.asyncio
async def test_process_youtube_with_audio_enclosure(processor):
    """YouTube URL takes priority over audio enclosure."""
    yt_result = YouTubeResult(text="video transcript", source="captions")

    with patch.object(
        processor.youtube_service, "get_transcript", return_value=yt_result
    ):
        result = await processor.process(
            "https://youtube.com/watch?v=dQw4w9WgXcQ",
            content_url="https://cdn.example.com/audio.mp3",
        )

    assert result.is_media is True
    assert result.source == "youtube_captions"
