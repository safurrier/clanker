"""Network smoke tests for Memegen adapter."""

from __future__ import annotations

import pytest

from clanker.providers.memegen import MemegenImage

# PNG magic bytes
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@pytest.mark.memegen()
@pytest.mark.asyncio()
async def test_memegen_smoke_generates_image() -> None:
    adapter = MemegenImage()
    image_bytes = await adapter.generate({"template": "buzz", "text": "hi|there"})
    assert image_bytes
    assert image_bytes[:8] == PNG_SIGNATURE, "Expected PNG image"


@pytest.mark.memegen()
@pytest.mark.asyncio()
async def test_memegen_handles_spaces_in_text() -> None:
    """Test that spaces in text work (API returns 301 redirect)."""
    adapter = MemegenImage()
    # Spaces in text trigger a 301 redirect from %20 to underscore
    image_bytes = await adapter.generate({
        "template": "drake",
        "text": ["thing I hate", "thing I love"],
    })
    assert len(image_bytes) > 1000, f"Expected real image, got {len(image_bytes)} bytes"
    assert image_bytes[:8] == PNG_SIGNATURE, "Expected PNG image"


@pytest.mark.memegen()
@pytest.mark.asyncio()
async def test_memegen_list_text_format() -> None:
    """Test that list-based text format works (used by shitpost command)."""
    adapter = MemegenImage()
    image_bytes = await adapter.generate({
        "template": "panik-kalm-panik",
        "text": ["First panel", "Second panel", "Third panel"],
    })
    assert len(image_bytes) > 1000, f"Expected real image, got {len(image_bytes)} bytes"
    assert image_bytes[:8] == PNG_SIGNATURE, "Expected PNG image"
