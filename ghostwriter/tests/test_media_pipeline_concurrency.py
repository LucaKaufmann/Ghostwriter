"""Deterministic, provider-free media pipeline concurrency tests."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.models.media_feed import MediaFeed
from app.models.media_item import MediaItem
from app.models.media_processing_run import MediaProcessingRun
from app.services.content_processor import ParsedArticle
from app.services.media_processor import MediaResult
from app.worker import media_pipeline


@pytest.fixture
def media_db(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'media.db'}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(media_pipeline, "engine", engine)
    yield engine
    engine.dispose()


def add_item(engine, *, status="pending", created_at=None):
    suffix = uuid4().hex
    with Session(engine) as session:
        feed = MediaFeed(
            feed_type="podcast",
            url=f"https://example.com/{suffix}",
            title=f"Feed {suffix}",
            is_active=False,
            mode="raw",
        )
        session.add(feed)
        session.commit()
        item = MediaItem(
            media_feed_id=feed.id,
            guid=suffix,
            url=f"https://example.com/{suffix}/episode",
            content_url=f"https://example.com/{suffix}/audio.mp3",
            title=f"Episode {suffix}",
            content_type="podcast",
            mode="raw",
            status=status,
            created_at=created_at or datetime.now(UTC),
        )
        session.add(item)
        session.commit()
        return item.id


def runs(engine):
    with Session(engine) as session:
        return session.exec(select(MediaProcessingRun)).all()


def item_status(engine, item_id):
    with Session(engine) as session:
        return session.get(MediaItem, item_id).status


@pytest.mark.asyncio
async def test_simultaneous_runs_have_one_discovery_and_transcription_owner(
    media_db, monkeypatch
):
    item_ids = [add_item(media_db) for _ in range(2)]
    discovery_started = asyncio.Event()
    allow_discovery = asyncio.Event()
    discovery_calls = 0
    active_transcriptions = 0
    peak_transcriptions = 0
    transcribed_urls = []

    async def discover(_settings):
        nonlocal discovery_calls
        discovery_calls += 1
        discovery_started.set()
        await allow_discovery.wait()
        return 0

    async def transcribe(_self, url, **_kwargs):
        nonlocal active_transcriptions, peak_transcriptions
        transcribed_urls.append(url)
        active_transcriptions += 1
        peak_transcriptions = max(peak_transcriptions, active_transcriptions)
        await asyncio.sleep(0)
        active_transcriptions -= 1
        return MediaResult(
            text="synthetic transcript", source="podcast_audio", is_media=True
        )

    monkeypatch.setattr(media_pipeline, "_fetch_and_create_items", discover)
    monkeypatch.setattr(media_pipeline.MediaProcessor, "process", transcribe)
    first = asyncio.create_task(media_pipeline.run_media_pipeline())
    await discovery_started.wait()
    second = asyncio.create_task(media_pipeline.run_media_pipeline())
    await asyncio.sleep(0)
    allow_discovery.set()
    await asyncio.gather(first, second)

    assert discovery_calls == 1
    assert len(transcribed_urls) == 2
    assert len(set(transcribed_urls)) == 2
    assert peak_transcriptions == 1
    assert [item_status(media_db, item_id) for item_id in item_ids] == [
        "completed",
        "completed",
    ]
    completed_runs = runs(media_db)
    assert len(completed_runs) == 1
    assert completed_runs[0].status == "completed"
    assert completed_runs[0].items_processed == 2
    assert completed_runs[0].items_failed == 0


@pytest.mark.asyncio
async def test_cancellation_fails_run_and_item_then_allows_retry(media_db, monkeypatch):
    item_id = add_item(media_db)
    processing_started = asyncio.Event()
    release_processing = asyncio.Event()
    calls = 0

    async def transcribe(_self, _url, **_kwargs):
        nonlocal calls
        calls += 1
        processing_started.set()
        await release_processing.wait()
        return MediaResult(
            text="retried transcript", source="podcast_audio", is_media=True
        )

    monkeypatch.setattr(media_pipeline.MediaProcessor, "process", transcribe)
    first = asyncio.create_task(media_pipeline.run_media_pipeline())
    await processing_started.wait()
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first

    assert item_status(media_db, item_id) == "failed"
    failed_run = runs(media_db)[0]
    assert failed_run.status == "failed"
    assert failed_run.completed_at is not None
    assert failed_run.error_message == "Media pipeline cancelled"

    with Session(media_db) as session:
        item = session.get(MediaItem, item_id)
        item.status = "pending"
        session.add(item)
        session.commit()
    release_processing.set()
    await media_pipeline.run_media_pipeline()
    assert calls == 2
    assert item_status(media_db, item_id) == "completed"
    assert [run.status for run in runs(media_db)] == ["failed", "completed"]


@pytest.mark.asyncio
async def test_cancellation_preserves_prior_completed_and_current_failed_counts(
    media_db, monkeypatch
):
    first_id = add_item(media_db)
    second_id = add_item(media_db)
    second_started = asyncio.Event()
    calls = 0

    async def transcribe(_self, _url, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            second_started.set()
            await asyncio.Event().wait()
        return MediaResult(text="first transcript", source="podcast_audio", is_media=True)

    monkeypatch.setattr(media_pipeline.MediaProcessor, "process", transcribe)
    task = asyncio.create_task(media_pipeline.run_media_pipeline())
    await second_started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert item_status(media_db, first_id) == "completed"
    assert item_status(media_db, second_id) == "failed"
    run = runs(media_db)[0]
    assert run.status == "failed"
    assert run.items_processed == 1
    assert run.items_failed == 1


@pytest.mark.asyncio
async def test_fetch_failure_and_stale_item_allow_later_run(media_db, monkeypatch):
    stale_id = add_item(
        media_db,
        status="processing",
        created_at=datetime.now(UTC) - timedelta(hours=2),
    )
    calls = 0

    async def discover(_settings):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("temporary discovery error")
        return 0

    monkeypatch.setattr(media_pipeline, "_fetch_and_create_items", discover)
    await media_pipeline.run_media_pipeline()
    assert item_status(media_db, stale_id) == "failed"
    assert runs(media_db)[0].status == "failed"

    with Session(media_db) as session:
        item = session.get(MediaItem, stale_id)
        item.status = "pending"
        session.add(item)
        session.commit()

    async def transcribe(_self, _url, **_kwargs):
        return MediaResult(
            text="later transcript", source="podcast_audio", is_media=True
        )

    monkeypatch.setattr(media_pipeline.MediaProcessor, "process", transcribe)
    await media_pipeline.run_media_pipeline()
    assert calls == 2
    assert item_status(media_db, stale_id) == "completed"
    assert [run.status for run in runs(media_db)] == ["failed", "completed"]


@pytest.mark.asyncio
async def test_transient_feed_error_is_retried_on_later_run(media_db, monkeypatch):
    item_id = add_item(media_db, status="completed")
    with Session(media_db) as session:
        item = session.get(MediaItem, item_id)
        feed = session.get(MediaFeed, item.media_feed_id)
        feed.is_active = True
        session.add(feed)
        session.commit()

    parse_calls = 0
    paid_calls = 0

    async def parse_feed(_self, _url, *, max_entries):
        nonlocal parse_calls
        parse_calls += 1
        if parse_calls == 1:
            raise RuntimeError("temporary feed outage")
        return [
            ParsedArticle(
                guid="new-episode",
                url="https://example.com/new-episode",
                title="New episode",
                content_url="https://example.com/new-episode.mp3",
            )
        ]

    async def transcribe(_self, _url, **_kwargs):
        nonlocal paid_calls
        paid_calls += 1
        return MediaResult(
            text="later transcript", source="podcast_audio", is_media=True
        )

    monkeypatch.setattr(media_pipeline.ContentProcessor, "parse_feed", parse_feed)
    monkeypatch.setattr(media_pipeline.MediaProcessor, "process", transcribe)
    await media_pipeline.run_media_pipeline()
    await media_pipeline.run_media_pipeline()

    assert parse_calls == 2
    assert paid_calls == 1
    assert [run.status for run in runs(media_db)] == ["completed", "completed"]
    assert [run.items_discovered for run in runs(media_db)] == [0, 1]
