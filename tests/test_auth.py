import pytest

from tests.conftest import TEST_PASSWORD


async def test_login_returns_both_tokens(client, user):
    response = await client.post(
        "/auth/login", json={"email": user.email, "password": TEST_PASSWORD}
    )
    body = response.json()

    assert response.status_code == 200
    assert body["token_type"] == "bearer"
    assert body["access_token"] and body["refresh_token"]
    assert body["access_token"] != body["refresh_token"]


@pytest.mark.parametrize("password", ["wrong-password", ""])
async def test_login_rejects_bad_credentials(client, user, password):
    response = await client.post("/auth/login", json={"email": user.email, "password": password})
    assert response.status_code in (401, 422)


async def test_login_is_case_insensitive_on_email(client, make_user):
    created = await make_user(email="Mixed.Case@Example.com")
    assert created.email == "mixed.case@example.com"

    response = await client.post(
        "/auth/login", json={"email": "MIXED.CASE@example.com", "password": TEST_PASSWORD}
    )
    assert response.status_code == 200


async def test_login_rejects_unknown_email(client):
    response = await client.post(
        "/auth/login", json={"email": "nobody@example.com", "password": TEST_PASSWORD}
    )
    assert response.status_code == 401


async def test_inactive_user_cannot_log_in(client, make_user):
    disabled = await make_user(is_active=False)
    response = await client.post(
        "/auth/login", json={"email": disabled.email, "password": TEST_PASSWORD}
    )
    assert response.status_code == 401


async def test_me_requires_a_token(client):
    response = await client.get("/auth/me")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


async def test_me_returns_the_caller(client, user, headers):
    response = await client.get("/auth/me", headers=headers)
    assert response.status_code == 200
    assert response.json()["email"] == user.email


async def test_refresh_token_is_rejected_as_an_access_token(client, user):
    login = await client.post("/auth/login", json={"email": user.email, "password": TEST_PASSWORD})
    refresh_token = login.json()["refresh_token"]

    response = await client.get("/auth/me", headers={"Authorization": f"Bearer {refresh_token}"})
    assert response.status_code == 401
    assert "access token" in response.json()["detail"].lower()


async def test_access_token_is_rejected_on_refresh(client, user, headers):
    response = await client.post("/auth/refresh", headers=headers)
    assert response.status_code == 401
    assert "refresh token" in response.json()["detail"].lower()


async def test_refresh_issues_a_new_access_token(client, user):
    login = await client.post("/auth/login", json={"email": user.email, "password": TEST_PASSWORD})
    refresh_token = login.json()["refresh_token"]

    response = await client.post(
        "/auth/refresh", headers={"Authorization": f"Bearer {refresh_token}"}
    )
    assert response.status_code == 200

    new_access = response.json()["access_token"]
    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {new_access}"})
    assert me.status_code == 200


async def test_logout_revokes_both_tokens(client, user):
    login = await client.post("/auth/login", json={"email": user.email, "password": TEST_PASSWORD})
    tokens = login.json()

    logout = await client.post(
        "/auth/logout",
        json={
            "refresh_token": tokens["refresh_token"],
            "access_token": tokens["access_token"],
        },
    )
    assert logout.status_code == 200

    reuse_access = await client.get(
        "/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert reuse_access.status_code == 401
    assert "revoked" in reuse_access.json()["detail"].lower()

    reuse_refresh = await client.post(
        "/auth/refresh", headers={"Authorization": f"Bearer {tokens['refresh_token']}"}
    )
    assert reuse_refresh.status_code == 401


async def test_garbage_token_is_rejected(client):
    response = await client.get("/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401


async def test_deleted_user_token_stops_working(client, user, headers, session):
    await session.delete(user)
    await session.commit()

    response = await client.get("/auth/me", headers=headers)
    assert response.status_code == 401
    assert "no longer exists" in response.json()["detail"].lower()
