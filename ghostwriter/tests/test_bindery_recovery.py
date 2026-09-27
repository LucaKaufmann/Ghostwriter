"""Offline recovery boundaries for atomic digest publication and source receipts."""

import asyncio
from datetime import datetime
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
from app.models.source_acknowledgement import SourceAcknowledgement
from app.services import source_acknowledgement as acknowledgement_service
from app.services.content_processor import ExtractedArticle
from app.services.source_acknowledgement import (
    add_intent,
    drain_pending,
    gmail_binding_for_account,
    wallabag_binding,
)
from app.worker import bindery


async def wait_for_follow_ups():
    """Keep background scans inside the lifetime of their disposable test DB."""
    while True:
        await asyncio.sleep(0)  # Let call_soon create a queued follow-up.
        tasks = tuple(acknowledgement_service._follow_up_tasks)
        if tasks:
            await asyncio.gather(*tasks)
            continue
        if not acknowledgement_service._pending_requests:
            break
    assert not acknowledgement_service._drain_lock.locked()


class WallabagRemote:
    is_configured = True
    settings = SimpleNamespace(
        wallabag_mode="raw", wallabag_url="https://wallabag.example.test",
        wallabag_username="fixture", wallabag_client_id="fixture",
        wallabag_tag_on_process="ghostwriter",
    )

    def __init__(self):
        self.marked = []
        self.fail_mark = False
        self.apply_then_fail = False

    async def fetch_unread_articles(self):
        if self.marked:
            return []
        return [{
            "id": 7, "url": "https://example.com/saved", "title": "Saved item",
            "content": "<p>Enough synthetic words for the saved article body.</p>",
            "domain_name": "example.com",
        }]

    async def mark_processed(self, entry_id):
        if self.fail_mark:
            raise RuntimeError("remote unavailable")
        self.marked.append(entry_id)
        if self.apply_then_fail:
            raise RuntimeError("response lost")


class NewsletterRemote:
    is_configured = True
    settings = SimpleNamespace(gmail_client_id="fixture", gmail_label="Ghostwriter")

    def __init__(self):
        self.marked = []
        self.fail_mark = False
        self.apply_then_fail = False
        self.account = "fixture@example.test"

    async def get_account_id(self):
        return self.account

    async def _get_access_token(self):
        return "fixture-token"

    async def get_account_id_for_token(self, _token):
        return self.account

    async def fetch_newsletters(self):
        self.last_fetch_account_id = self.account
        if self.marked:
            return [], []
        body = "Synthetic newsletter body with useful words for this test."
        return [ExtractedArticle(
            guid="message-1", url="https://example.com/mail", title="Newsletter",
            content=body, author="Writer", word_count=len(body.split()),
            feed_title="Newsletter",
        )], ["message-1"]

    async def mark_processed(self, ids):
        if self.fail_mark:
            raise RuntimeError("remote unavailable")
        self.marked.extend(ids)
        if self.apply_then_fail:
            raise RuntimeError("response lost")

    async def mark_processed_with_token(self, ids, _token):
        await self.mark_processed(ids)


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
            feed_type="podcast", url="https://example.com/podcast", title="Synthetic"
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
            receipts = session.exec(select(SourceAcknowledgement)).all()
            return SimpleNamespace(
                status=digest.status, count=digest.article_count,
                rows=rows, seen=session.exec(select(SeenArticle)).all(),
                media_owner=media.consumed_digest_id,
                artifact=(tmp_path / digest.filename).exists(),
                receipts=receipts,
            )

    return SimpleNamespace(
        database=database, remote=remote, mail=mail, writer=writer,
        media_id=media_id, new_pipeline=new_pipeline, snapshot=snapshot,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["artifact", "article", "media", "commit"])
