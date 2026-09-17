"""Answer generation with Claude (Anthropic Messages API).

Without an ANTHROPIC_API_KEY the service degrades to an extractive answer built
straight from the retrieved passages. That keeps the whole app - and the test
suite - usable with no credentials, while making the missing key obvious in the
response text rather than as a 500.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from src.config import settings
from src.utils.errors import LLMError

logger = logging.getLogger(__name__)

EXTRACTIVE_MODEL = "extractive-fallback"

REFUSAL_MESSAGE = (
    "I can't answer that question about this document. "
    "Try rephrasing it, or ask about a different part of the document."
)


@dataclass
class LLMAnswer:
    text: str
    model: str
    stop_reason: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)


class LLMService:
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = api_key if api_key is not None else settings.ANTHROPIC_API_KEY
        self.model = model or settings.LLM_MODEL
        self._client: Any | None = None

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    @property
    def client(self) -> Any:
        if self._client is None:
            from anthropic import AsyncAnthropic

            self._client = AsyncAnthropic(
                api_key=self.api_key, timeout=settings.LLM_TIMEOUT_SECONDS
            )
        return self._client

    # ---- request construction -------------------------------------------------

    def _request_kwargs(self, system: str, messages: list[dict[str, str]]) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": settings.LLM_MAX_TOKENS,
            "system": system,
            "messages": messages,
            "output_config": {"effort": settings.LLM_EFFORT},
        }

        if settings.LLM_THINKING == "adaptive":
            kwargs["thinking"] = {"type": "adaptive"}

        if self._use_beta:
            # Server-side refusal fallback: on a policy decline the API re-runs
            # the request on a fallback model within the same call.
            kwargs["betas"] = ["server-side-fallback-2026-07-01"]
            kwargs["fallbacks"] = "default"

        return kwargs

    @property
    def _use_beta(self) -> bool:
        return settings.LLM_REFUSAL_FALLBACK

    @property
    def _messages_api(self) -> Any:
        return self.client.beta.messages if self._use_beta else self.client.messages

    @staticmethod
    def _text_of(response: Any) -> str:
        parts = [
            block.text
            for block in getattr(response, "content", [])
            if getattr(block, "type", None) == "text"
        ]
        return "\n".join(parts).strip()

    # ---- generation -----------------------------------------------------------

    async def generate(self, system: str, messages: list[dict[str, str]]) -> LLMAnswer:
        if not self.available:
            raise LLMError("ANTHROPIC_API_KEY is not configured")

        import anthropic

        try:
            response = await self._messages_api.create(**self._request_kwargs(system, messages))
        except anthropic.NotFoundError as exc:
            raise LLMError(f"Unknown model '{self.model}'") from exc
        except anthropic.AuthenticationError as exc:
            raise LLMError("The Anthropic API key was rejected") from exc
        except anthropic.RateLimitError as exc:
            raise LLMError("Rate limited by the Anthropic API - please retry shortly") from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(f"Anthropic API error ({exc.status_code})") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError("Could not reach the Anthropic API") from exc

        if getattr(response, "stop_reason", None) == "refusal":
            details = getattr(response, "stop_details", None)
            logger.info(
                "Claude refused the request (category=%s)", getattr(details, "category", None)
            )
            return LLMAnswer(text=REFUSAL_MESSAGE, model=self.model, stop_reason="refusal")

        usage = getattr(response, "usage", None)
        return LLMAnswer(
            text=self._text_of(response) or REFUSAL_MESSAGE,
            model=getattr(response, "model", self.model),
            stop_reason=getattr(response, "stop_reason", None),
            usage={
                "input_tokens": getattr(usage, "input_tokens", None),
                "output_tokens": getattr(usage, "output_tokens", None),
            },
        )

    async def stream(self, system: str, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        """Yield answer text as it is produced."""
        if not self.available:
            raise LLMError("ANTHROPIC_API_KEY is not configured")

        import anthropic

        try:
            async with self._messages_api.stream(
                **self._request_kwargs(system, messages)
            ) as stream:
                async for text in stream.text_stream:
                    yield text

                final = await stream.get_final_message()
                if getattr(final, "stop_reason", None) == "refusal":
                    yield REFUSAL_MESSAGE
        except anthropic.APIStatusError as exc:
            raise LLMError(f"Anthropic API error ({exc.status_code})") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError("Could not reach the Anthropic API") from exc

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None
