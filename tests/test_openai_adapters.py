"""Offline tests for OpenAI adapters."""

from __future__ import annotations

import json

import httpx
import pytest

from clanker.models import Context, Message, Persona
from clanker.providers.errors import TransientProviderError
from clanker.providers.openai import OpenAILLM, OpenAISTT


@pytest.mark.asyncio()
async def test_openai_llm_builds_request() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        payload = json.loads(request.content)
        assert payload["model"]
        assert payload["messages"]
        return httpx.Response(200, json={"choices": [{"message": {"content": "hi"}}]})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        llm = OpenAILLM(api_key="key", http_client=client)
        context = Context(
            request_id="req",
            user_id=1,
            guild_id=None,
            channel_id=2,
            persona=Persona(id="p", display_name="p", system_prompt="system"),
            messages=[Message(role="user", content="hi")],
            metadata={},
        )
        reply = await llm.generate(context, context.messages)
        assert reply.content == "hi"

    assert requests
    assert requests[0].url.path.endswith("/chat/completions")


@pytest.mark.asyncio()
async def test_openai_stt_builds_request() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"text": "hello"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        stt = OpenAISTT(api_key="key", http_client=client)
        transcript = await stt.transcribe(b"audio")
        assert transcript == "hello"

    assert requests
    assert requests[0].url.path.endswith("/audio/transcriptions")


@pytest.mark.asyncio()
async def test_openai_llm_network_error_raises_transient() -> None:
    """httpx.ConnectError is mapped to TransientProviderError."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        llm = OpenAILLM(api_key="key", http_client=client)
        context = Context(
            request_id="req",
            user_id=1,
            guild_id=None,
            channel_id=2,
            persona=Persona(id="p", display_name="p", system_prompt="system"),
            messages=[Message(role="user", content="hi")],
            metadata={},
        )
        with pytest.raises(TransientProviderError):
            await llm.generate(context, list(context.messages))


@pytest.mark.asyncio()
async def test_openai_stt_network_error_raises_transient() -> None:
    """httpx.ConnectError is mapped to TransientProviderError."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        stt = OpenAISTT(api_key="key", http_client=client)
        with pytest.raises(TransientProviderError):
            await stt.transcribe(b"audio")
