"""Application settings, loaded from the environment (or a local .env file)."""

from functools import lru_cache
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_SECRET_KEY = "dev-secret-change-me"


class Settings(BaseSettings):
    # ---- Application ----
    APP_NAME: str = "DocMind AI"
    ENVIRONMENT: Literal["development", "test", "production"] = "development"
    DEBUG: bool = False
    API_PREFIX: str = ""
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # ---- Database ----
    DATABASE_URL: str = "postgresql+asyncpg://docmind:docmind@localhost:5432/docmind"
    DB_ECHO: bool = False

    # ---- Auth ----
    SECRET_KEY: str = DEV_SECRET_KEY
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7

    # ---- Redis (token blocklist). Empty string => in-memory fallback. ----
    REDIS_URL: str = ""

    # ---- Uploads ----
    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_SIZE_MB: int = 25
    ALLOWED_EXTENSIONS: list[str] = [".pdf", ".docx", ".txt", ".md"]

    # ---- Chunking (sizes are in characters) ----
    CHUNK_SIZE: int = 1200
    CHUNK_OVERLAP: int = 200

    # ---- Embeddings ----
    # "hash" is a deterministic, dependency-free local embedder. It needs no API
    # key and makes the whole pipeline runnable offline, which is what the test
    # suite uses. Swap to "voyage" or "openai" for real semantic retrieval.
    EMBEDDING_PROVIDER: Literal["hash", "voyage", "openai"] = "hash"
    EMBEDDING_MODEL: str = "voyage-3"
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_BASE_URL: str = ""
    EMBEDDING_DIMENSIONS: int = 1536
    EMBEDDING_BATCH_SIZE: int = 64
    EMBEDDING_TIMEOUT_SECONDS: float = 60.0

    # ---- LLM (answer generation) ----
    ANTHROPIC_API_KEY: str = ""
    LLM_MODEL: str = "claude-opus-5"
    LLM_MAX_TOKENS: int = 16000
    LLM_EFFORT: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    # "adaptive" requires a Claude 4.6-or-newer model; set "off" for older ones.
    LLM_THINKING: Literal["adaptive", "off"] = "adaptive"
    # Server-side refusal fallback: if the model declines, the API retries the
    # same request on a fallback model inside the same call.
    LLM_REFUSAL_FALLBACK: bool = True
    LLM_TIMEOUT_SECONDS: float = 120.0

    # ---- Retrieval ----
    RAG_TOP_K: int = 5
    RAG_MAX_CONTEXT_CHARS: int = 12000

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("CORS_ORIGINS", "ALLOWED_EXTENSIONS", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        """Allow comma-separated values in .env, e.g. CORS_ORIGINS=a,b."""
        if isinstance(value, str) and not value.strip().startswith("["):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("ALLOWED_EXTENSIONS")
    @classmethod
    def _normalise_extensions(cls, value: list[str]) -> list[str]:
        return [ext if ext.startswith(".") else f".{ext}" for ext in (e.lower() for e in value)]

    @property
    def max_upload_size_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    @property
    def uses_redis(self) -> bool:
        return bool(self.REDIS_URL.strip())

    @model_validator(mode="after")
    def _check_production_hardening(self) -> "Settings":
        if self.CHUNK_OVERLAP >= self.CHUNK_SIZE:
            raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE")
        if self.ENVIRONMENT == "production":
            if self.SECRET_KEY == DEV_SECRET_KEY:
                raise ValueError("SECRET_KEY must be set to a unique value in production")
            if self.DEBUG:
                raise ValueError("DEBUG must be disabled in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
