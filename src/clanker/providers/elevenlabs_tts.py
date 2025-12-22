"""ElevenLabs TTS adapter."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from ..constants import DEFAULT_TTS_MODEL
from .errors import PermanentProviderError, TransientProviderError
from .tts import TTS


@dataclass(frozen=True)
class ElevenLabsTTS(TTS):
    """ElevenLabs text-to-speech adapter."""

    api_key: str
    model: str = DEFAULT_TTS_MODEL
    base_url: str = "https://api.elevenlabs.io/v1"
    timeout_s: float = 30.0
    http_client: httpx.AsyncClient | None = None

    async def synthesize(
        self, text: str, voice: str | None, params: dict | None = None
    ) -> bytes:
        voice_id = voice or "default"
        payload = {
            "text": text,
            "model_id": self.model,
        }
        if params:
            payload.update(params)
        headers = {
            "xi-api-key": self.api_key,
            "accept": "audio/mpeg",
            "content-type": "application/json",
        }
        client = self.http_client or httpx.AsyncClient(timeout=self.timeout_s)
        close_client = self.http_client is None
        try:
            response = await client.post(
                f"{self.base_url}/text-to-speech/{voice_id}",
                headers=headers,
                json=payload,
            )
        finally:
            if close_client:
                await client.aclose()

        if response.status_code in {429, 500, 502, 503, 504}:
            raise TransientProviderError(
                f"ElevenLabs TTS transient error: {response.status_code}"
            )
        if response.status_code >= 400:
            raise PermanentProviderError(
                f"ElevenLabs TTS error: {response.status_code}"
            )
        return response.content