async def test_failed_publication_rolls_back_all_claims(scene, boundary):
    pipeline = scene.new_pipeline()
    listener = None
    target = None
    if boundary == "artifact":
        scene.writer.fail = True
    elif boundary == "article":
        target = DigestArticle
        def listener(*_):
            raise RuntimeError("article failure")
        event.listen(target, "before_insert", listener)
    elif boundary == "media":
        target = MediaItem
        def listener(*_):
            raise RuntimeError("media failure")
        event.listen(target, "before_update", listener)
    else:
        target = Session
        def listener(session):
            if any(isinstance(x, Digest) and x.status == "completed" for x in session.dirty):
                raise RuntimeError("commit failure")
        event.listen(target, "before_commit", listener)
    try:
        with pytest.raises(RuntimeError):
            await pipeline.run()
    finally:
        if listener is not None:
            event.remove(target, "before_insert" if boundary == "article" else
                         "before_update" if boundary == "media" else "before_commit", listener)
    failed = scene.snapshot(pipeline.digest_id)
    assert failed.status == "failed"
    assert failed.rows == [] and failed.seen == [] and failed.receipts == []
    assert failed.media_owner is None
    assert scene.remote.marked == [] and scene.mail.marked == []

    scene.writer.fail = False
    retry = scene.new_pipeline()
    await retry.run()
    state = scene.snapshot(retry.digest_id)
    assert state.status == "completed" and state.artifact
    assert state.count == len(state.rows) == 3
    assert state.media_owner == retry.digest_id
    assert len(state.seen) == 2
    assert {receipt.state for receipt in state.receipts} == {"done"}


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["synthetic", "digest", "config"])
async def test_pre_pipeline_read_failure_marks_run_failed_and_allows_retry(scene, monkeypatch, boundary):
    pipeline = scene.new_pipeline()
    if boundary == "synthetic":
        monkeypatch.setattr(pipeline, "_ensure_synthetic_feeds", lambda: (_ for _ in ()).throw(
            RuntimeError("synthetic feed read failed")
        ))
        listener = None
    else:
        marker = "from digest" if boundary == "digest" else "from client_config"
        failed_once = False

        def fail_once(_conn, _cursor, statement, _parameters, _context, _executemany):
            nonlocal failed_once
            if not failed_once and marker in statement.lower():
                failed_once = True
                raise RuntimeError(f"{boundary} read failed")

        listener = fail_once
        event.listen(scene.database, "before_cursor_execute", listener)
    try:
        with pytest.raises(RuntimeError, match="read failed"):
            await pipeline.run()
    finally:
        if listener:
            event.remove(scene.database, "before_cursor_execute", listener)
    failed = scene.snapshot(pipeline.digest_id)
    assert failed.status == "failed"
    assert failed.rows == [] and failed.seen == [] and failed.receipts == []
    assert failed.media_owner is None and not failed.artifact
    with Session(scene.database) as session:
        digest = session.get(Digest, pipeline.digest_id)
        assert digest.locked_at is None
        assert "read failed" in digest.error_message

    retry = scene.new_pipeline()
    await retry.run()
    assert scene.snapshot(retry.digest_id).status == "completed"


@pytest.mark.asyncio
async def test_post_commit_logger_error_cannot_demote_completed(scene, monkeypatch):
    pipeline = scene.new_pipeline()
    monkeypatch.setattr(bindery.digest_logger, "pipeline_completed", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("log failure")))
    await pipeline.run()
    state = scene.snapshot(pipeline.digest_id)
    assert state.status == "completed" and state.artifact
    assert state.count == len(state.rows) == 3
    assert state.media_owner == pipeline.digest_id


@pytest.mark.asyncio
@pytest.mark.parametrize("effect", ["none", "applied_then_error"])
async def test_remote_uncertainty_keeps_receipts_until_retry(scene, effect):
    scene.remote.fail_mark = effect == "none"
    scene.mail.fail_mark = effect == "none"
    scene.remote.apply_then_fail = effect == "applied_then_error"
    scene.mail.apply_then_fail = effect == "applied_then_error"
    pipeline = scene.new_pipeline()
    await pipeline.run()
    state = scene.snapshot(pipeline.digest_id)
    assert state.status == "completed" and state.count == 3
    assert {receipt.state for receipt in state.receipts} == {"pending"}
    scene.remote.fail_mark = scene.mail.fail_mark = False
    scene.remote.apply_then_fail = scene.mail.apply_then_fail = False
    await pipeline._drain_source_acknowledgements()
    assert {receipt.state for receipt in scene.snapshot(pipeline.digest_id).receipts} == {"done"}
    assert scene.remote.marked and scene.mail.marked


