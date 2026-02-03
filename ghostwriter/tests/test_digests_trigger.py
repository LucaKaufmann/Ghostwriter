def test_trigger_digest_conflict(monkeypatch, client):
    async def _fake_generate(_period):
        return None

    monkeypatch.setattr("app.api.digests.generate_digest", _fake_generate)

    response = client.post("/api/digests/trigger", json={"period": "manual"})
    assert response.status_code == 409
