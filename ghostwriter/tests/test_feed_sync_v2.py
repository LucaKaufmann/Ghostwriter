"""Versioned feed sync, durable replay, and legacy safety fixtures."""

import asyncio
import socket
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlmodel import Session, select

from app.core.config import get_settings
from app.core.database import engine
from app.models.client_settings import ClientSettings
from app.models.feed import Feed
from app.models.feed_sync import FeedMutationReceipt
from app.services.content_processor import ContentProcessor
from app.services.outbound_fetch import FetchedResource
from app.worker.cleanup import cleanup_old_tombstones


@pytest.fixture
def public_dns(monkeypatch, block_real_network):
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, port, *a, **k: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.215.14", port))
    ])


def url():
    return f"https://example.com/{uuid4()}.xml"


def create(client, value):
    response = client.post("/api/feeds", json={"url": value, "title": "One", "mode": "raw",
                                               "is_active": True, "max_articles": 5})
    assert response.status_code == 200, response.text
    return response.json()


def binding(client):
    response = client.get("/api/feeds/changes-v2")
    assert response.status_code == 200
    return response.json()


def test_incremental_pull_requires_matching_identity_and_records_activity(client):
    initial = binding(client)
    with Session(engine) as session:
        recorded = session.exec(select(ClientSettings)).one().last_feed_sync_at
    assert recorded is not None
    missing = client.get("/api/feeds/changes-v2", params={"since_version": 0})
    assert missing.status_code == 422
    rotated = client.get("/api/feeds/changes-v2", params={
        "since_version": 0, "server_instance_id": str(uuid4()),
    })
    assert rotated.status_code == 409
    with Session(engine) as session:
        assert session.exec(select(ClientSettings)).one().last_feed_sync_at == recorded
    valid = client.get("/api/feeds/changes-v2", params={
        "since_version": initial["server_version"],
        "server_instance_id": initial["server_instance_id"],
    })
    assert valid.status_code == 200
    with Session(engine) as session:
        assert session.exec(select(ClientSettings)).one().last_feed_sync_at >= recorded


def test_duplicate_web_create_returns_conflict_before_dns(client, public_dns, monkeypatch):
    value = url()
    create(client, value)

    async def no_dns(_url):
        raise AssertionError("duplicate feed must not resolve DNS")

    monkeypatch.setattr("app.api.feeds.validate_public_url_bounded", no_dns)
    duplicate = client.post("/api/feeds", json={"url": value, "title": "Again"})
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "feed_conflict"


@pytest.mark.parametrize("change", ["update", "delete"])
def test_legacy_snapshot_rechecks_after_dns_wait(client, public_dns, monkeypatch, change):
    value = url()
    feed = create(client, value)
    entered = threading.Event()
    release = threading.Event()
    validations = 0
    lock = threading.Lock()

    async def gated_validation(_url):
        nonlocal validations
        with lock:
            validations += 1
            first = validations == 1
        if first:
            entered.set()
            assert await asyncio.to_thread(release.wait, 3)

    monkeypatch.setattr("app.api.feeds._validate_feed_url", gated_validation)
    snapshot = {"url": value, "title": "One", "mode": "raw",
                "is_active": True, "max_articles": 5}
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(client.post, "/api/feeds/sync", json=[snapshot])
            assert entered.wait(2)
            headers = {"If-Match": f'"{feed["version"]}"'}
            if change == "update":
                changed = client.put(f"/api/feeds/{feed['id']}", json={"title": "New"},
                                     headers=headers)
            else:
                changed = client.delete(f"/api/feeds/{feed['id']}", headers=headers)
            assert changed.status_code == 200
            release.set()
            result = pending.result(timeout=3)
            assert result.status_code == 409
            assert result.json()["detail"]["code"] == "legacy_write_requires_upgrade"
    finally:
        release.set()


def test_concurrent_creates_return_success_and_active_conflict(client, monkeypatch):
    value = url()
    both_ready = threading.Event()
    release = threading.Event()
    lock = threading.Lock()
    validations = 0

    async def gated_validation(_url):
        nonlocal validations
        with lock:
            validations += 1
            if validations == 2:
                both_ready.set()
        assert await asyncio.to_thread(release.wait, 3)

    monkeypatch.setattr("app.api.feeds._validate_feed_url", gated_validation)
    body = {"url": value, "title": "Concurrent", "mode": "raw",
            "is_active": True, "max_articles": 5}
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(client.post, "/api/feeds", json=body)
            second = pool.submit(client.post, "/api/feeds", json=body)
            assert both_ready.wait(2)
            release.set()
            responses = [first.result(timeout=3), second.result(timeout=3)]
    finally:
        release.set()
    assert sorted(response.status_code for response in responses) == [200, 409]
    conflict = next(response for response in responses if response.status_code == 409)
    assert conflict.json()["detail"]["code"] == "feed_conflict"


