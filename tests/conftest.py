"""Shared test fixtures.

The suite runs entirely offline: SQLite stands in for PostgreSQL (similarity
search falls back to an in-Python cosine scan), the token blocklist is the
in-memory implementation, and the `hash` embedder needs no API key.
"""

import os
import tempfile
import uuid
from pathlib import Path

# Configure the app before any src module is imported - settings, the database
# engine and the embedding column width are all resolved at import time.
TEST_ROOT = Path(tempfile.mkdtemp(prefix="docmind-tests-"))
os.environ.update(
    {
        "ENVIRONMENT": "test",
        "DEBUG": "false",
        "DATABASE_URL": f"sqlite+aiosqlite:///{TEST_ROOT / 'test.db'}",
        "SECRET_KEY": "test-secret-key",
        "REDIS_URL": "",
        "UPLOAD_DIR": str(TEST_ROOT / "uploads"),
        "MAX_UPLOAD_SIZE_MB": "1",
        "EMBEDDING_PROVIDER": "hash",
        "ANTHROPIC_API_KEY": "",
        "ACCESS_TOKEN_EXPIRE_MINUTES": "30",
        "REFRESH_TOKEN_EXPIRE_MINUTES": "1440",
    }
)

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from src.db.database import Base, engine, get_session  # noqa: E402
from src.main import app  # noqa: E402
from src.models import Document, DocumentStatus, User  # noqa: E402
from src.utils.security import hash_password  # noqa: E402

TEST_PASSWORD = "sup3r-secret-pw"


@pytest.fixture(autouse=True)
async def _database():
    """A fresh schema for every test, so tests cannot leak state into each other."""
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def session():
    async for db_session in get_session():
        yield db_session


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client


@pytest.fixture
def make_user(session):
    async def _make_user(
        email: str | None = None,
        password: str = TEST_PASSWORD,
        is_admin: bool = False,
        is_active: bool = True,
    ) -> User:
        user = User(
            email=email or f"user-{uuid.uuid4().hex[:8]}@example.com",
            password_hash=hash_password(password),
            first_name="Test",
            last_name="User",
            is_admin=is_admin,
            is_active=is_active,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user

    return _make_user


@pytest.fixture
def auth_headers(client):
    async def _auth_headers(email: str, password: str = TEST_PASSWORD) -> dict[str, str]:
        response = await client.post("/auth/login", json={"email": email, "password": password})
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return _auth_headers


@pytest.fixture
async def user(make_user):
    return await make_user()


@pytest.fixture
async def headers(user, auth_headers):
    return await auth_headers(user.email)


@pytest.fixture
def make_document(session):
    async def _make_document(
        owner: User,
        filename: str = "notes.txt",
        text: str | None = None,
        status: str = DocumentStatus.PENDING,
    ) -> Document:
        document_id = uuid.uuid4()
        directory = Path(os.environ["UPLOAD_DIR"]) / str(owner.id)
        directory.mkdir(parents=True, exist_ok=True)

        path = directory / f"{document_id}{Path(filename).suffix}"
        body = text if text is not None else "DocMind indexes documents.\n"
        path.write_text(body, encoding="utf-8")

        document = Document(
            id=document_id,
            user_id=owner.id,
            filename=filename,
            file_path=str(path),
            file_type="text/plain",
            file_size=len(body.encode("utf-8")),
            status=status,
        )
        session.add(document)
        await session.commit()
        await session.refresh(document)
        return document

    return _make_document


@pytest.fixture
def fake_llm(monkeypatch):
    """Stand in for Claude so chat can be tested without an API key.

    Returns the list of prompts the service was called with, so tests can assert
    on what was actually sent to the model.
    """
    from src.services.llm import LLMAnswer, LLMService

    calls: list[dict] = []

    async def _generate(self, system, messages):
        calls.append({"system": system, "messages": messages})
        return LLMAnswer(
            text="European revenue grew twelve percent [1].", model="claude-opus-5-stub"
        )

    async def _stream(self, system, messages):
        calls.append({"system": system, "messages": messages})
        for piece in ("European revenue ", "grew twelve percent [1]."):
            yield piece

    monkeypatch.setattr(LLMService, "available", property(lambda self: True))
    monkeypatch.setattr(LLMService, "generate", _generate)
    monkeypatch.setattr(LLMService, "stream", _stream)
    return calls


@pytest.fixture
def small_chunks(monkeypatch):
    """Shrink the chunk window so a short fixture document yields many chunks."""
    from src.config import settings

    monkeypatch.setattr(settings, "CHUNK_SIZE", 120)
    monkeypatch.setattr(settings, "CHUNK_OVERLAP", 20)


@pytest.fixture
def sample_text() -> str:
    return (
        "DocMind AI is a document assistant.\n\n"
        "Chapter 1: Revenue. European revenue grew by twelve percent in the third quarter, "
        "driven by strong demand in Germany and France.\n\n"
        "Chapter 2: Headcount. The engineering team grew from forty to fifty-five people "
        "over the same period.\n\n"
        "Chapter 3: Risks. Supply chain delays remain the most significant operational risk "
        "for the coming year.\n"
    )
