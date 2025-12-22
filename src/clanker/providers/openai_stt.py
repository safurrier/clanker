"""OpenAI STT adapter."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from ..constants import DEFAULT_STT_MODEL
from .errors import PermanentProviderError, TransientProviderError
from .stt import STT


@dataclass(frozen=True)
class OpenAISTT(STT):
    """OpenAI speech-to-text adapter."""

    api_key: str
    model: str = DEFAULT_STT_MODEL
    base_url: str = "https://api.openai.com/v1"
    timeout_s: float = 30.0
    http_client: httpx.AsyncClient | None = None

    async def transcribe(self, audio_bytes: bytes, params: dict | None = None) -> str:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        data = {"model": self.model}
        if params:
            data.update(params)
        files = {
            "file": ("audio.wav", audio_bytes, "audio/wav"),
        }
        client = self.http_client or httpx.AsyncClient(timeout=self.timeout_s)
        close_client = self.http_client is None
        try:
            response = await client.post(
                f"{self.base_url}/audio/transcriptions",
                headers=headers,
                data=data,
                files=files,
            )
        finally:
            if close_client:
                await client.aclose()

        if response.status_code in {429, 500, 502, 503, 504}:
            raise TransientProviderError(
                f"OpenAI STT transient error: {response.status_code}"
            )
        if response.status_code >= 400:
            error_detail = response.text
            raise PermanentProviderError(
                f"OpenAI STT error: {response.status_code} - {error_detail}"
            )
        payload = response.json()
        text = payload.get("text") or ""
        return str(text)