def test_web_create_dns_does_not_block_other_requests(client, monkeypatch):
    started = threading.Event()
    release = threading.Event()

    def resolve(host, port, *args, **kwargs):
        if host == "slow.example.com":
            started.set()
            assert release.wait(5)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.215.14", port))]

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            slow = pool.submit(client.post, "/api/feeds", json={
                "url": "https://slow.example.com/web-rss", "title": "Slow",
            })
            assert started.wait(2)
            fast = pool.submit(client.post, "/api/feeds", json={
                "url": "https://fast.example.com/web-rss", "title": "Fast",
            })
            assert fast.result(timeout=2).status_code == 200
            assert client.get("/api/health").status_code == 200
            assert not slow.done()
            release.set()
            assert slow.result(timeout=3).status_code == 200
    finally:
        release.set()


def test_web_create_dns_deadline_returns_without_persisting(client, monkeypatch):
    from app.services import outbound_fetch

    started = threading.Event()
    release = threading.Event()

    def resolve(host, port, *args, **kwargs):
        started.set()
        assert release.wait(3)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.215.14", port))]

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    settings = get_settings().model_copy(update={"fetch_timeout_seconds": 0.1})
    monkeypatch.setattr(outbound_fetch, "get_settings", lambda: settings)
    value = f"https://timeout.example.com/{uuid4()}.xml"
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            request = pool.submit(client.post, "/api/feeds", json={
                "url": value, "title": "Timed out",
            })
            assert started.wait(1)
            assert request.result(timeout=1).status_code == 504
    finally:
        release.set()
    with Session(engine) as session:
        assert session.exec(select(Feed).where(Feed.url == value)).first() is None


def push(client, identity, items):
    return client.post("/api/feeds/mutations-v2", json={"server_instance_id": identity,
                                                       "mutations": items})


def test_v2_cas_replay_tombstones(client, public_dns, monkeypatch):
    value = url()
    feed = create(client, value)
    identity = binding(client)["server_instance_id"]
    web = client.put(f"/api/feeds/{feed['id']}", json={"title": "Web"},
                     headers={"If-Match": f'"{feed["version"]}"'})
    assert web.status_code == 200, web.text
    stale = {"op_id": str(uuid4()), "url": value, "kind": "upsert",
             "base_version": feed["version"], "fields": {"title": "Stale"}}
    fresh_url = url()
    good = {"op_id": str(uuid4()), "url": fresh_url, "kind": "upsert",
            "base_version": None, "fields": {"title": "New", "is_active": True,
                                              "mode": "raw", "max_articles": 0}}
    response = push(client, identity, [stale, good])
    assert response.status_code == 200, response.text
    conflict, applied = response.json()["results"]
    assert conflict["status"] == "conflict" and conflict["current"]["title"] == "Web"
    assert applied["status"] == "applied" and applied["current"]["max_articles"] == 0
    async def no_dns(_url):
        raise AssertionError("receipt replay must not resolve DNS")

    with monkeypatch.context() as scoped:
        scoped.setattr("app.services.feed_sync.validate_public_url_bounded", no_dns)
        assert push(client, identity, [good]).json()["results"][0] == applied
    altered = {**good, "fields": {**good["fields"], "title": "Changed"}}
    assert push(client, identity, [altered]).json()["results"][0]["code"] == "op_id_reused"
    delete = {"op_id": str(uuid4()), "url": fresh_url, "kind": "delete",
              "base_version": applied["current"]["version"]}
    tombstone = push(client, identity, [delete]).json()["results"][0]
    assert tombstone["current"]["kind"] == "tombstone"
    assert push(client, identity, [delete]).json()["results"][0] == tombstone
    duplicate_delete = {**delete, "op_id": str(uuid4()),
                        "base_version": tombstone["current"]["version"]}
    acknowledged = push(client, identity, [duplicate_delete]).json()["results"][0]
    assert acknowledged["status"] == "applied"
    assert acknowledged["current"]["version"] == tombstone["current"]["version"]
    stale_delete = {**delete, "op_id": str(uuid4())}
    assert push(client, identity, [stale_delete]).json()["results"][0]["status"] == "conflict"
    changes = client.get("/api/feeds/changes-v2", params={"since_version": feed["version"],
                                                       "server_instance_id": identity}).json()
    assert changes["changes"][-1] == tombstone["current"]
    with Session(engine) as session:
        assert session.exec(select(FeedMutationReceipt).where(
            FeedMutationReceipt.op_id == good["op_id"])).first()


