"""Tests for health and system endpoints."""

def test_root(client):
    """Test root endpoint returns service info."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "Ghostwriter"
    assert "version" in data


def test_health(client):
    """Test health endpoint."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"

    # Full status is exposed under /api/health
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert "version" in data
    assert "ai_provider" in data


def test_config(client):
    """Test config endpoint."""
    response = client.get("/api/health/config")
    assert response.status_code == 200
    data = response.json()
    assert "timezone" in data
    assert "ai_provider" in data
    assert "schedule_enabled" in data
