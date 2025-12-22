"""Memegen image adapter."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

import httpx

from .errors import PermanentProviderError, TransientProviderError
from .image import ImageGen


@dataclass(frozen=True)
class MemegenImage(ImageGen):
    """Memegen image generator adapter."""

    base_url: str = "https://api.memegen.link/images"
    timeout_s: float = 30.0
    http_client: httpx.AsyncClient | None = None

    async def generate(self, spec: dict) -> bytes:
        template = str(spec.get("template", "buzz"))
        text = spec.get("text") or ""
        top, bottom = _split_text(text)
        url = f"{self.base_url}/{template}/{quote(top)}/{quote(bottom)}.png"
        client = self.http_client or httpx.AsyncClient(timeout=self.timeout_s)
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


def _split_text(text: str) -> tuple[str, str]:
    if not text:
        return "", ""
    if "|" in text:
        top, bottom = text.split("|", 1)
        return top.strip(), bottom.strip()
    return text.strip(), ""
