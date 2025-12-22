"""Network smoke tests for Memegen adapter."""

from __future__ import annotations

import os

import pytest

from clanker.providers.memegen import MemegenImage


@pytest.mark.network()
@pytest.mark.asyncio()
async def test_memegen_smoke_generates_image() -> None:
    if not os.getenv("MEMEGEN_SMOKE"):
        pytest.skip("MEMEGEN_SMOKE not set")

    adapter = MemegenImage()
    image_bytes = await adapter.generate({"template": "buzz", "text": "hi|there"})
    assert image_bytes
