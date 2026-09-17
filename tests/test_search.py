"""Retrieval quality and access scoping for chunk search."""

from src.models import DocumentStatus

CORPUS = (
    "Chapter 1: Revenue. European revenue grew by twelve percent in the third quarter, "
    "driven by demand in Germany and France.\n\n"
    "Chapter 2: Headcount. The engineering team grew from forty to fifty-five people.\n\n"
    "Chapter 3: Risks. Supply chain delays remain the most significant operational risk.\n"
)


async def _upload(client, headers, text=CORPUS, filename="report.txt"):
    """Upload a document and wait for it to be indexed.

    The upload response is serialised before the background task runs, so the
    document's final state comes from a follow-up read.
    """
    response = await client.post(
        "/documents/upload",
        files={"file": (filename, text.encode(), "text/plain")},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    document_id = response.json()["id"]

    indexed = await client.get(f"/documents/{document_id}", headers=headers)
    assert indexed.json()["status"] == DocumentStatus.READY, indexed.text
    return document_id


async def test_search_returns_scored_results(client, headers):
    await _upload(client, headers)

    response = await client.post(
        "/chunks/search", json={"query": "European revenue growth", "top_k": 3}, headers=headers
    )
    results = response.json()

    assert response.status_code == 200
    assert results
    assert all(-1.0 <= result["score"] <= 1.0 for result in results)


async def test_results_are_ordered_by_descending_score(client, headers, small_chunks):
    await _upload(client, headers)

    response = await client.post(
        "/chunks/search", json={"query": "supply chain risk", "top_k": 5}, headers=headers
    )

    scores = [result["score"] for result in response.json()]
    assert len(scores) > 1
    assert scores == sorted(scores, reverse=True)


async def test_the_best_match_is_the_relevant_passage(client, headers, small_chunks):
    await _upload(client, headers)

    response = await client.post(
        "/chunks/search",
        json={"query": "how large did the engineering team grow", "top_k": 1},
        headers=headers,
    )

    assert "engineering" in response.json()[0]["content"].lower()


async def test_top_k_limits_the_result_count(client, headers, small_chunks):
    await _upload(client, headers)

    response = await client.post(
        "/chunks/search", json={"query": "revenue", "top_k": 2}, headers=headers
    )

    assert len(response.json()) == 2


async def test_search_can_be_scoped_to_one_document(client, headers):
    first = await _upload(client, headers, filename="first.txt")
    await _upload(client, headers, text="Entirely unrelated penguin facts.", filename="second.txt")

    response = await client.post(
        "/chunks/search",
        json={"query": "revenue", "document_id": first, "top_k": 10},
        headers=headers,
    )

    assert response.status_code == 200
    assert {result["document_id"] for result in response.json()} == {first}


async def test_search_never_returns_another_users_chunks(client, headers, make_user, auth_headers):
    other = await make_user()
    other_headers = await auth_headers(other.email)
    await _upload(client, other_headers, filename="theirs.txt")

    response = await client.post(
        "/chunks/search", json={"query": "revenue", "top_k": 10}, headers=headers
    )

    assert response.json() == []


async def test_scoping_to_another_users_document_is_a_404(client, headers, make_user, auth_headers):
    other = await make_user()
    document_id = await _upload(client, await auth_headers(other.email))

    response = await client.post(
        "/chunks/search", json={"query": "revenue", "document_id": document_id}, headers=headers
    )

    assert response.status_code == 404


async def test_search_requires_authentication(client):
    response = await client.post("/chunks/search", json={"query": "revenue"})
    assert response.status_code == 401


async def test_empty_query_is_rejected(client, headers):
    response = await client.post("/chunks/search", json={"query": ""}, headers=headers)
    assert response.status_code == 422