@pytest.mark.asyncio
async def test_changed_account_suspends_without_sending(scene):
    scene.mail.fail_mark = True
    pipeline = scene.new_pipeline()
    await pipeline.run()
    before = len(scene.mail.marked)
    scene.mail.fail_mark = False
    scene.mail.account = "other@example.test"
    await pipeline._drain_source_acknowledgements()
    assert len(scene.mail.marked) == before
    assert any(r.state == "suspended" for r in scene.snapshot(pipeline.digest_id).receipts)


@pytest.mark.asyncio
async def test_crash_after_provider_success_replays_pending_receipt(scene):
    scene.remote.fail_mark = scene.mail.fail_mark = True
    pipeline = scene.new_pipeline()
    await pipeline.run()
    scene.remote.fail_mark = scene.mail.fail_mark = False

    def fail_done_commit(session):
        if any(
            isinstance(x, SourceAcknowledgement) and x.state == "done"
            for x in session.dirty
        ):
            raise RuntimeError("simulated crash before receipt commit")

    event.listen(Session, "before_commit", fail_done_commit)
    try:
        with pytest.raises(RuntimeError, match="simulated crash"):
            await pipeline._drain_source_acknowledgements()
    finally:
        event.remove(Session, "before_commit", fail_done_commit)
    assert any(r.state == "pending" for r in scene.snapshot(pipeline.digest_id).receipts)
    first_remote_calls = len(scene.remote.marked) + len(scene.mail.marked)
    assert first_remote_calls == 1
    await pipeline._drain_source_acknowledgements()
    assert len(scene.remote.marked) + len(scene.mail.marked) == 3
    assert {r.state for r in scene.snapshot(pipeline.digest_id).receipts} == {"done"}


@pytest.mark.asyncio
async def test_gmail_ack_uses_the_verified_token_even_if_next_token_changes(scene):
    scene.mail.fail_mark = True
    pipeline = scene.new_pipeline()
    await pipeline.run()
    scene.mail.fail_mark = False
    tokens = iter(["token-for-original", "token-for-other"])
    used = []

    async def next_token():
        return next(tokens)

    async def account_for_token(token):
        return (
            "fixture@example.test" if token == "token-for-original"
            else "other@example.test"
        )

    async def mark_with_token(ids, token):
        used.append((ids, token))

    scene.mail._get_access_token = next_token
    scene.mail.get_account_id_for_token = account_for_token
    scene.mail.mark_processed_with_token = mark_with_token
    await pipeline._drain_source_acknowledgements()
    assert used == [(["message-1"], "token-for-original")]
    assert next(tokens) == "token-for-other"


@pytest.mark.asyncio
async def test_suspended_mismatches_do_not_starve_later_receipts(scene):
    binding = wallabag_binding(scene.remote)
    with Session(scene.database) as session:
        for index in range(3):
            session.add(SourceAcknowledgement(
                digest_id=uuid4(), provider="wallabag",
                source_identity=("wrong" if index < 2 else binding[0]),
                source_config_fingerprint=("wrong" if index < 2 else binding[1]),
                external_item_id=str(index + 1), action="archive_and_tag",
                created_at=datetime(2026, 1, index + 1),
            ))
        session.commit()
    def factory(_session):
        return scene.remote
    await drain_pending(engine=scene.database, limit=2, wallabag_factory=factory)
    assert scene.remote.marked == []
    await drain_pending(engine=scene.database, limit=2, wallabag_factory=factory)
    assert scene.remote.marked == [3]


