from pathlib import Path

from src.models import DocumentStatus
from tests.factories import build_pdf


def upload(content: bytes, filename: str, content_type: str = "text/plain"):
    return {"file": (filename, content, content_type)}


async def test_upload_stores_the_document(client, headers, sample_text):
    response = await client.post(
        "/documents/upload",
        files=upload(sample_text.encode(), "report.txt"),
        headers=headers,
    )
    body = response.json()

    assert response.status_code == 201
    assert body["filename"] == "report.txt"
    assert body["file_size"] == len(sample_text.encode())
    assert Path(body["file_path"]).is_file()


async def test_upload_indexes_the_document(client, headers, sample_text):
    response = await client.post(
        "/documents/upload",
        files=upload(sample_text.encode(), "report.txt"),
        headers=headers,
    )
    document_id = response.json()["id"]

    # BackgroundTasks run before the ASGI response completes under the test
    # transport, so indexing has already finished by the time we get here.
    status_response = await client.get(f"/documents/{document_id}/status", headers=headers)
    body = status_response.json()

    assert body["status"] == DocumentStatus.READY
    assert body["chunk_count"] > 0
    assert body["error_message"] is None


async def test_upload_indexes_a_pdf(client, headers):
    pdf = build_pdf([["Revenue rose sharply."], ["Headcount stayed flat."]])

    response = await client.post(
        "/documents/upload",
        files=upload(pdf, "report.pdf", "application/pdf"),
        headers=headers,
    )
    document_id = response.json()["id"]

    body = (await client.get(f"/documents/{document_id}", headers=headers)).json()
    assert body["status"] == DocumentStatus.READY
    assert body["page_count"] == 2


async def test_upload_rejects_an_unsupported_type(client, headers):
    response = await client.post(
        "/documents/upload",
        files=upload(b"PK\x03\x04", "archive.zip", "application/zip"),
        headers=headers,
    )

    assert response.status_code == 415
    assert ".zip" in response.json()["detail"]


async def test_upload_rejects_a_file_without_an_extension(client, headers):
    response = await client.post(
        "/documents/upload", files=upload(b"data", "noextension"), headers=headers
    )
    assert response.status_code == 415


async def test_upload_rejects_an_oversized_file(client, headers):
    # The test configuration caps uploads at 1 MB.
    response = await client.post(
        "/documents/upload", files=upload(b"x" * (2 * 1024 * 1024), "big.txt"), headers=headers
    )

    assert response.status_code == 413


async def test_upload_rejects_an_empty_file(client, headers):
    response = await client.post(
        "/documents/upload", files=upload(b"", "empty.txt"), headers=headers
    )
    assert response.status_code == 413


async def test_a_hostile_filename_cannot_escape_the_upload_directory(client, headers, sample_text):
    response = await client.post(
        "/documents/upload",
        files=upload(sample_text.encode(), "../../../../etc/passwd.txt"),
        headers=headers,
    )
    body = response.json()

    assert response.status_code == 201
    stored = Path(body["file_path"]).resolve()
    assert stored.is_relative_to(Path("uploads").resolve()) or "uploads" in str(stored)
    assert ".." not in str(stored)


async def test_unindexable_file_is_marked_failed(client, headers):
    response = await client.post(
        "/documents/upload",
        files=upload(b"\x00\x00\x00", "binary.pdf", "application/pdf"),
        headers=headers,
    )
    document_id = response.json()["id"]

    body = (await client.get(f"/documents/{document_id}", headers=headers)).json()
    assert body["status"] == DocumentStatus.FAILED
    assert body["error_message"]


async def test_upload_requires_authentication(client, sample_text):
    response = await client.post(
        "/documents/upload", files=upload(sample_text.encode(), "report.txt")
    )
    assert response.status_code == 401


async def test_list_returns_only_the_callers_documents(
    client, user, headers, make_user, make_document
):
    await make_document(user, filename="mine.txt")
    other = await make_user()
    await make_document(other, filename="theirs.txt")

    response = await client.get("/documents/", headers=headers)
    body = response.json()

    assert response.status_code == 200
    assert [document["filename"] for document in body] == ["mine.txt"]


async def test_list_can_filter_by_status(client, user, headers, make_document):
    await make_document(user, filename="ready.txt", status=DocumentStatus.READY)
    await make_document(user, filename="failed.txt", status=DocumentStatus.FAILED)

    response = await client.get("/documents/?status=ready", headers=headers)

    assert [document["filename"] for document in response.json()] == ["ready.txt"]


async def test_another_users_document_reads_as_missing(client, headers, make_user, make_document):
    other = await make_user()
    document = await make_document(other)

    response = await client.get(f"/documents/{document.id}", headers=headers)
    assert response.status_code == 404


async def test_delete_removes_the_row_and_the_file(client, user, headers, make_document):
    document = await make_document(user)
    path = Path(document.file_path)
    assert path.is_file()

    response = await client.delete(f"/documents/{document.id}", headers=headers)

    assert response.status_code == 200
    assert not path.exists()
    assert (await client.get(f"/documents/{document.id}", headers=headers)).status_code == 404


async def test_delete_removes_the_chunks(client, headers, sample_text, session):
    import uuid

    from sqlalchemy import select

    from src.models import DocumentChunk

    upload_response = await client.post(
        "/documents/upload", files=upload(sample_text.encode(), "report.txt"), headers=headers
    )
    document_id = uuid.UUID(upload_response.json()["id"])

    await client.delete(f"/documents/{document_id}", headers=headers)

    remaining = await session.execute(
        select(DocumentChunk).where(DocumentChunk.document_id == document_id)
    )
    assert remaining.scalars().all() == []


async def test_cannot_delete_another_users_document(client, headers, make_user, make_document):
    other = await make_user()
    document = await make_document(other)

    response = await client.delete(f"/documents/{document.id}", headers=headers)

    assert response.status_code == 404
    assert Path(document.file_path).is_file()


async def test_reindex_reruns_the_pipeline(client, headers, sample_text):
    upload_response = await client.post(
        "/documents/upload", files=upload(sample_text.encode(), "report.txt"), headers=headers
    )
    document_id = upload_response.json()["id"]

    response = await client.post(f"/documents/{document_id}/reindex", headers=headers)
    assert response.status_code == 202

    body = (await client.get(f"/documents/{document_id}", headers=headers)).json()
    assert body["status"] == DocumentStatus.READY
    assert body["chunk_count"] > 0


async def test_chunks_endpoint_returns_indexed_text(client, headers, sample_text):
    upload_response = await client.post(
        "/documents/upload", files=upload(sample_text.encode(), "report.txt"), headers=headers
    )
    document_id = upload_response.json()["id"]

    response = await client.get(f"/documents/{document_id}/chunks", headers=headers)
    chunks = response.json()

    assert response.status_code == 200
    assert chunks
    assert [chunk["chunk_index"] for chunk in chunks] == sorted(
        chunk["chunk_index"] for chunk in chunks
    )
