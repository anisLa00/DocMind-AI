from tests.conftest import TEST_PASSWORD

SIGNUP = {
    "first_name": "Ada",
    "last_name": "Lovelace",
    "email": "ada@example.com",
    "password": "analytical-engine",
}


async def test_signup_creates_a_user(client):
    response = await client.post("/users/", json=SIGNUP)
    body = response.json()

    assert response.status_code == 201
    assert body["email"] == "ada@example.com"
    assert body["is_admin"] is False
    assert body["is_active"] is True


async def test_signup_never_returns_the_password(client):
    response = await client.post("/users/", json=SIGNUP)
    body = response.json()

    assert "password" not in body
    assert "password_hash" not in body
    assert SIGNUP["password"] not in response.text


async def test_signup_rejects_a_duplicate_email(client):
    assert (await client.post("/users/", json=SIGNUP)).status_code == 201

    response = await client.post("/users/", json={**SIGNUP, "first_name": "Someone"})
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


async def test_signup_rejects_a_duplicate_email_in_another_case(client):
    await client.post("/users/", json=SIGNUP)
    response = await client.post("/users/", json={**SIGNUP, "email": "ADA@example.com"})
    assert response.status_code == 409


async def test_signup_rejects_a_short_password(client):
    response = await client.post("/users/", json={**SIGNUP, "password": "short"})
    assert response.status_code == 422


async def test_signup_rejects_an_invalid_email(client):
    response = await client.post("/users/", json={**SIGNUP, "email": "not-an-email"})
    assert response.status_code == 422


async def test_me_returns_the_caller(client, user, headers):
    response = await client.get("/users/me", headers=headers)
    assert response.status_code == 200
    assert response.json()["id"] == str(user.id)


async def test_update_me(client, headers):
    response = await client.patch("/users/me", json={"first_name": "Renamed"}, headers=headers)
    assert response.status_code == 200
    assert response.json()["first_name"] == "Renamed"


async def test_update_me_rejects_a_taken_email(client, make_user, headers):
    other = await make_user(email="taken@example.com")

    response = await client.patch("/users/me", json={"email": other.email}, headers=headers)
    assert response.status_code == 409


async def test_change_password(client, user, headers):
    response = await client.post(
        "/users/me/password",
        json={"current_password": TEST_PASSWORD, "new_password": "brand-new-password"},
        headers=headers,
    )
    assert response.status_code == 200

    old = await client.post("/auth/login", json={"email": user.email, "password": TEST_PASSWORD})
    assert old.status_code == 401

    new = await client.post(
        "/auth/login", json={"email": user.email, "password": "brand-new-password"}
    )
    assert new.status_code == 200


async def test_change_password_requires_the_current_one(client, headers):
    response = await client.post(
        "/users/me/password",
        json={"current_password": "not-my-password", "new_password": "brand-new-password"},
        headers=headers,
    )
    assert response.status_code == 400


async def test_listing_users_requires_an_admin(client, headers):
    response = await client.get("/users/", headers=headers)
    assert response.status_code == 403


async def test_admin_can_list_users(client, make_user, auth_headers):
    admin = await make_user(email="admin@example.com", is_admin=True)
    await make_user(email="regular@example.com")

    response = await client.get("/users/", headers=await auth_headers(admin.email))
    assert response.status_code == 200
    assert len(response.json()) >= 2


async def test_lookup_by_email_requires_an_admin(client, user, headers):
    response = await client.get(f"/users/email/{user.email}", headers=headers)
    assert response.status_code == 403


async def test_a_user_cannot_read_another_user(client, make_user, headers):
    other = await make_user()
    response = await client.get(f"/users/id/{other.id}", headers=headers)
    assert response.status_code == 403


async def test_a_user_cannot_delete_another_user(client, make_user, headers):
    other = await make_user()
    response = await client.delete(f"/users/{other.id}", headers=headers)
    assert response.status_code == 403


async def test_a_user_can_delete_themselves(client, user, headers):
    response = await client.delete("/users/me", headers=headers)
    assert response.status_code == 200
    assert (await client.get("/auth/me", headers=headers)).status_code == 401


async def test_deleting_a_user_removes_their_documents(
    client, user, headers, make_document, session
):
    from sqlalchemy import select

    from src.models import Document

    user_id = user.id
    await make_document(user)
    assert (await client.delete("/users/me", headers=headers)).status_code == 200

    remaining = await session.execute(select(Document).where(Document.user_id == user_id))
    assert remaining.scalars().all() == []