@pytest.mark.asyncio
async def test_slow_provider_budget_and_concurrent_scan_do_not_delay_edition(scene):
    pipeline = scene.new_pipeline()
    started = asyncio.Event()

    async def stalled_mark(_entry_id):
        started.set()
        await asyncio.Event().wait()

    scene.remote.mark_processed = stalled_mark

    async def short_drain(**kwargs):
        await drain_pending(
            engine=scene.database, deadline_seconds=0.05,
            newsletter_factory=lambda: scene.mail,
            wallabag_factory=lambda _session: scene.remote,
            **kwargs,
        )

    pipeline._drain_source_acknowledgements = short_drain
    run_task = asyncio.create_task(pipeline.run())
    await asyncio.wait_for(started.wait(), 1)
    await asyncio.wait_for(short_drain(request_follow_up=False), 0.02)
    await asyncio.wait_for(run_task, 1)
    state = scene.snapshot(pipeline.digest_id)
    assert state.status == "completed" and state.artifact
    assert state.count == len(state.rows) == 3
    assert any(r.state == "pending" for r in state.receipts)
    assert any(r.last_error_code == "deadline_exceeded" for r in state.receipts)
    await asyncio.wait_for(wait_for_follow_ups(), 2)


@pytest.mark.asyncio
async def test_publication_during_prior_drain_gets_automatic_follow_up(scene):
    binding = wallabag_binding(scene.remote)
    with Session(scene.database) as session:
        session.add(SourceAcknowledgement(
            digest_id=uuid4(), provider="wallabag",
            source_identity=binding[0], source_config_fingerprint=binding[1],
            external_item_id="99", action="archive_and_tag",
        ))
        session.commit()
    started = asyncio.Event()

    async def mark(entry_id):
        if entry_id == 99:
            started.set()
            await asyncio.Event().wait()
        scene.remote.marked.append(entry_id)

    scene.remote.mark_processed = mark
    prior = asyncio.create_task(drain_pending(
        engine=scene.database, limit=1, deadline_seconds=0.5,
        wallabag_factory=lambda _session: scene.remote,
    ))
    await asyncio.wait_for(started.wait(), 1)
    pipeline = scene.new_pipeline()
    await asyncio.wait_for(pipeline.run(), 1)
    assert scene.snapshot(pipeline.digest_id).status == "completed"
    assert scene.remote.marked == []  # Publication returned while prior pass held lock.
    await asyncio.wait_for(prior, 2)
    async def wait_for_new_receipts():
        while True:
            with Session(scene.database) as session:
                new = session.exec(select(SourceAcknowledgement).where(
                    SourceAcknowledgement.digest_id == pipeline.digest_id
                )).all()
                if len(new) == 2 and all(receipt.state == "done" for receipt in new):
                    return
            await asyncio.sleep(0.01)

    await asyncio.wait_for(wait_for_new_receipts(), 2)
    await asyncio.wait_for(wait_for_follow_ups(), 2)
    with Session(scene.database) as session:
        old = session.exec(select(SourceAcknowledgement).where(
            SourceAcknowledgement.external_item_id == "99"
        )).one()
        new = session.exec(select(SourceAcknowledgement).where(
            SourceAcknowledgement.digest_id == pipeline.digest_id
        )).all()
        assert old.state == "pending" and old.last_error_code == "deadline_exceeded"
        assert len(new) == 2 and {receipt.state for receipt in new} == {"done"}
    assert scene.remote.marked == [7]


@pytest.mark.asyncio
async def test_cancelled_prior_pass_propagates_and_preserves_follow_up(scene):
    binding = wallabag_binding(scene.remote)
    with Session(scene.database) as session:
        session.add(SourceAcknowledgement(
            digest_id=uuid4(), provider="wallabag",
            source_identity=binding[0], source_config_fingerprint=binding[1],
            external_item_id="99", action="archive_and_tag",
        ))
        session.commit()
    started = asyncio.Event()

    async def mark(entry_id):
        if entry_id == 99:
            started.set()
            await asyncio.Event().wait()
        scene.remote.marked.append(entry_id)

    scene.remote.mark_processed = mark
    prior = asyncio.create_task(drain_pending(
        engine=scene.database, limit=1, deadline_seconds=10,
        wallabag_factory=lambda _session: scene.remote,
    ))
    await asyncio.wait_for(started.wait(), 1)
    pipeline = scene.new_pipeline()
    await asyncio.wait_for(pipeline.run(), 1)
    prior.cancel()
    with pytest.raises(asyncio.CancelledError):
        await prior

    async def wait_for_new_receipts():
        while True:
            with Session(scene.database) as session:
                new = session.exec(select(SourceAcknowledgement).where(
                    SourceAcknowledgement.digest_id == pipeline.digest_id
                )).all()
                if len(new) == 2 and all(receipt.state == "done" for receipt in new):
                    return
            await asyncio.sleep(0.01)

    await asyncio.wait_for(wait_for_new_receipts(), 2)
    await asyncio.wait_for(wait_for_follow_ups(), 2)
    assert scene.remote.marked == [7]


