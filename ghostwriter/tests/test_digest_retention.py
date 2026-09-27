"""Digest retention contract regression tests with synthetic storage."""

import asyncio
import os
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlmodel import Session, select

from app.core.database import engine
from app.models.article_feedback import ArticleFeedback
from app.models.digest import Digest, DigestArticle
from app.models.feed import Feed
from app.models.podcast_episode import PodcastEpisode
from app.models.schedule import Schedule
from app.worker.cleanup import cleanup_old_digests


def seeded(old=False):
    did, fid, aid = uuid4(), uuid4(), uuid4()
    name = f"{did}.epub"
    with Session(engine) as s:
        s.add(
            Feed(
                id=fid,
                url=f"https://example.test/{fid}",
                title="Feed",
                mode="raw",
                max_articles=1,
            )
        )
        s.add(
            Digest(
                id=did,
                filename=name,
                period="manual",
                status="completed",
                created_at=datetime.utcnow() - timedelta(days=400 if old else 0),
            )
        )
        s.add(
            DigestArticle(
                id=aid,
                digest_id=did,
                feed_id=fid,
                title="Source",
                url="one-off://source",
                mode="raw",
                content="private content",
            )
        )
        s.commit()
    output = Path(os.environ["OUTPUT_DIR"])
    output.mkdir(parents=True, exist_ok=True)
    epub, pdf = output / name, output / name.replace(".epub", ".pdf")
    epub.write_bytes(b"epub")
    pdf.write_bytes(b"pdf")
    return did, aid, fid, name, epub, pdf


@pytest.mark.parametrize("episode_status", ["pending", "processing", "failed", "ready"])
@pytest.mark.parametrize("reference", ["digest", "article"])
def test_episode_reference_blocks_manual_and_scheduled(
    client, episode_status, reference
):
    did, aid, _, name, epub, pdf = seeded(old=True)
    with Session(engine) as s:
        s.add(
            PodcastEpisode(
                status=episode_status,
                digest_ids=[str(did).upper()] if reference == "digest" else [],
                article_ids=[str(aid)] if reference == "article" else [],
            )
        )
        s.commit()
    assert client.delete(f"/api/digests/{name}").status_code == 409
    assert asyncio.run(cleanup_old_digests()) == 0
    with Session(engine) as s:
        assert s.get(Digest, did).status == "completed"
        assert s.get(DigestArticle, aid) is not None
    assert epub.exists() and pdf.exists()


def test_owned_rows_and_files_only(client):
    did, aid, fid, name, epub, pdf = seeded()
    unrelated = epub.parent / f"{uuid4()}.epub"
    unrelated.write_bytes(b"keep")
    cover = epub.parent / f"{uuid4()}.jpg"
    cover.write_bytes(b"shared cover")
    audio = epub.parent / f"{uuid4()}.mp3"
    audio.write_bytes(b"independent audio")
    from app.models.manual_cover import ManualCover

    cover_id, episode_id = uuid4(), uuid4()
    with Session(engine) as s:
        s.add(ArticleFeedback(article_id=aid, digest_id=did, rating="up"))
        s.add(Schedule(period="morning", last_run_digest_id=did))
        s.add(ManualCover(id=cover_id, name="Shared", file_name=cover.name))
        s.add(PodcastEpisode(id=episode_id, digest_ids=[], audio_path=str(audio)))
        s.commit()
    assert client.delete(f"/api/digests/{name}").status_code == 200
    with Session(engine) as s:
        assert s.get(Digest, did) is None
        assert s.get(DigestArticle, aid) is None
        assert (
            s.exec(
                select(ArticleFeedback).where(ArticleFeedback.article_id == aid)
            ).first()
            is None
        )
        assert s.get(Feed, fid) is not None
        assert s.get(ManualCover, cover_id) is not None
        assert s.get(PodcastEpisode, episode_id) is not None
        assert (
            s.exec(select(Schedule).where(Schedule.last_run_digest_id == did)).first()
            is None
        )
    assert not epub.exists() and not pdf.exists() and unrelated.exists()
    assert cover.read_bytes() == b"shared cover"
    assert audio.read_bytes() == b"independent audio"
    assert client.delete(f"/api/digests/{name}").status_code == 404


