from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src import __version__
from src.config import settings
from src.db.database import get_session
from src.schemas.common import HealthResponse
from src.services.llm import LLMService
from src.utils.redis import blocklist_healthy

health_router = APIRouter(tags=["Health"])


def _base_health(status_text: str, database: str, blocklist: str) -> HealthResponse:
    return HealthResponse(
        status=status_text,
        version=__version__,
        database=database,
        blocklist=blocklist,
        llm_configured=LLMService().available,
        embedding_provider=settings.EMBEDDING_PROVIDER,
    )


@health_router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness probe - answers without touching any dependency."""
    return _base_health("ok", "unchecked", "unchecked")


@health_router.get("/health/ready", response_model=HealthResponse)
async def readiness(
    response: Response, session: AsyncSession = Depends(get_session)
) -> HealthResponse:
    """Readiness probe - verifies the database and the token blocklist."""
    try:
        await session.execute(text("SELECT 1"))
        database = "ok"
    except Exception:
        database = "unavailable"

    blocklist = "ok" if await blocklist_healthy() else "unavailable"
    healthy = database == "ok" and blocklist == "ok"

    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return _base_health("ok" if healthy else "degraded", database, blocklist)