def test_legacy_guards_and_restore(client, public_dns):
    value = url()
    feed = create(client, value)
    assert client.post("/api/feeds/sync", json=[{"url": value, "title": "One", "mode": "raw",
                                                  "is_active": True, "max_articles": 5}]).status_code == 200
    assert client.post("/api/feeds/sync", json=[{"url": value, "title": "Changed"}]).status_code == 409
    assert client.put(f"/api/feeds/{feed['id']}", json={"title": "Changed"}).status_code == 428
    assert client.delete(f"/api/feeds/{feed['id']}").status_code == 428
    deleted = client.delete(f"/api/feeds/{feed['id']}",
                            headers={"If-Match": f'"{feed["version"]}"'})
    assert deleted.status_code == 200
    tombstone = next(row for row in binding(client)["changes"] if row["url"] == value)
    assert tombstone["kind"] == "tombstone"
    body = {"url": value, "title": "Restored", "mode": "raw", "max_articles": 0}
    response = client.post("/api/feeds", json=body)
    assert response.status_code == 428
    assert response.json()["detail"]["current"] == tombstone
    restored = client.post("/api/feeds", json=body,
                           headers={"If-Match": f'"{tombstone["version"]}"'})
    assert restored.status_code == 200
    assert restored.json()["id"] == feed["id"]


def test_envelope_and_item_validation(client, public_dns):
    identity = binding(client)["server_instance_id"]
    item = {"op_id": str(uuid4()), "url": url(), "kind": "upsert", "base_version": None,
            "fields": {"title": "New", "is_active": True, "mode": "raw", "max_articles": 5}}
    assert push(client, str(uuid4()), [item]).status_code == 409
    assert push(client, identity, [item, item]).status_code == 422
    assert push(client, identity, [item] * 101).status_code == 422
    assert push(client, identity, [{**item, "op_id": "bad"}]).status_code == 422
    assert client.post("/api/feeds/mutations-v2", json={"server_instance_id": identity}).status_code == 422
    assert client.post("/api/feeds/mutations-v2", json={"server_instance_id": identity,
                                                      "mutations": {}}).status_code == 422
    bad = {**item, "op_id": str(uuid4()), "fields": {**item["fields"], "max_articles": -1}}
    assert push(client, identity, [bad]).json()["results"][0]["code"] == "invalid_fields"
    unknown = {**item, "op_id": str(uuid4()), "unexpected": "field"}
    assert push(client, identity, [unknown]).json()["results"][0]["code"] == "invalid_fields"
    fractional = {**item, "op_id": str(uuid4()), "base_version": 1.5}
    assert push(client, identity, [fractional]).json()["results"][0]["code"] == "invalid_fields"
    assert push(client, identity, [item]).json()["results"][0]["status"] == "applied"


def test_legacy_zero_to_ten_mapping_cannot_overwrite(client, public_dns):
    value = url()
    feed = create(client, value)
    changed = client.put(f"/api/feeds/{feed['id']}", json={"max_articles": 0},
                         headers={"If-Match": f'"{feed["version"]}"'})
    assert changed.status_code == 200
    payload = {"url": value, "title": "One", "mode": "raw",
               "is_active": True, "max_articles": 10}
    assert client.post("/api/feeds/sync", json=[payload]).status_code == 409
    assert client.get(f"/api/feeds/{feed['id']}").json()["max_articles"] == 0


