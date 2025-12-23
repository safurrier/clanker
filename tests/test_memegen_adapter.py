"""Offline tests for Memegen adapter."""

from __future__ import annotations

import httpx
import pytest

from clanker.providers.memegen import MemegenImage


@pytest.mark.asyncio()
async def test_memegen_builds_request() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=b"image")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = MemegenImage(http_client=client)
        result = await adapter.generate({"template": "buzz", "text": "hi|there"})
        assert result == b"image"

    assert requests
    assert requests[0].url.path.endswith("/buzz/hi/there.png")


@pytest.mark.asyncio()
async def test_memegen_builds_multiline_request() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=b"image")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = MemegenImage(http_client=client)
        result = await adapter.generate(
            {"template": "buzz", "text": ["one", "two", "three"]}
        )
        assert result == b"image"

    assert requests
    assert requests[0].url.path.endswith("/buzz/one/two/three.png")
