"""Unit tests for the Claude wrapper: request shape, refusals and error mapping."""

import pytest

from src.config import settings
from src.services.llm import REFUSAL_MESSAGE, LLMService
from src.utils.errors import LLMError


class FakeBlock:
    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class FakeUsage:
    input_tokens = 120
    output_tokens = 45


class FakeResponse:
    def __init__(self, text="An answer.", stop_reason="end_turn", stop_details=None):
        self.content = [FakeBlock(text)]
        self.stop_reason = stop_reason
        self.stop_details = stop_details
        self.model = "claude-opus-5"
        self.usage = FakeUsage()


class FakeMessages:
    def __init__(self, response) -> None:
        self.response = response
        self.kwargs = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def build_service(response) -> tuple[LLMService, FakeMessages]:
    service = LLMService(api_key="test-key")
    messages = FakeMessages(response)

    class FakeClient:
        beta = type("Beta", (), {"messages": messages})()

    FakeClient.messages = messages
    service._client = FakeClient()
    return service, messages


def test_no_api_key_means_unavailable():
    assert LLMService(api_key="").available is False
    assert LLMService(api_key="sk-test").available is True


async def test_generate_returns_the_text():
    service, _ = build_service(FakeResponse("European revenue grew."))

    answer = await service.generate("system", [{"role": "user", "content": "q"}])

    assert answer.text == "European revenue grew."
    assert answer.model == "claude-opus-5"
    assert answer.usage["input_tokens"] == 120


async def test_generate_without_a_key_is_an_error():
    with pytest.raises(LLMError, match="ANTHROPIC_API_KEY"):
        await LLMService(api_key="").generate("system", [{"role": "user", "content": "q"}])


async def test_the_request_uses_the_configured_model_and_effort():
    service, messages = build_service(FakeResponse())

    await service.generate("a system prompt", [{"role": "user", "content": "q"}])

    assert messages.kwargs["model"] == settings.LLM_MODEL
    assert messages.kwargs["max_tokens"] == settings.LLM_MAX_TOKENS
    assert messages.kwargs["system"] == "a system prompt"
    assert messages.kwargs["output_config"] == {"effort": settings.LLM_EFFORT}


async def test_adaptive_thinking_is_requested_by_default():
    service, messages = build_service(FakeResponse())

    await service.generate("system", [{"role": "user", "content": "q"}])

    assert messages.kwargs["thinking"] == {"type": "adaptive"}


async def test_thinking_can_be_turned_off(monkeypatch):
    monkeypatch.setattr(settings, "LLM_THINKING", "off")
    service, messages = build_service(FakeResponse())

    await service.generate("system", [{"role": "user", "content": "q"}])

    assert "thinking" not in messages.kwargs


async def test_refusal_fallback_is_enabled_by_default():
    service, messages = build_service(FakeResponse())

    await service.generate("system", [{"role": "user", "content": "q"}])

    assert messages.kwargs["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in messages.kwargs["betas"]


async def test_refusal_fallback_can_be_disabled(monkeypatch):
    monkeypatch.setattr(settings, "LLM_REFUSAL_FALLBACK", False)
    service, messages = build_service(FakeResponse())

    await service.generate("system", [{"role": "user", "content": "q"}])

    assert "fallbacks" not in messages.kwargs
    assert "betas" not in messages.kwargs


async def test_a_refusal_becomes_a_readable_message():
    details = type("Details", (), {"category": "cyber", "explanation": "no"})()
    service, _ = build_service(FakeResponse("", stop_reason="refusal", stop_details=details))

    answer = await service.generate("system", [{"role": "user", "content": "q"}])

    assert answer.text == REFUSAL_MESSAGE
    assert answer.stop_reason == "refusal"


async def test_an_empty_response_falls_back_to_a_readable_message():
    service, _ = build_service(FakeResponse(""))

    answer = await service.generate("system", [{"role": "user", "content": "q"}])

    assert answer.text == REFUSAL_MESSAGE


@pytest.mark.parametrize(
    ("exception_name", "expected"),
    [
        ("AuthenticationError", "key was rejected"),
        ("RateLimitError", "Rate limited"),
        ("APIConnectionError", "Could not reach"),
    ],
)
async def test_api_errors_map_to_readable_llm_errors(exception_name, expected):
    import anthropic
    import httpx2

    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    exception_class = getattr(anthropic, exception_name)

    if exception_name == "APIConnectionError":
        error = exception_class(message="boom", request=request)
    else:
        response = httpx2.Response(
            429 if exception_name == "RateLimitError" else 401, request=request
        )
        error = exception_class(message="boom", response=response, body=None)

    service, _ = build_service(error)

    with pytest.raises(LLMError, match=expected):
        await service.generate("system", [{"role": "user", "content": "q"}])