def test_existing_dead_domain_can_update_and_delete_without_dns(client, public_dns, monkeypatch):
    value = url()
    feed = create(client, value)
    identity = binding(client)["server_instance_id"]

    async def no_dns(_url):
        raise AssertionError("stored feed identity must not require DNS")

    with monkeypatch.context() as scoped:
        scoped.setattr("app.services.feed_sync.validate_public_url_bounded", no_dns)
        edit = {"op_id": str(uuid4()), "url": value, "kind": "upsert",
                "base_version": feed["version"], "fields": {"title": "Still mine"}}
        updated = push(client, identity, [edit]).json()["results"][0]
        assert updated["status"] == "applied"
        assert updated["current"]["title"] == "Still mine"
        delete = {"op_id": str(uuid4()), "url": value, "kind": "delete",
                  "base_version": updated["current"]["version"]}
        removed = push(client, identity, [delete]).json()["results"][0]
        assert removed["status"] == "applied"
        assert removed["current"]["kind"] == "tombstone"
        never_seen = {"op_id": str(uuid4()), "url": "https://dead.example.com/rss",
                      "kind": "delete", "base_version": None}
        assert push(client, identity, [never_seen]).json()["results"][0] == {
            "op_id": never_seen["op_id"], "status": "applied", "current": None,
        }


def test_web_metadata_put_does_not_revalidate_immutable_feed_url(client, public_dns, monkeypatch):
    feed = create(client, url())

    async def failed_dns(_url):
        raise AssertionError("metadata-only PUT must not resolve the stored URL")

    monkeypatch.setattr("app.api.feeds._validate_feed_url", failed_dns)
    edited = client.put(f"/api/feeds/{feed['id']}",
                        json={"title": "Unreachable feed", "is_active": False},
                        headers={"If-Match": f'"{feed["version"]}"'})
    assert edited.status_code == 200
    assert edited.json()["title"] == "Unreachable feed"
    assert edited.json()["is_active"] is False
    stale = client.put(f"/api/feeds/{feed['id']}", json={"title": "Stale edit"},
                       headers={"If-Match": f'"{feed["version"]}"'})
    assert stale.status_code == 409
    assert client.get(f"/api/feeds/{feed['id']}").json()["title"] == "Unreachable feed"


def test_web_put_cannot_implicitly_restore_tombstone(client, public_dns):
    value = url()
    feed = create(client, value)
    deleted = client.delete(f"/api/feeds/{feed['id']}",
                            headers={"If-Match": f'"{feed["version"]}"'})
    assert deleted.status_code == 200
    tombstone = next(row for row in binding(client)["changes"] if row["url"] == value)
    retry = client.put(f"/api/feeds/{feed['id']}", json={"title": "Accidental restore"},
                       headers={"If-Match": f'"{tombstone["version"]}"'})
    assert retry.status_code == 409
    assert retry.json()["detail"]["current"] == tombstone
    assert next(row for row in binding(client)["changes"] if row["url"] == value) == tombstone


def test_synthetic_rows_stay_internal_and_unversioned(client, public_dns):
    synthetic = f"synthetic://test-{uuid4()}"
    with Session(engine) as session:
        session.add(Feed(url=synthetic, title="Internal", is_active=True, mode="raw"))
        session.commit()
    assert all(row["url"] != synthetic for row in binding(client)["changes"])
    assert all(row["url"] != synthetic for row in client.get("/api/feeds").json())
    assert all(row["url"] != synthetic for row in client.get("/api/feeds/changes").json()["feeds"])
    identity = binding(client)["server_instance_id"]
    item = {"op_id": str(uuid4()), "url": synthetic, "kind": "delete", "base_version": 0}
    assert push(client, identity, [item]).json()["results"][0]["code"] == "invalid_url"
    with Session(engine) as session:
        assert session.exec(select(Feed).where(Feed.url == synthetic)).one().version == 0


@pytest.mark.asyncio
async def test_tombstones_survive_cleanup(client, public_dns):
    value = url()
    feed = create(client, value)
    client.delete(f"/api/feeds/{feed['id']}", headers={"If-Match": f'"{feed["version"]}"'})
    assert await cleanup_old_tombstones() == 0
    with Session(engine) as session:
        assert session.exec(select(Feed).where(Feed.url == value)).first().deleted_at is not None