def test_missing_files_and_orphan(client):
    did, _, _, name, epub, pdf = seeded()
    epub.unlink()
    pdf.unlink()
    assert client.delete(f"/api/digests/{name}").status_code == 200
    orphan = epub.parent / f"{uuid4()}.epub"
    orphan.write_bytes(b"private")
    assert client.delete(f"/api/digests/{orphan.name}").status_code == 404
    assert client.get(f"/api/digests/{orphan.name}").status_code == 404
    assert orphan.read_bytes() == b"private"


def test_file_failure_marked_and_retryable(client, monkeypatch):
    did, aid, _, name, epub, pdf = seeded()
    original = Path.unlink

    def fail(path, *args, **kwargs):
        if path == pdf.resolve():
            raise PermissionError("synthetic")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail)
    assert client.delete(f"/api/digests/{name}").status_code == 503
    with Session(engine) as s:
        assert s.get(Digest, did).status == "deleting"
        assert s.get(DigestArticle, aid) is not None
    assert not epub.exists() and pdf.exists()
    assert client.get(f"/api/digests/{did}/articles").status_code == 404
    assert client.get(f"/api/digests/{did}/articles/{aid}/source").status_code == 404
    assert client.get(f"/api/digests/{did}/cover").status_code == 404
    assert client.get(f"/api/digests/{did}/status").status_code == 404
    assert client.get(f"/api/digests/{did}/download").status_code == 404
    assert client.get(f"/api/digests/{name}").status_code == 404
    assert all(item["id"] != str(did) for item in client.get("/api/digests").json())
    monkeypatch.setattr(Path, "unlink", original)
    assert client.delete(f"/api/digests/{name}").status_code == 200
    assert not pdf.exists()


def test_collision_and_symlink_conflict(client):
    did, _, _, name, epub, pdf = seeded()
    other = uuid4()
    with Session(engine) as s:
        s.add(Digest(id=other, filename=name, period="manual", status="completed"))
        s.commit()
    assert client.delete(f"/api/digests/{name}").status_code == 409
    with Session(engine) as s:
        s.delete(s.get(Digest, other))
        s.commit()
    epub.unlink()
    target = epub.parent / f"{uuid4()}.txt"
    target.write_bytes(b"keep")
    epub.symlink_to(target)
    assert client.delete(f"/api/digests/{name}").status_code == 409
    assert target.read_bytes() == b"keep"


def test_scheduled_cleanup_and_failed_manual(client):
    old_id, old_article, _, old_name, old_epub, old_pdf = seeded(old=True)
    assert asyncio.run(cleanup_old_digests()) == 1
    with Session(engine) as s:
        assert s.get(Digest, old_id) is None
        assert s.get(DigestArticle, old_article) is None
    assert not old_epub.exists() and not old_pdf.exists()
    failed_id, _, _, failed_name, _, _ = seeded()
    with Session(engine) as s:
        digest = s.get(Digest, failed_id)
        digest.status = "failed"
        s.add(digest)
        s.commit()
    assert client.delete(f"/api/digests/{failed_name}").status_code == 200


def test_media_pointer_cleared_without_reconsumption(client):
    from app.models.media_item import MediaItem

    did, _, _, name, _, _ = seeded()
    media_id = uuid4()
    consumed_at = datetime.utcnow()
    with Session(engine) as s:
        s.add(
            MediaItem(
                id=media_id,
                media_feed_id=uuid4(),
                guid=str(media_id),
                url="https://example.test/media",
                title="Transcript",
                content="independent transcript",
                consumed_at=consumed_at,
                consumed_digest_id=did,
            )
        )
        s.commit()
    assert client.delete(f"/api/digests/{name}").status_code == 200
    with Session(engine) as s:
        media = s.get(MediaItem, media_id)
        assert media.content == "independent transcript"
        assert media.consumed_at == consumed_at
        assert media.consumed_digest_id is None