@pytest.mark.asyncio
async def test_digest_follow_up_continues_only_unattempted_receipts(scene):
    digest_id = uuid4()
    binding = wallabag_binding(scene.remote)
    with Session(scene.database) as session:
        for index in range(1, 52):
            session.add(SourceAcknowledgement(
                digest_id=digest_id, provider="wallabag",
                source_identity=binding[0], source_config_fingerprint=binding[1],
                external_item_id=str(index), action="archive_and_tag",
                created_at=datetime(2026, 1, 1, 0, 0, index),
            ))
        session.commit()

    async def mark(entry_id):
        if entry_id == 1:
            raise RuntimeError("provider unavailable for one item")
        scene.remote.marked.append(entry_id)

    scene.remote.mark_processed = mark
    await drain_pending(
        engine=scene.database, limit=50, digest_id=digest_id,
        wallabag_factory=lambda _session: scene.remote,
    )
    await asyncio.wait_for(wait_for_follow_ups(), 2)
    with Session(scene.database) as session:
        receipts = session.exec(select(SourceAcknowledgement).where(
            SourceAcknowledgement.digest_id == digest_id
        )).all()
    assert len(receipts) == 51
    assert all(receipt.attempt_count == 1 for receipt in receipts)
    assert {receipt.external_item_id for receipt in receipts if receipt.state == "done"} == {
        str(index) for index in range(2, 52)
    }
    assert {receipt.external_item_id for receipt in receipts if receipt.state == "pending"} == {"1"}
    assert sorted(scene.remote.marked) == list(range(2, 52))


@pytest.mark.asyncio
async def test_cancellation_before_commit_is_retryable_after_startup(scene, monkeypatch):
    from app import main

    pipeline = scene.new_pipeline()

    def cancel_commit(session):
        if any(isinstance(x, Digest) and x.status == "completed" for x in session.dirty):
            raise asyncio.CancelledError()

    event.listen(Session, "before_commit", cancel_commit)
    try:
        with pytest.raises(asyncio.CancelledError):
            await pipeline.run()
    finally:
        event.remove(Session, "before_commit", cancel_commit)
    before = scene.snapshot(pipeline.digest_id)
    assert before.status == "failed"
    assert before.rows == [] and before.seen == [] and before.receipts == []
    assert before.media_owner is None
    assert scene.remote.marked == [] and scene.mail.marked == []

    monkeypatch.setattr(main, "engine", scene.database)
    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.setattr(main, "setup_scheduler", lambda: None)
    monkeypatch.setattr(main, "shutdown_scheduler", lambda: None)
    monkeypatch.setattr(main.podcast_service, "recover_stuck_episodes", lambda: 0)
    monkeypatch.setattr(main.podcast_service, "set_event_loop", lambda *_: None)
    async with main.lifespan(main.app):
        await asyncio.sleep(0)
    assert scene.snapshot(pipeline.digest_id).status == "failed"
    retry = scene.new_pipeline()
    await retry.run()
    assert scene.snapshot(retry.digest_id).count == 3


