"""Memegen image adapter."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from urllib.parse import quote

import httpx

from ..base import ImageGen
from ..errors import PermanentProviderError, TransientProviderError


@dataclass(frozen=True)
class MemegenImage(ImageGen):
    """Memegen image generator adapter."""

    base_url: str = "https://api.memegen.link/images"
    timeout_s: float = 30.0
    http_client: httpx.AsyncClient | None = None

    async def generate(self, params: dict) -> bytes | str:
        template = str(params.get("template", "buzz"))
        text = params.get("text") or ""
        segments = _split_text(text)
        if len(segments) == 1:
            segments.append("")
        encoded_segments = "/".join(quote(segment) for segment in segments)
        url = f"{self.base_url}/{template}/{encoded_segments}.png"
        client = self.http_client or httpx.AsyncClient(
            timeout=self.timeout_s, follow_redirects=True
        )
        close_client = self.http_client is None
        try:
            response = await client.get(url)
        finally:
            if close_client:
                await client.aclose()

        if response.status_code in {429, 500, 502, 503, 504}:
            raise TransientProviderError(
                f"Memegen transient error: {response.status_code}"
            )
        if response.status_code >= 400:
            raise PermanentProviderError(f"Memegen error: {response.status_code}")
        return response.content


def _split_text(text: str | Sequence[str]) -> list[str]:
    if isinstance(text, str):
        if not text:
            return ["", ""]
        if "|" in text:
            top, bottom = text.split("|", 1)
            return [top.strip(), bottom.strip()]
        return [text.strip()]
    if not text:
        return ["", ""]
    return [str(segment).strip() for segment in text]