def test_final_transaction_failure_retries_without_content(client, monkeypatch):
    from app.services import digest_deletion

    did, aid, _, name, epub, pdf = seeded()
    original = digest_deletion.immediate_session
    calls = 0

    def fail_final():
        nonlocal calls
        calls += 1
        if calls == 4:
            raise OSError("synthetic final transaction failure")
        return original()

    monkeypatch.setattr(digest_deletion, "immediate_session", fail_final)
    assert client.delete(f"/api/digests/{name}").status_code == 503
    with Session(engine) as s:
        assert s.get(Digest, did).status == "deleting"
        assert s.get(DigestArticle, aid) is not None
    assert not epub.exists() and not pdf.exists()
    monkeypatch.setattr(digest_deletion, "immediate_session", original)
    assert client.delete(f"/api/digests/{name}").status_code == 200


def test_feedback_write_rechecks_marked_parent(client):
    from app.models.article_feedback import ArticleFeedbackUpsert
    from app.services.podcast_service import podcast_service

    did, aid, _, name, _, pdf = seeded()
    with Session(engine) as s:
        article = s.get(DigestArticle, aid)
        # Preserve a stale article object while deletion claims its parent.
        original = Path.unlink

        def fail_pdf(path, *args, **kwargs):
            if path == pdf.resolve():
                raise PermissionError("synthetic")
            return original(path, *args, **kwargs)

        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(Path, "unlink", fail_pdf)
            assert client.delete(f"/api/digests/{name}").status_code == 503
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            podcast_service.upsert_feedback(
                s, article, ArticleFeedbackUpsert(rating="up")
            )
        assert exc_info.value.status_code == 409
    with Session(engine) as s:
        assert (
            s.exec(
                select(ArticleFeedback).where(ArticleFeedback.article_id == aid)
            ).first()
            is None
        )


def test_collision_in_pdf_claims_blocks_service(client):
    from app.services.digest_deletion import DeletionConflict, delete_digest

    did, _, _, name, epub, pdf = seeded()
    other = uuid4()
    with Session(engine) as s:
        s.add(Digest(id=other, filename=pdf.name, period="manual", status="completed"))
        s.commit()
    with pytest.raises(DeletionConflict):
        delete_digest(did, os.environ["OUTPUT_DIR"])
    with Session(engine) as s:
        assert s.get(Digest, did).status == "completed"
    assert epub.exists() and pdf.exists()