@pytest.mark.asyncio
async def test_cancellation_after_commit_keeps_edition_and_retries_receipts(scene, monkeypatch):
    from app import main
    from app.services import source_acknowledgement as ack

    pipeline = scene.new_pipeline()
    scene.remote.fail_mark = scene.mail.fail_mark = True

    def cancel_log(*_args, **_kwargs):
        raise asyncio.CancelledError()

    monkeypatch.setattr(bindery.digest_logger, "pipeline_completed", cancel_log)
    with pytest.raises(asyncio.CancelledError):
        await pipeline.run()
    state = scene.snapshot(pipeline.digest_id)
    assert state.status == "completed" and state.artifact and state.count == 3
    assert {r.state for r in state.receipts} == {"pending"}

    scene.remote.fail_mark = scene.mail.fail_mark = False
    monkeypatch.setattr(main, "engine", scene.database)
    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.setattr(main, "setup_scheduler", lambda: None)
    monkeypatch.setattr(main, "shutdown_scheduler", lambda: None)
    monkeypatch.setattr(main.podcast_service, "recover_stuck_episodes", lambda: 0)
    monkeypatch.setattr(main.podcast_service, "set_event_loop", lambda *_: None)
    monkeypatch.setattr(ack, "NewsletterService", lambda *_: scene.mail)
    async with main.lifespan(main.app):
        await asyncio.sleep(0.05)
    assert {r.state for r in scene.snapshot(pipeline.digest_id).receipts} == {"done"}
    assert scene.snapshot(pipeline.digest_id).status == "completed"


@pytest.mark.asyncio
async def test_media_changed_after_selection_aborts_publication(scene):
    pipeline = scene.new_pipeline()
    original = scene.writer.generate

    def change_media(*args, **kwargs):
        artifact = original(*args, **kwargs)
        with Session(scene.database) as session:
            media = session.get(MediaItem, scene.media_id)
            media.content = "A changed transcript."
            session.add(media)
            session.commit()
        return artifact

    scene.writer.generate = change_media
    with pytest.raises(RuntimeError, match="Selected media changed"):
        await pipeline.run()
    state = scene.snapshot(pipeline.digest_id)
    assert state.status == "failed" and state.rows == []
    assert state.seen == [] and state.receipts == []
    assert state.media_owner is None


@pytest.mark.asyncio
async def test_pending_receipt_survives_digest_deletion(scene, monkeypatch, tmp_path):
    from app.services import digest_deletion

    scene.remote.fail_mark = scene.mail.fail_mark = True
    pipeline = scene.new_pipeline()
    await pipeline.run()
    assert {r.state for r in scene.snapshot(pipeline.digest_id).receipts} == {"pending"}
    monkeypatch.setattr(digest_deletion, "engine", scene.database)
    digest_deletion.delete_digest(pipeline.digest_id, tmp_path)
    with Session(scene.database) as session:
        assert session.get(Digest, pipeline.digest_id) is None
        assert len(session.exec(select(SourceAcknowledgement)).all()) == 2


def test_binding_ignores_credential_rotation_but_detects_source_change(scene):
    original = wallabag_binding(scene.remote)
    scene.remote.settings = SimpleNamespace(
        **{**vars(scene.remote.settings), "wallabag_password": "rotated"}
    )
    assert wallabag_binding(scene.remote) == original
    scene.remote.settings.wallabag_username = "different-account"
    assert wallabag_binding(scene.remote) != original

    gmail_original = gmail_binding_for_account(scene.mail.account, scene.mail)
    scene.mail.settings = SimpleNamespace(
        **{**vars(scene.mail.settings), "gmail_client_secret": "rotated"}
    )
    assert gmail_binding_for_account(scene.mail.account, scene.mail) == gmail_original
    scene.mail.settings.gmail_label = "Another Label"
    assert gmail_binding_for_account(scene.mail.account, scene.mail) != gmail_original


def test_intents_dedupe_within_edition_but_can_recur_later(scene):
    binding = wallabag_binding(scene.remote)
    first, second = uuid4(), uuid4()
    with Session(scene.database) as session:
        add_intent(session, first, "wallabag", binding, "7")
        session.flush()
        add_intent(session, first, "wallabag", binding, "7")
        add_intent(session, second, "wallabag", binding, "7")
        session.commit()
    with Session(scene.database) as session:
        rows = session.exec(select(SourceAcknowledgement)).all()
        assert len(rows) == 2
        assert {row.digest_id for row in rows} == {first, second}
