async def test_root(client):
    response = await client.get("/")
    assert response.status_code == 200
    assert response.json()["message"] == "DocMind AI API is running"


async def test_liveness(client):
    response = await client.get("/health")
    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "ok"
    assert body["embedding_provider"] == "hash"
    assert body["llm_configured"] is False


async def test_readiness_checks_dependencies(client):
    response = await client.get("/health/ready")
    body = response.json()
    assert response.status_code == 200
    assert body["database"] == "ok"
    assert body["blocklist"] == "ok"
