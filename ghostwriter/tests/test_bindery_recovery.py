"""Offline evidence for digest failures after source selection.

These tests describe current behavior; they do not assert a new recovery policy.
"""

import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine, select

from app.models.client_config import ClientConfig
from app.models.digest import Digest, DigestArticle
from app.models.media_feed import MediaFeed
from app.models.media_item import MediaItem
from app.models.seen_article import SeenArticle
from app.services.content_processor import ExtractedArticle
from app.worker import bindery


class WallabagRemote:
    is_configured = True
    settings = SimpleNamespace(wallabag_mode="raw")

    def __init__(self):
        self.marked = []
        self.fail_mark = False
        self.apply_then_fail = False

    async def fetch_unread_articles(self):
        if self.marked:
            return []
        return [{
            "id": 7,
            "url": "https://example.com/saved",
            "title": "Saved item",
            "content": "<p>Enough synthetic words for the saved article body.</p>",
            "domain_name": "example.com",
        }]

    async def mark_processed(self, entry_id):
        if self.fail_mark:
            raise RuntimeError("remote marker unavailable")
        self.marked.append(entry_id)
        if self.apply_then_fail:
            raise RuntimeError("remote response lost after marker")


class NewsletterRemote:
    is_configured = True

    def __init__(self):
        self.marked = []
        self.fail_mark = False
        self.apply_then_fail = False

    async def fetch_newsletters(self):
        if self.marked:
            return [], []
        body = "Synthetic newsletter body with useful words for this test."
        return [ExtractedArticle(
            guid="message-1", url="https://example.com/mail",
            title="Newsletter", content=body, author="Writer",
            word_count=len(body.split()), feed_title="Newsletter",
        )], ["message-1"]

    async def mark_processed(self, ids):
        if self.fail_mark:
            raise RuntimeError("remote marker unavailable")
        self.marked.extend(ids)
        if self.apply_then_fail:
            raise RuntimeError("remote response lost after marker")


class ArtifactWriter:
    def __init__(self, directory):
        self.directory = directory
        self.fail = False

    def generate(self, *args, **kwargs):
        if self.fail:
            raise RuntimeError("artifact failure")
        path = self.directory / kwargs["output_filename"]
        path.write_bytes(b"synthetic epub artifact")
        return str(path)


