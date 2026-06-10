"""Tests for podcast chapter markers: parsing, timing, ID3 tags, and API."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest
from mutagen.id3 import ID3
from sqlmodel import Session

from app.core.config import get_settings
from app.core.database import engine
from app.services.podcast_service import (
    PodcastDigestService,
    ScriptChapter,
    podcast_service,
)
from tests.test_podcast_api import (  # noqa: F401  (auth_headers is a fixture)
    _create_digest_with_articles,
    _create_episode,
    auth_headers,
)

DIALOGUE_SCRIPT_WITH_CHAPTERS = """[CHAPTER]: AI Chip Wars
[HOST_A]: Cold open about chips.
[HOST_B]: Context on the chip story.
[HOST_A]: More chip details.
[CHAPTER]: Open Source Funding
[HOST_B]: Funding story begins.
[HOST_A]: Funding analysis.
[HOST_B]: Closing thoughts.
"""

DIALOGUE_SCRIPT_NO_CHAPTERS = """[HOST_A]: Cold open about chips.
[HOST_B]: Context on the chip story.
[HOST_A]: More chip details.
[HOST_B]: Funding story begins.
[HOST_A]: Funding analysis.
[HOST_B]: Closing thoughts.
"""


class TestParseScriptWithChapters:
    def test_extracts_chapters_and_segments(self):
        segments, chapters = PodcastDigestService.parse_script_with_chapters(
            DIALOGUE_SCRIPT_WITH_CHAPTERS
        )
        assert len(segments) == 6
        assert [segment.speaker for segment in segments] == [
            "HOST_A",
            "HOST_B",
            "HOST_A",
            "HOST_B",
            "HOST_A",
            "HOST_B",
        ]
        assert [(c.title, c.segment_index) for c in chapters] == [
            ("AI Chip Wars", 0),
            ("Open Source Funding", 3),
        ]

    def test_script_without_markers_yields_no_chapters(self):
        segments, chapters = PodcastDigestService.parse_script_with_chapters(
            DIALOGUE_SCRIPT_NO_CHAPTERS
        )
        assert len(segments) == 6
        assert chapters == []

    def test_wrapper_returns_segments_only(self):
        segments = PodcastDigestService.parse_script_segments(
            DIALOGUE_SCRIPT_WITH_CHAPTERS
        )
        assert len(segments) == 6
        assert all(not s.text.startswith("[CHAPTER]") for s in segments)

    def test_marker_is_case_insensitive(self):
        script = DIALOGUE_SCRIPT_NO_CHAPTERS + "[Chapter]: Final Topic\n[HOST_A]: Bonus line.\n[HOST_B]: Bonus reply.\n"
        _, chapters = PodcastDigestService.parse_script_with_chapters(script)
        assert [(c.title, c.segment_index) for c in chapters] == [("Final Topic", 6)]

    def test_consecutive_markers_collapse_to_first(self):
        script = (
            "[CHAPTER]: First Title\n"
            "[CHAPTER]: Second Title\n" + DIALOGUE_SCRIPT_NO_CHAPTERS
        )
        _, chapters = PodcastDigestService.parse_script_with_chapters(script)
        assert [(c.title, c.segment_index) for c in chapters] == [("First Title", 0)]

    def test_trailing_marker_is_dropped(self):
        script = DIALOGUE_SCRIPT_NO_CHAPTERS + "[CHAPTER]: Points Nowhere\n"
        _, chapters = PodcastDigestService.parse_script_with_chapters(script)
        assert chapters == []

    def test_long_titles_truncated(self):
        script = "[CHAPTER]: " + "x" * 200 + "\n" + DIALOGUE_SCRIPT_NO_CHAPTERS
        _, chapters = PodcastDigestService.parse_script_with_chapters(script)
        assert len(chapters) == 1
        assert len(chapters[0].title) == 80

    def test_validation_rules_still_enforced(self):
        with pytest.raises(ValueError):
            PodcastDigestService.parse_script_with_chapters("[CHAPTER]: Only Marker")
        with pytest.raises(ValueError):
            PodcastDigestService.parse_script_with_chapters(
                "[CHAPTER]: T\n[HOST_A]: one line only"
            )
        with pytest.raises(ValueError):
            PodcastDigestService.parse_script_with_chapters(
                DIALOGUE_SCRIPT_WITH_CHAPTERS + "stage direction\n"
            )


class TestParseSoloScript:
    SOLO_SCRIPT = (
        "[CHAPTER]: Morning Markets\n"
        "Welcome to the briefing... markets opened sharply lower today.\n\n"
        "The selloff traces back to overnight chip export news.\n\n"
        "[pause]\n\n"
        "[CHAPTER]: Startup Shakeups\n"
        "Meanwhile a major startup announced a surprise pivot.\n\n"
        "Investors are split on what this means for the sector.\n"
    )

    def test_chapter_lines_do_not_count_as_paragraphs(self):
        cleaned = PodcastDigestService.parse_solo_script(self.SOLO_SCRIPT)
        # Markers are preserved in the stored script text.
        assert "[CHAPTER]: Morning Markets" in cleaned

    def test_minimum_paragraphs_excludes_markers(self):
        short = (
            "[CHAPTER]: A\n\nOne paragraph.\n\n[CHAPTER]: B\n\nTwo paragraph.\n\n"
            "[CHAPTER]: C\n\nThree paragraph.\n"
        )
        with pytest.raises(ValueError):
            PodcastDigestService.parse_solo_script(short)


class TestBuildSoloChunksWithChapters:
    def test_chunks_break_at_chapter_boundaries(self):
        chunks, chapters = PodcastDigestService._build_solo_chunks_with_chapters(
            TestParseSoloScript.SOLO_SCRIPT,
            provider="openai",
        )
        assert len(chunks) == 2
        assert "markets opened sharply lower" in chunks[0]
        assert "surprise pivot" in chunks[1]
        assert [(c.title, c.segment_index) for c in chapters] == [
            ("Morning Markets", 0),
            ("Startup Shakeups", 1),
        ]

    def test_wrapper_matches_chunks(self):
        chunks = PodcastDigestService._build_solo_chunks(
            TestParseSoloScript.SOLO_SCRIPT, provider="openai"
        )
        chunks_with, _ = PodcastDigestService._build_solo_chunks_with_chapters(
            TestParseSoloScript.SOLO_SCRIPT, provider="openai"
        )
        assert chunks == chunks_with

    def test_no_markers_yields_single_section(self):
        chunks, chapters = PodcastDigestService._build_solo_chunks_with_chapters(
            "First paragraph of plain content here.\n\nSecond paragraph follows on.",
            provider="openai",
        )
        assert len(chunks) == 1
        assert chapters == []


class TestBuildChapterMarkers:
    CHAPTERS = [
        ScriptChapter(title="One", segment_index=0),
        ScriptChapter(title="Two", segment_index=2),
        ScriptChapter(title="Three", segment_index=4),
    ]

    def test_accumulates_durations_and_gaps(self):
        markers = PodcastDigestService._build_chapter_markers(
            self.CHAPTERS,
            synthesized_indexes=[0, 1, 2, 3, 4, 5],
            durations=[10.0, 5.0, 8.0, 4.0, 6.0, 3.0],
            gap_durations=[0.5, 0.5, 0.5, 0.5, 0.5],
        )
        assert markers == [
            {"title": "One", "start_seconds": 0.0},
            {"title": "Two", "start_seconds": 16.0},
            {"title": "Three", "start_seconds": 29.0},
        ]

    def test_no_gaps_for_seamless_concat(self):
        markers = PodcastDigestService._build_chapter_markers(
            self.CHAPTERS,
            synthesized_indexes=[0, 1, 2, 3, 4],
            durations=[10.0, 5.0, 8.0, 4.0, 6.0],
            gap_durations=None,
        )
        assert markers is not None
        assert markers[1]["start_seconds"] == 15.0
        assert markers[2]["start_seconds"] == 27.0

    def test_skipped_segment_remaps_to_next_surviving(self):
        # Segment 2 (chapter Two's first line) failed TTS.
        markers = PodcastDigestService._build_chapter_markers(
            self.CHAPTERS,
            synthesized_indexes=[0, 1, 3, 4, 5],
            durations=[10.0, 5.0, 4.0, 6.0, 3.0],
            gap_durations=[0.5, 0.5, 0.5, 0.5],
        )
        assert markers is not None
        assert markers[1] == {"title": "Two", "start_seconds": 16.0}

    def test_fully_skipped_chapter_is_dropped(self):
        # Segments 2 and 3 (all of chapter Two) failed TTS: Two must be
        # dropped, not allowed to label the start of Three's audio.
        markers = PodcastDigestService._build_chapter_markers(
            self.CHAPTERS,
            synthesized_indexes=[0, 1, 4, 5],
            durations=[10.0, 5.0, 6.0, 3.0],
            gap_durations=[0.5, 0.5, 0.5],
        )
        assert markers is not None
        assert [m["title"] for m in markers] == ["One", "Three"]
        assert markers[1]["start_seconds"] == 16.0

    def test_single_chapter_returns_none(self):
        markers = PodcastDigestService._build_chapter_markers(
            [ScriptChapter(title="Solo", segment_index=0)],
            synthesized_indexes=[0, 1],
            durations=[10.0, 5.0],
            gap_durations=[0.5],
        )
        assert markers is None

    def test_mismatched_durations_return_none(self):
        markers = PodcastDigestService._build_chapter_markers(
            self.CHAPTERS,
            synthesized_indexes=[0, 1, 2],
            durations=[10.0, 5.0],
            gap_durations=None,
        )
        assert markers is None

    def test_first_marker_snaps_to_zero(self):
        markers = PodcastDigestService._build_chapter_markers(
            [
                ScriptChapter(title="One", segment_index=1),
                ScriptChapter(title="Two", segment_index=2),
            ],
            synthesized_indexes=[0, 1, 2],
            durations=[10.0, 5.0, 8.0],
            gap_durations=None,
        )
        assert markers is not None
        assert markers[0]["start_seconds"] == 0.0


class TestDialogueSceneChapterBreaks:
    def test_break_indexes_force_scene_seams(self):
        entries = [
            ("HOST_A", "a" * 100),
            ("HOST_B", "b" * 100),
            ("HOST_B", "c" * 100),
            ("HOST_A", "d" * 100),
        ]
        scenes = PodcastDigestService._group_dialogue_scenes(
            entries, max_chars=10_000, break_indexes={2}
        )
        assert scenes == [[0, 1], [2, 3]]

    def test_no_breaks_keeps_existing_grouping(self):
        entries = [("HOST_A", "a" * 100), ("HOST_B", "b" * 100)]
        scenes = PodcastDigestService._group_dialogue_scenes(entries, max_chars=10_000)
        assert scenes == [[0, 1]]


class TestWriteId3ChapterTags:
    def test_writes_chap_and_ctoc_frames(self, tmp_path):
        audio_path = tmp_path / "episode.mp3"
        audio_path.write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 256)
        chapters = [
            {"title": "Intro", "start_seconds": 0.0},
            {"title": "Deep Dive", "start_seconds": 61.25},
        ]
        PodcastDigestService._write_id3_chapter_tags(
            audio_path, chapters, total_duration_seconds=120
        )

        tag = ID3(audio_path)
        toc = tag.getall("CTOC")
        assert len(toc) == 1
        assert toc[0].child_element_ids == ["chp0", "chp1"]
        chaps = sorted(tag.getall("CHAP"), key=lambda frame: frame.start_time)
        assert len(chaps) == 2
        assert chaps[0].start_time == 0
        assert chaps[0].end_time == 61250
        assert str(chaps[0].sub_frames["TIT2"]) == "Intro"
        assert chaps[1].start_time == 61250
        assert chaps[1].end_time == 120000
        assert str(chaps[1].sub_frames["TIT2"]) == "Deep Dive"

    def test_skips_without_duration(self, tmp_path):
        audio_path = tmp_path / "episode.mp3"
        audio_path.write_bytes(b"\x00" * 64)
        PodcastDigestService._write_id3_chapter_tags(
            audio_path,
            [{"title": "Intro", "start_seconds": 0.0}],
            total_duration_seconds=None,
        )
        assert audio_path.read_bytes() == b"\x00" * 64


EPISODE_CHAPTERS = [
    {"title": "AI Chip Wars", "start_seconds": 0.0},
    {"title": "Open Source Funding", "start_seconds": 95.5},
]


def _ready_episode_with_chapters(chapters=None, token=None):
    digest_id, article_ids = _create_digest_with_articles(article_count=2)
    settings = get_settings()
    podcasts_dir = Path(settings.output_dir) / "podcasts"
    podcasts_dir.mkdir(parents=True, exist_ok=True)
    audio_path = podcasts_dir / f"chapters-{uuid4()}.mp3"
    audio_path.write_bytes(b"audio-bytes")

    user_id = None
    if token is not None:
        with Session(engine) as session:
            prefs = podcast_service.get_or_create_preferences(session, user_id=None)
            prefs.podcast_feed_enabled = True
            prefs.podcast_feed_token = token
            prefs.updated_at = datetime.utcnow()
            user_id = prefs.user_id
            session.add(prefs)
            session.commit()

    return _create_episode(
        digest_id=digest_id,
        article_ids=article_ids,
        status="ready",
        audio_path=audio_path,
        user_id=user_id,
        chapters=chapters,
    )


class TestChaptersApi:
    def test_episode_detail_includes_chapters(self, client, auth_headers):
        episode = _ready_episode_with_chapters(chapters=EPISODE_CHAPTERS)
        response = client.get(
            f"/api/podcast/episodes/{episode.id}", headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json()["chapters"] == [
            {"title": "AI Chip Wars", "start_seconds": 0.0},
            {"title": "Open Source Funding", "start_seconds": 95.5},
        ]

    def test_episode_detail_chapters_null_when_absent(self, client, auth_headers):
        episode = _ready_episode_with_chapters(chapters=None)
        response = client.get(
            f"/api/podcast/episodes/{episode.id}", headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json()["chapters"] is None

    def test_chapters_endpoint_returns_podcasting_2_0_json(self, client):
        token = f"feed_token_chapters_{uuid4().hex[:8]}"
        episode = _ready_episode_with_chapters(
            chapters=EPISODE_CHAPTERS, token=token
        )
        response = client.get(
            f"/api/podcast/episodes/{episode.id}/chapters?token={token}"
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith(
            "application/json+chapters"
        )
        payload = json.loads(response.content)
        assert payload == {
            "version": "1.2.0",
            "chapters": [
                {"startTime": 0.0, "title": "AI Chip Wars"},
                {"startTime": 95.5, "title": "Open Source Funding"},
            ],
        }

    def test_chapters_endpoint_404_when_absent(self, client, auth_headers):
        episode = _ready_episode_with_chapters(chapters=None)
        response = client.get(
            f"/api/podcast/episodes/{episode.id}/chapters", headers=auth_headers
        )
        assert response.status_code == 404

    def test_chapters_endpoint_rejects_invalid_token(self, client):
        token = f"feed_token_chapters_{uuid4().hex[:8]}"
        episode = _ready_episode_with_chapters(
            chapters=EPISODE_CHAPTERS, token=token
        )
        response = client.get(
            f"/api/podcast/episodes/{episode.id}/chapters?token=wrong_token_123"
        )
        assert response.status_code == 401

    def test_feed_xml_advertises_chapters(self, client):
        token = f"feed_token_chapters_{uuid4().hex[:8]}"
        with_chapters = _ready_episode_with_chapters(
            chapters=EPISODE_CHAPTERS, token=token
        )
        without_chapters = _ready_episode_with_chapters(chapters=None, token=token)

        feed = client.get(f"/api/podcast/feed.xml?token={token}")
        assert feed.status_code == 200
        root = ET.fromstring(feed.content)
        assert "podcastindex.org" in feed.content.decode()
        items = root.findall("./channel/item")
        tags_by_guid = {
            item.findtext("guid"): item.find(
                "{https://podcastindex.org/namespace/1.0}chapters"
            )
            for item in items
        }
        chapters_tag = tags_by_guid[f"podcast-episode-{with_chapters.id}"]
        assert chapters_tag is not None
        assert chapters_tag.attrib["type"] == "application/json+chapters"
        assert (
            f"/api/podcast/episodes/{with_chapters.id}/chapters?token={token}"
            in chapters_tag.attrib["url"]
        )
        assert tags_by_guid[f"podcast-episode-{without_chapters.id}"] is None
