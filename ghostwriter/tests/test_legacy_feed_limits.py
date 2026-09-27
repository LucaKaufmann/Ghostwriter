"""Pre-validation stored caps remain readable without changing durable state."""

import json
import socket
from uuid import UUID, uuid4

import pytest
from sqlmodel import Session

from app.core.database import engine
from app.models.feed import MAX_FEED_ARTICLES, Feed
from app.models.feed_sync import FeedMutationReceipt
from tests.test_feed_sync_v2 import binding, create, push, url


@pytest.fixture
def legacy_feed(client, monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, port, *a, **k: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.215.14", port))
    ])
    return create(client, url())


@pytest.mark.parametrize("stored", [-2, 2**31, 2**63 - 1])
def test_legacy_cap_reads_conflicts_and_noop_preserve_storage(client, legacy_feed, stored):
    feed = legacy_feed
    expected = min(MAX_FEED_ARTICLES, max(0, stored))
    with Session(engine) as session:
        row = session.get(Feed, UUID(feed["id"]))
        row.max_articles = stored
        session.add(row)
        session.commit()
    initial = binding(client)
    assert next(row for row in initial["changes"] if row["id"] == feed["id"])["max_articles"] == expected
    incremental = client.get("/api/feeds/changes-v2", params={
        "server_instance_id": initial["server_instance_id"], "since_version": 0,
    })
    assert incremental.status_code == 200
    assert next(row for row in incremental.json()["changes"] if row["id"] == feed["id"])["max_articles"] == expected
    assert next(row for row in client.get("/api/feeds").json() if row["id"] == feed["id"])["max_articles"] == expected
    assert client.get(f"/api/feeds/{feed['id']}").json()["max_articles"] == expected
    assert next(row for row in client.get("/api/feeds/changes").json()["feeds"] if row["id"] == feed["id"])["max_articles"] == expected
    conflict = client.put(f"/api/feeds/{feed['id']}", json={"title": "New"},
                          headers={"If-Match": '"0"'})
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["current"]["max_articles"] == expected
    projected = {key: feed[key] for key in ("url", "title", "mode", "is_active")}
    projected["max_articles"] = expected
    noop = client.post("/api/feeds/sync", json=[projected])
    assert noop.status_code == 200, noop.text
    assert noop.json()["unchanged"] == 1
    with Session(engine) as session:
        row = session.get(Feed, UUID(feed["id"]))
        assert (row.max_articles, row.version, row.updated_at.isoformat()) == (
            stored, feed["version"], feed["updated_at"])
    # A legitimate partial edit still returns a readable feed, without rewriting the cap.
    updated = client.put(f"/api/feeds/{feed['id']}", json={"title": "New"},
                         headers={"If-Match": f'"{feed["version"]}"'})
    assert updated.status_code == 200
    assert updated.json()["max_articles"] == expected
    with Session(engine) as session:
        assert session.get(Feed, UUID(feed["id"])).max_articles == stored


@pytest.mark.parametrize("receipt_status", ["applied", "conflict"])
@pytest.mark.parametrize("miss_preflight", [False, True])
def test_historical_receipt_projects_cap_without_rewriting_it(
    client, legacy_feed, monkeypatch, receipt_status, miss_preflight,
):
    feed = legacy_feed
    identity = binding(client)["server_instance_id"]
    item = {"op_id": str(uuid4()), "url": feed["url"], "kind": "upsert",
            "base_version": 0, "fields": {"title": "Proposal"}}
    response = push(client, identity, [item])
    assert response.status_code == 200
    with Session(engine) as session:
        receipt = session.get(FeedMutationReceipt, item["op_id"])
        historical = json.loads(receipt.result_json)
        historical["status"] = receipt_status
        historical["current"]["max_articles"] = 2**40
        saved_json = json.dumps(historical)
        receipt.result_json = saved_json
        session.add(receipt)
        session.commit()
    if miss_preflight:
        original_get = Session.get
        missed = False

        def get_after_concurrent_receipt(self, entity, ident, **kwargs):
            nonlocal missed
            if entity is FeedMutationReceipt and not missed:
                missed = True
                return None
            return original_get(self, entity, ident, **kwargs)

        monkeypatch.setattr(Session, "get", get_after_concurrent_receipt)
    first = push(client, identity, [item])
    second = push(client, identity, [item])
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    result = first.json()["results"][0]
    assert result["status"] == receipt_status
    assert result["current"]["max_articles"] == MAX_FEED_ARTICLES
    with Session(engine) as session:
        assert session.get(FeedMutationReceipt, item["op_id"]).result_json == saved_json
        row = session.get(Feed, UUID(feed["id"]))
        assert (row.title, row.version) == (feed["title"], feed["version"])
