"""Offline tests for the Anthropic LLM adapter."""

from __future__ import annotations

import json

import httpx
import pytest

from clanker.models import Context, Message, Persona
from clanker.providers.anthropic import AnthropicLLM
from clanker.providers.errors import PermanentProviderError, TransientProviderError


def _make_context(system_prompt: str = "Be helpful.") -> Context:
    return Context(
        request_id="req-1",
        user_id=1,
        guild_id=None,
        channel_id=2,
        persona=Persona(id="p", display_name="Bot", system_prompt=system_prompt),
        messages=[Message(role="user", content="Hello")],
        metadata={},
    )


def _anthropic_response(text: str) -> dict:
    return {
        "id": "msg_123",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": text}],
        "model": "claude-3-5-haiku-latest",
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }


@pytest.mark.asyncio()
async def test_anthropic_llm_sends_correct_request() -> None:
    """Verifies the adapter constructs a valid Anthropic Messages API request."""
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        payload = json.loads(request.content)
        # system must be a top-level field, not inside messages
        assert "system" in payload
        assert all(m["role"] != "system" for m in payload["messages"])
        assert "max_tokens" in payload
        assert payload["model"]
        return httpx.Response(200, json=_anthropic_response("Hello back!"))

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        llm = AnthropicLLM(api_key="test-key", http_client=client)
        context = _make_context()
        reply = await llm.generate(context, list(context.messages))

    assert reply.role == "assistant"
    assert reply.content == "Hello back!"
    assert len(requests) == 1
    assert requests[0].url.path == "/v1/messages"


@pytest.mark.asyncio()
async def test_anthropic_llm_auth_header() -> None:
    """Verifies x-api-key header is set (not Bearer)."""
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=_anthropic_response("ok"))

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        llm = AnthropicLLM(api_key="my-secret-key", http_client=client)
        context = _make_context()
        await llm.generate(context, list(context.messages))

    assert requests[0].headers["x-api-key"] == "my-secret-key"
    assert "authorization" not in requests[0].headers


@pytest.mark.asyncio()
async def test_anthropic_llm_transient_error_on_429() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"type": "rate_limit_error"}})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        llm = AnthropicLLM(api_key="key", http_client=client)
        with pytest.raises(TransientProviderError):
            await llm.generate(_make_context(), [Message(role="user", content="hi")])


@pytest.mark.asyncio()
async def test_anthropic_llm_permanent_error_on_400() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"type": "invalid_request_error"}})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        llm = AnthropicLLM(api_key="key", http_client=client)
        with pytest.raises(PermanentProviderError):
            await llm.generate(_make_context(), [Message(role="user", content="hi")])


@pytest.mark.asyncio()
async def test_anthropic_llm_empty_content_returns_empty_string() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"content": []})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        llm = AnthropicLLM(api_key="key", http_client=client)
        reply = await llm.generate(_make_context(), [Message(role="user", content="hi")])

    assert reply.content == ""


@pytest.mark.asyncio()
async def test_anthropic_llm_params_merged_into_payload() -> None:
    """Extra params (e.g. temperature) are forwarded to the API."""
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=_anthropic_response("cool"))

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        llm = AnthropicLLM(api_key="key", http_client=client)
        context = _make_context()
        await llm.generate(
            context, list(context.messages), params={"temperature": 0.5, "max_tokens": 50}
        )

    payload = json.loads(requests[0].content)
    assert payload["temperature"] == 0.5
    assert payload["max_tokens"] == 50


def test_anthropic_factory_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """ProviderFactory raises when ANTHROPIC_API_KEY is missing."""
    from clanker.providers.factory import ProviderFactory

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    factory = ProviderFactory()
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        factory.get_llm("anthropic")


def test_anthropic_factory_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """ProviderFactory returns an AnthropicLLM when env var is set."""
    from clanker.providers.factory import ProviderFactory

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    factory = ProviderFactory()
    llm = factory.get_llm("anthropic")
    assert isinstance(llm, AnthropicLLM)


def test_factory_rejects_unknown_llm_provider() -> None:
    from clanker.providers.factory import ProviderFactory

    factory = ProviderFactory()
    with pytest.raises(ValueError, match="Unsupported llm provider"):
        factory.get_llm("unknown-provider")
