"""Offline tests for AnthropicLLM adapter."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from clanker.models import Context, Message, Persona
from clanker.providers.anthropic.llm import AnthropicLLM
from clanker.providers.errors import PermanentProviderError, TransientProviderError


def _make_context() -> Context:
    persona = Persona(
        id="tester",
        display_name="Tester",
        system_prompt="You are a test assistant.",
    )
    return Context(
        request_id="req-1",
        user_id=1,
        guild_id=None,
        channel_id=99,
        persona=persona,
        messages=[],
        metadata={},
    )


def _ok_response(text: str) -> dict[str, Any]:
    return {
        "id": "msg_01",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": text}],
        "model": "claude-sonnet-4-6",
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }


@pytest.mark.asyncio()
async def test_generate_returns_assistant_message() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_ok_response("Hello from Anthropic!"))

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        llm = AnthropicLLM(api_key="test-key", http_client=client)
        context = _make_context()
        result = await llm.generate(context, [Message(role="user", content="Hi")])

    assert result.role == "assistant"
    assert result.content == "Hello from Anthropic!"


@pytest.mark.asyncio()
async def test_generate_sends_system_prompt_as_top_level_field() -> None:
    captured: list[dict[str, Any]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(200, json=_ok_response("ok"))

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        llm = AnthropicLLM(api_key="test-key", http_client=client)
        context = _make_context()
        await llm.generate(context, [Message(role="user", content="test")])

    body = captured[0]
    assert body["system"] == "You are a test assistant."
    assert all(m["role"] != "system" for m in body["messages"])


@pytest.mark.asyncio()
async def test_generate_uses_messages_endpoint() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=_ok_response("ok"))

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        llm = AnthropicLLM(api_key="test-key", http_client=client)
        context = _make_context()
        await llm.generate(context, [Message(role="user", content="hi")])

    assert requests[0].url.path.endswith("/messages")


@pytest.mark.asyncio()
async def test_generate_transient_error_on_429() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "rate limit"}})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        llm = AnthropicLLM(api_key="test-key", http_client=client)
        context = _make_context()
        with pytest.raises(TransientProviderError, match="429"):
            await llm.generate(context, [Message(role="user", content="hi")])


@pytest.mark.asyncio()
async def test_generate_permanent_error_on_401() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "unauthorized"}})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        llm = AnthropicLLM(api_key="bad-key", http_client=client)
        context = _make_context()
        with pytest.raises(PermanentProviderError, match="401"):
            await llm.generate(context, [Message(role="user", content="hi")])


@pytest.mark.asyncio()
async def test_generate_empty_content_blocks() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"content": []})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        llm = AnthropicLLM(api_key="test-key", http_client=client)
        context = _make_context()
        result = await llm.generate(context, [Message(role="user", content="hi")])

    assert result.content == ""


def test_factory_registers_anthropic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    from clanker.providers.factory import ProviderFactory

    factory = ProviderFactory()
    provider = factory.get_llm("anthropic")
    assert isinstance(provider, AnthropicLLM)


def test_factory_anthropic_requires_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from clanker.providers.factory import ProviderFactory

    factory = ProviderFactory()
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        factory.get_llm("anthropic")