def test_queue_and_deletion_serialize_on_writer(client, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from app.services.digest_deletion import DeletionConflict, delete_digest
    from app.services.podcast_service import podcast_service

    did, _, _, _, _, _ = seeded()
    entered, release = Event(), Event()
    original = podcast_service._queue_episode_generation_locked

    def paused(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return original(*args, **kwargs)

    monkeypatch.setattr(podcast_service, "_queue_episode_generation_locked", paused)
    monkeypatch.setattr(podcast_service, "_schedule_episode_task", lambda _id: None)

    def queue():
        with Session(engine) as s:
            return podcast_service.queue_episode_generation(s, did).id

    with ThreadPoolExecutor(max_workers=2) as pool:
        queued = pool.submit(queue)
        assert entered.wait(5)
        deletion = pool.submit(delete_digest, did, os.environ["OUTPUT_DIR"])
        release.set()
        episode_id = queued.result(timeout=5)
        with pytest.raises(DeletionConflict):
            deletion.result(timeout=5)
    with Session(engine) as s:
        assert s.get(PodcastEpisode, episode_id) is not None
        assert s.get(Digest, did).status == "completed"


def test_pdf_render_and_deletion_share_publication_gate(client, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from app.models.client_config import ClientConfig
    from app.services.pdf_generator import PdfGenerator

    did, _, _, name, _, pdf = seeded()
    pdf.unlink()
    from sqlmodel import delete as sql_delete

    with Session(engine) as s:
        s.exec(sql_delete(ClientConfig))
        s.add(ClientConfig(pdf_enabled=True, pdf_page_size="A4"))
        s.commit()
    entered, release = Event(), Event()

    def render(self, *, output_filename, **_kwargs):
        temporary = Path(os.environ["OUTPUT_DIR"]) / output_filename
        temporary.write_bytes(b"%PDFsynthetic")
        entered.set()
        assert release.wait(5)
        return str(temporary)

    monkeypatch.setattr(PdfGenerator, "generate", render)
    with ThreadPoolExecutor(max_workers=2) as pool:
        download = pool.submit(client.get, f"/api/digests/{did}/download?format=pdf")
        assert entered.wait(5)
        deletion = pool.submit(client.delete, f"/api/digests/{name}")
        release.set()
        response = download.result(timeout=5)
        deleted = deletion.result(timeout=5)
    assert response.status_code == 200
    assert response.content == b"%PDFsynthetic"
    assert deleted.status_code == 200
    assert not pdf.exists()


def test_opened_download_survives_concurrent_unlink(client):
    from app.api.digests import _stream_open_file
    from app.services.digest_deletion import delete_digest

    did, _, _, name, epub, _ = seeded()
    response = _stream_open_file(epub, name, "application/epub+zip")
    ranged = _stream_open_file(epub, name, "application/epub+zip")
    delete_digest(did, os.environ["OUTPUT_DIR"])

    async def read(opened_response, headers):
        events = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(event):
            events.append(event)

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": headers,
            "extensions": {},
        }
        await opened_response(scope, receive, send)
        return b"".join(
            event["body"] for event in events if event["type"] == "http.response.body"
        )

    assert asyncio.run(read(response, [])) == b"epub"
    assert asyncio.run(read(ranged, [(b"range", b"bytes=1-2")])) == b"pu"
    assert not epub.exists()


def test_processing_digest_conflicts_without_mutation(client):
    did, _, _, name, epub, pdf = seeded()
    with Session(engine) as s:
        digest = s.get(Digest, did)
        digest.status = "processing"
        s.add(digest)
        s.commit()
    assert client.delete(f"/api/digests/{name}").status_code == 409
    with Session(engine) as s:
        assert s.get(Digest, did).status == "processing"
    assert epub.exists() and pdf.exists()


def test_private_one_off_without_episode_stays_private_during_failed_cleanup(
    client, monkeypatch
):
    did, aid, _, name, epub, pdf = seeded(old=True)
    with Session(engine) as s:
        feed = s.exec(select(Feed).where(Feed.url == "synthetic://one-off")).first()
        if feed is None:
            feed = Feed(
                url="synthetic://one-off",
                title="One-off Podcast",
                mode="raw",
                max_articles=1,
            )
            s.add(feed)
            s.flush()
        article = s.get(DigestArticle, aid)
        article.feed_id = feed.id
        s.add(article)
        s.commit()
    original = Path.unlink

    def fail_pdf(path, *args, **kwargs):
        if path == pdf.resolve():
            raise PermissionError("synthetic")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_pdf)
    asyncio.run(cleanup_old_digests())
    with Session(engine) as s:
        assert s.get(Digest, did).status == "deleting"
        assert s.get(DigestArticle, aid) is not None
    assert not epub.exists() and pdf.exists()
    assert client.get(f"/api/digests/{did}/articles").status_code == 404
    assert client.get(f"/api/digests/{name}").status_code == 404
    monkeypatch.setattr(Path, "unlink", original)
    assert asyncio.run(cleanup_old_digests()) >= 1
    with Session(engine) as s:
        assert s.get(Digest, did) is None


def test_failed_digest_with_empty_filename_deletes_by_id(client):
    did = uuid4()
    with Session(engine) as s:
        s.add(Digest(id=did, filename="", period="manual", status="failed"))
        s.commit()
    assert client.delete(f"/api/digests/{did}").status_code == 200
    with Session(engine) as s:
        assert s.get(Digest, did) is None
    assert client.delete(f"/api/digests/{did}").status_code == 404
