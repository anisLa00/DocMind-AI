from src.models import DocumentStatus

CORPUS = (
    "Chapter 1: Revenue. European revenue grew by twelve percent in the third quarter.\n\n"
    "Chapter 2: Headcount. The engineering team grew from forty to fifty-five people.\n\n"
    "Chapter 3: Risks. Supply chain delays remain the most significant operational risk.\n"
)


async def upload_ready_document(client, headers, filename="report.txt"):
    response = await client.post(
        "/documents/upload",
        files={"file": (filename, CORPUS.encode(), "text/plain")},
        headers=headers,
    )
    document_id = response.json()["id"]

    indexed = await client.get(f"/documents/{document_id}", headers=headers)
    assert indexed.json()["status"] == DocumentStatus.READY, indexed.text
    return document_id


async def test_create_conversation(client, headers):
    document_id = await upload_ready_document(client, headers)

    response = await client.post(
        "/conversations/", json={"document_id": document_id}, headers=headers
    )
    body = response.json()

    assert response.status_code == 201
    assert body["document_id"] == document_id
    assert body["title"] == "Chat about report.txt"


async def test_create_conversation_with_a_custom_title(client, headers):
    document_id = await upload_ready_document(client, headers)

    response = await client.post(
        "/conversations/",
        json={"document_id": document_id, "title": "Q3 numbers"},
        headers=headers,
    )

    assert response.json()["title"] == "Q3 numbers"


async def test_cannot_chat_about_an_unindexed_document(client, user, headers, make_document):
    document = await make_document(user, status=DocumentStatus.PENDING)

    response = await client.post(
        "/conversations/", json={"document_id": str(document.id)}, headers=headers
    )

    assert response.status_code == 409
    assert "not ready" in response.json()["detail"]


async def test_cannot_chat_about_a_failed_document(client, user, headers, make_document):
    document = await make_document(user, status=DocumentStatus.FAILED)

    response = await client.post(
        "/conversations/", json={"document_id": str(document.id)}, headers=headers
    )
    assert response.status_code == 409


async def test_cannot_start_a_conversation_on_another_users_document(
    client, headers, make_user, auth_headers
):
    other = await make_user()
    document_id = await upload_ready_document(client, await auth_headers(other.email))

    response = await client.post(
        "/conversations/", json={"document_id": document_id}, headers=headers
    )
    assert response.status_code == 404


async def test_list_returns_only_the_callers_conversations(
    client, headers, make_user, auth_headers
):
    document_id = await upload_ready_document(client, headers)
    await client.post("/conversations/", json={"document_id": document_id}, headers=headers)

    other = await make_user()
    other_headers = await auth_headers(other.email)
    other_document = await upload_ready_document(client, other_headers, "theirs.txt")
    await client.post(
        "/conversations/", json={"document_id": other_document}, headers=other_headers
    )

    response = await client.get("/conversations/", headers=headers)

    assert len(response.json()) == 1
    assert response.json()[0]["document_id"] == document_id


async def test_rename_a_conversation(client, headers):
    document_id = await upload_ready_document(client, headers)
    conversation = await client.post(
        "/conversations/", json={"document_id": document_id}, headers=headers
    )
    conversation_id = conversation.json()["id"]

    response = await client.patch(
        f"/conversations/{conversation_id}", json={"title": "Renamed"}, headers=headers
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Renamed"


async def test_delete_a_conversation(client, headers):
    document_id = await upload_ready_document(client, headers)
    conversation_id = (
        await client.post("/conversations/", json={"document_id": document_id}, headers=headers)
    ).json()["id"]

    response = await client.delete(f"/conversations/{conversation_id}", headers=headers)

    assert response.status_code == 200
    assert (
        await client.get(f"/conversations/{conversation_id}", headers=headers)
    ).status_code == 404


async def test_deleting_a_document_removes_its_conversations(client, headers):
    document_id = await upload_ready_document(client, headers)
    conversation_id = (
        await client.post("/conversations/", json={"document_id": document_id}, headers=headers)
    ).json()["id"]

    await client.delete(f"/documents/{document_id}", headers=headers)

    response = await client.get(f"/conversations/{conversation_id}", headers=headers)
    assert response.status_code == 404


async def test_another_users_conversation_reads_as_missing(
    client, headers, make_user, auth_headers
):
    other = await make_user()
    other_headers = await auth_headers(other.email)
    document_id = await upload_ready_document(client, other_headers)
    conversation_id = (
        await client.post(
            "/conversations/", json={"document_id": document_id}, headers=other_headers
        )
    ).json()["id"]

    assert (
        await client.get(f"/conversations/{conversation_id}", headers=headers)
    ).status_code == 404
    assert (
        await client.delete(f"/conversations/{conversation_id}", headers=headers)
    ).status_code == 404


async def test_conversations_require_authentication(client):
    assert (await client.get("/conversations/")).status_code == 401