@pytest.mark.asyncio
async def test_synced_zero_limit_reaches_all_feed_entries(client, public_dns, monkeypatch):
    identity = binding(client)["server_instance_id"]
    value = url()
    op = {"op_id": str(uuid4()), "url": value, "kind": "upsert", "base_version": None,
          "fields": {"title": "Unlimited", "is_active": True,
                     "mode": "raw", "max_articles": 0}}
    assert push(client, identity, [op]).json()["results"][0]["status"] == "applied"
    with Session(engine) as session:
        feed = session.exec(select(Feed).where(Feed.url == value)).one()
        limit = feed.max_articles
    entries = [{"id": str(i), "link": f"https://example.com/article-{i}",
                "title": f"Article {i}"} for i in range(3)]
    monkeypatch.setattr("feedparser.parse", lambda *a, **k: SimpleNamespace(bozo=False, entries=entries))

    async def fetch(url, **kwargs):
        return FetchedResource(url, "application/rss+xml", "utf-8", b"<rss/>")

    monkeypatch.setattr("app.services.content_processor.fetch_resource", fetch)
    articles = await ContentProcessor().parse_feed(value, max_entries=limit)
    assert [article.url for article in articles] == [entry["link"] for entry in entries]


def test_gated_dns_does_not_hold_writer_lock_or_leave_receipt(client, monkeypatch):
    identity = binding(client)["server_instance_id"]
    started = threading.Event()
    release = threading.Event()

    def resolve(host, port, *args, **kwargs):
        if host == "slow.example.com":
            started.set()
            assert release.wait(5)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.215.14", port))]

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    settings = get_settings().model_copy(update={"fetch_timeout_seconds": 1.5})
    monkeypatch.setattr("app.services.outbound_fetch.get_settings", lambda: settings)
    slow = {"op_id": str(uuid4()), "url": "https://slow.example.com/rss", "kind": "upsert",
            "base_version": None,
            "fields": {"title": "Slow", "is_active": True, "mode": "raw", "max_articles": 5}}
    fast = {**slow, "op_id": str(uuid4()), "url": "https://fast.example.com/rss"}
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            slow_future = pool.submit(push, client, identity, [slow])
            assert started.wait(2)
            fast_future = pool.submit(push, client, identity, [fast])
            assert fast_future.result(timeout=1).json()["results"][0]["status"] == "applied"
            assert client.get("/api/health").status_code == 200
            assert not slow_future.done()
            assert slow_future.result(timeout=3).status_code == 503
    finally:
        release.set()
    with Session(engine) as session:
        assert session.get(FeedMutationReceipt, slow["op_id"]) is None
        assert session.exec(select(Feed).where(Feed.url == slow["url"])).first() is None

@pytest.mark.parametrize("cap", [-1, 2**31, 2**63])
def test_feed_cap_outside_native_range_never_changes_feed(client, public_dns, cap):
    value = url()
    fields = {"url": value, "title": "Range", "mode": "raw", "is_active": True,
              "max_articles": cap}
    assert client.post("/api/feeds", json=fields).status_code == 422
    assert client.post("/api/feeds/sync", json=[fields]).status_code == 422
    feed = create(client, value)
    identity = binding(client)["server_instance_id"]
    assert client.put(f"/api/feeds/{feed['id']}", json={"max_articles": cap},
                      headers={"If-Match": f'"{feed["version"]}"'}).status_code == 422
    rejected = push(client, identity, [{"op_id": str(uuid4()), "url": value,
        "kind": "upsert", "base_version": feed["version"],
        "fields": {"max_articles": cap}}])
    assert rejected.status_code == 200
    assert rejected.json()["results"][0]["status"] == "rejected"
    current = client.get(f"/api/feeds/{feed['id']}").json()
    assert current["max_articles"] == 5
    assert current["version"] == feed["version"]


def test_largest_native_feed_cap_roundtrips_through_web_and_v2(client, public_dns):
    value = url()
    maximum = 2**31 - 1
    created = client.post("/api/feeds", json={"url": value, "title": "Largest", "max_articles": maximum})
    assert created.status_code == 200
    feed = created.json()
    snapshot = binding(client)
    assert next(item for item in snapshot["changes"] if item["url"] == value)["max_articles"] == maximum
    changed = push(client, snapshot["server_instance_id"], [{"op_id": str(uuid4()),
        "url": value, "kind": "upsert", "base_version": feed["version"],
        "fields": {"max_articles": 0}}])
    assert changed.status_code == 200
    current = changed.json()["results"][0]["current"]
    assert current["max_articles"] == 0
    changed_again = push(client, snapshot["server_instance_id"], [{"op_id": str(uuid4()),
        "url": value, "kind": "upsert", "base_version": current["version"],
        "fields": {"max_articles": maximum}}])
    assert changed_again.json()["results"][0]["current"]["max_articles"] == maximum
