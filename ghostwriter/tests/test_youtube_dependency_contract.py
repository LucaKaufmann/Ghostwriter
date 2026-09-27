"""Exercise Ghostwriter captions against the installed transcript library API."""

import pytest
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._transcripts import TranscriptList

from app.core.config import Settings
from app.services.youtube_service import YouTubeService


class _CaptionResponse:
    status_code = 200
    text = (
        '<transcript><text start="0" dur="1">Hello</text>'
        '<text start="1" dur="1">world</text></transcript>'
    )

    def raise_for_status(self):
        pass


class _CaptionSession:
    def __init__(self):
        self.urls = []

    def get(self, url):
        self.urls.append(url)
        return _CaptionResponse()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("languages", "expected"),
    [(["en"], "Hello world"), (["de"], "Hello world"), ([], None)],
    ids=["english", "any-language", "empty"],
)
async def test_installed_transcript_api_caption_paths(monkeypatch, languages, expected):
    """Use real fetch/list/TranscriptList behavior without any HTTP request."""
    video_id = "dQw4w9WgXcQ"
    session = _CaptionSession()
    transcript_list = TranscriptList.build(
        session,
        video_id,
        {
            "captionTracks": [
                {
                    "languageCode": language,
                    "baseUrl": f"https://example.com/captions/{language}",
                    "name": {"runs": [{"text": language}]},
                }
                for language in languages
            ]
        },
    )

    def list_transcripts(self, requested_id):
        assert requested_id == video_id
        return transcript_list

    monkeypatch.setattr(YouTubeTranscriptApi, "list", list_transcripts)
    result = await YouTubeService(Settings())._get_captions(video_id)
    assert result == expected
    assert len(session.urls) == (0 if expected is None else 1)