@pytest.fixture
def scene(tmp_path, monkeypatch):
    database = create_engine(f"sqlite:///{tmp_path / 'recovery.db'}")
    SQLModel.metadata.create_all(database)
    monkeypatch.setattr(bindery, "engine", database)
    remote = WallabagRemote()
    mail = NewsletterRemote()
    writer = ArtifactWriter(tmp_path)
    monkeypatch.setattr(
        bindery.WallabagService, "from_db_or_settings",
        classmethod(lambda cls, *args: remote),
    )
    monkeypatch.setattr(bindery, "NewsletterService", lambda *args: mail)

    with Session(database) as session:
        session.add(ClientConfig(newsletter_mode="raw"))
        feed = MediaFeed(
            feed_type="podcast", url="https://example.com/podcast",
            title="Synthetic podcast",
        )
        session.add(feed)
        session.flush()
        media = MediaItem(
            media_feed_id=feed.id, guid="episode-1",
            url="https://example.com/episode-1", title="Episode 1",
            content="Synthetic completed transcript for a reading edition.",
            word_count=7, status="completed", content_type="podcast",
        )
        session.add(media)
        session.commit()
        media_id = media.id

    def new_pipeline():
        digest_id = uuid4()
        with Session(database) as session:
            session.add(Digest(
                id=digest_id, filename=f"{digest_id}.epub", period="manual",
                status="processing", stage="queued", locked_at=datetime.utcnow(),
            ))
            session.commit()
        pipeline = bindery.BinderyPipeline(digest_id)
        pipeline.epub_generator = writer
        return pipeline

    def snapshot(digest_id):
        with Session(database) as session:
            digest = session.get(Digest, digest_id)
            media = session.get(MediaItem, media_id)
            rows = session.exec(select(DigestArticle).where(
                DigestArticle.digest_id == digest_id
            )).all()
            seen = session.exec(select(SeenArticle)).all()
            return {
                "status": digest.status,
                "stage": digest.stage,
                "error": digest.error_message,
                "count": digest.article_count,
                "rows": [(r.content_type, r.title) for r in rows],
                "seen": len(seen),
                "media_digest": media.consumed_digest_id,
                "artifact": (tmp_path / digest.filename).exists(),
            }

    return SimpleNamespace(
        database=database, remote=remote, mail=mail, writer=writer,
        media_id=media_id, new_pipeline=new_pipeline, snapshot=snapshot,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "boundary", ["artifact", "articles", "media", "completion_commit", "completion_log"]
)
async def test_failed_boundaries_leave_distinct_durable_state(scene, monkeypatch, boundary):
    pipeline = scene.new_pipeline()
    events = []
    monkeypatch.setattr(
        bindery.digest_logger, "pipeline_failed",
        lambda digest_id, error, stage=None: events.append(("failed", stage)),
    )
    monkeypatch.setattr(
        bindery.digest_logger, "pipeline_completed",
        lambda *args, **kwargs: events.append(("completed", None)),
    )
    if boundary == "artifact":
        scene.writer.fail = True
    elif boundary == "articles":
        async def fail_articles(*args):
            raise RuntimeError("article persistence failure")
        monkeypatch.setattr(pipeline, "_save_newsletter_article_records", fail_articles)
    elif boundary == "media":
        def fail_media(_mapper, _connection, _target):
            raise RuntimeError("media consumed failure")
        event.listen(MediaItem, "before_update", fail_media)
    elif boundary == "completion_commit":
        def fail_final_commit(session):
            if any(
                isinstance(obj, Digest) and obj.status == "completed"
                for obj in session.dirty
            ):
                raise RuntimeError("completion commit failure")
        event.listen(Session, "before_commit", fail_final_commit)
    else:
        def fail_final_log(*args, **kwargs):
            raise RuntimeError("completion log failure")
        monkeypatch.setattr(bindery.digest_logger, "pipeline_completed", fail_final_log)

    try:
        with pytest.raises(RuntimeError):
            await pipeline.run()
    finally:
        if boundary == "media":
            event.remove(MediaItem, "before_update", fail_media)
        elif boundary == "completion_commit":
            event.remove(Session, "before_commit", fail_final_commit)

    first = scene.snapshot(pipeline.digest_id)
    assert first["status"] == "failed"
    final_log_committed = boundary == "completion_log"
    assert first["stage"] == ("completed" if final_log_committed else "compiling")
    assert events == [("failed", first["stage"])]
    assert first["count"] == (3 if final_log_committed else 0)
    assert first["seen"] == (2 if final_log_committed else 0)
    assert first["artifact"] == (boundary != "artifact")
    assert len(first["rows"]) == {
        "artifact": 0, "articles": 1, "media": 3,
        "completion_commit": 3, "completion_log": 3,
    }[boundary]
    assert first["media_digest"] == (
        pipeline.digest_id if boundary.startswith("completion") else None
    )
    assert scene.remote.marked == ([7] if boundary.startswith("completion") else [])
    assert scene.mail.marked == (
        ["message-1"] if boundary.startswith("completion") else []
    )

    scene.writer.fail = False
    if boundary == "completion_log":
        monkeypatch.setattr(
            bindery.digest_logger, "pipeline_completed", lambda *args, **kwargs: None
        )
    retry = scene.new_pipeline()
    await retry.run()
    second = scene.snapshot(retry.digest_id)
    assert second["status"] == "completed"
    assert second["artifact"] == (not boundary.startswith("completion"))
    assert len(second["rows"]) == (
        0 if boundary.startswith("completion") else 3
    )
    assert second["count"] == len(second["rows"])
    assert second["media_digest"] == (
        pipeline.digest_id if boundary.startswith("completion") else retry.digest_id
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("marker_effect", ["none", "applied_then_error"])
async def test_remote_marker_errors_are_logged_but_job_completes(
    scene, caplog, marker_effect
):
    scene.remote.fail_mark = marker_effect == "none"
    scene.mail.fail_mark = marker_effect == "none"
    scene.remote.apply_then_fail = marker_effect == "applied_then_error"
    scene.mail.apply_then_fail = marker_effect == "applied_then_error"
    pipeline = scene.new_pipeline()
    await pipeline.run()
    state = scene.snapshot(pipeline.digest_id)
    assert state["status"] == "completed"
    assert len(state["rows"]) == 3
    assert state["seen"] == 2
    assert scene.remote.marked == (
        [] if marker_effect == "none" else [7]
    )
    assert scene.mail.marked == (
        [] if marker_effect == "none" else ["message-1"]
    )
    assert "Failed to mark newsletter emails as read" in caplog.text
    assert "Failed to mark wallabag entry" in caplog.text

    retry = scene.new_pipeline()
    await retry.run()
    assert scene.snapshot(retry.digest_id)["count"] == 0


@pytest.mark.asyncio
async def test_cancellation_leaves_processing_until_restart(scene, monkeypatch):
    from app import main

    pipeline = scene.new_pipeline()

    def cancel_at_final_commit(session):
        if any(
            isinstance(obj, Digest) and obj.status == "completed"
            for obj in session.dirty
        ):
            raise asyncio.CancelledError()

    event.listen(Session, "before_commit", cancel_at_final_commit)
    try:
        with pytest.raises(asyncio.CancelledError):
            await pipeline.run()
    finally:
        event.remove(Session, "before_commit", cancel_at_final_commit)
    before = scene.snapshot(pipeline.digest_id)
    assert before["status"] == "processing"
    assert len(before["rows"]) == 3
    assert before["media_digest"] == pipeline.digest_id

    monkeypatch.setattr(main, "engine", scene.database)
    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.setattr(main, "setup_scheduler", lambda: None)
    monkeypatch.setattr(main, "shutdown_scheduler", lambda: None)
    monkeypatch.setattr(main.podcast_service, "recover_stuck_episodes", lambda: 0)
    monkeypatch.setattr(main.podcast_service, "set_event_loop", lambda *_: None)
    async with main.lifespan(main.app):
        pass
    after = scene.snapshot(pipeline.digest_id)
    assert after["status"] == "failed"
    assert after["error"] == "Cleared on restart"
    assert len(after["rows"]) == 3
    assert after["artifact"]
    assert after["media_digest"] == pipeline.digest_id


@pytest.mark.asyncio
async def test_cancellation_after_final_commit_keeps_completed_job(scene, monkeypatch):
    pipeline = scene.new_pipeline()

    def cancel_completion_log(*args, **kwargs):
        raise asyncio.CancelledError()

    monkeypatch.setattr(
        bindery.digest_logger, "pipeline_completed", cancel_completion_log
    )
    with pytest.raises(asyncio.CancelledError):
        await pipeline.run()
    state = scene.snapshot(pipeline.digest_id)
    assert state["status"] == "completed"
    assert state["stage"] == "completed"
    assert state["count"] == 3
    assert state["seen"] == 2
    assert len(state["rows"]) == 3
    assert state["artifact"]


@pytest.mark.asyncio
async def test_fresh_lock_blocks_then_stale_cutoff_fails_old_job(scene, monkeypatch):
    old = scene.new_pipeline()
    tasks = []

    def hold_task(coro):
        coro.close()
        tasks.append(True)
        return SimpleNamespace(get_name=lambda: "held")

    monkeypatch.setattr(bindery.asyncio, "create_task", hold_task)
    assert await bindery.generate_digest() is None
    assert tasks == []
    with Session(scene.database) as session:
        digest = session.get(Digest, old.digest_id)
        digest.locked_at = datetime.utcnow() - timedelta(minutes=31)
        session.add(digest)
        session.commit()
    new_id = await bindery.generate_digest()
    assert new_id is not None
    assert tasks == [True]
    old_state = scene.snapshot(old.digest_id)
    assert old_state["status"] == "failed"
    assert old_state["error"] == "Stale lock released"
    assert scene.snapshot(new_id)["status"] == "processing"
