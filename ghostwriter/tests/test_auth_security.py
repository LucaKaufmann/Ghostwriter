def _register_user(client, username="admin", password="password123", email="admin@example.com"):
    return client.post(
        "/api/auth/register",
        json={"username": username, "password": password, "email": email},
    )


def test_auth_required_after_first_user(client):
    register = _register_user(client)
    assert register.status_code == 200
    token = register.json()["access_token"]

    no_auth = client.get("/api/feeds")
    assert no_auth.status_code == 401

    with_auth = client.get(
        "/api/feeds",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert with_auth.status_code == 200


def test_api_token_allows_access(client):
    register = _register_user(client)
    token = register.json()["access_token"]

    created = client.post(
        "/api/auth/tokens",
        json={"name": "test-token"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert created.status_code == 200
    api_token = created.json()["token"]

    response = client.get(
        "/api/feeds",
        headers={"X-API-Key": api_token},
    )
    assert response.status_code == 200


def test_login_rejects_invalid_password(client):
    register = _register_user(client)
    assert register.status_code == 200

    login = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "wrong-password"},
    )
    assert login.status_code == 401


def test_invalid_token_rejected_after_user_exists(client):
    register = _register_user(client)
    assert register.status_code == 200

    response = client.get(
        "/api/feeds",
        headers={"Authorization": "Bearer not-a-valid-token"},
    )
    assert response.status_code == 401
