"""OpenAI STT adapter."""

from __future__ import annotations

from dataclasses import dataclass

import httpx
from loguru import logger

from ...constants import DEFAULT_STT_MODEL
from ..audio_utils import resample_wav
from ..base import STT
from ..errors import PermanentProviderError, TransientProviderError

# Whisper models are trained on 16kHz audio
WHISPER_SAMPLE_RATE = 16000


@dataclass
class OpenAISTT(STT):
    """OpenAI speech-to-text adapter."""

    api_key: str
    model: str = DEFAULT_STT_MODEL
    base_url: str = "https://api.openai.com/v1"
    timeout_s: float = 30.0
    http_client: httpx.AsyncClient | None = None
    _managed_client: httpx.AsyncClient | None = None

    def __post_init__(self) -> None:
        """Initialize managed HTTP client if not provided."""
        if self.http_client is None:
            self._managed_client = httpx.AsyncClient(timeout=self.timeout_s)

    async def transcribe(
        self,
        audio_bytes: bytes,
        sample_rate_hz: int = 16000,
        params: dict | None = None,
    ) -> str:
        # Resample to Whisper's expected rate if needed
        if sample_rate_hz != WHISPER_SAMPLE_RATE:
            logger.debug(
                "stt.resample: from={}Hz to={}Hz bytes={}",
                sample_rate_hz,
                WHISPER_SAMPLE_RATE,
                len(audio_bytes),
            )
            audio_bytes = resample_wav(audio_bytes, sample_rate_hz, WHISPER_SAMPLE_RATE)

        headers = {"Authorization": f"Bearer {self.api_key}"}
        data = {"model": self.model}
        if params:
            data.update(params)
        files = {
            "file": ("audio.wav", audio_bytes, "audio/wav"),
        }
        client = self.http_client or self._managed_client
        if client is None:
            raise RuntimeError("No HTTP client available")
        try:
            response = await client.post(
                f"{self.base_url}/audio/transcriptions",
                headers=headers,
                data=data,
                files=files,
            )
        except httpx.RequestError as exc:
            raise TransientProviderError(f"OpenAI STT network error: {exc}") from exc

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

    async def aclose(self) -> None:
        """Close the managed HTTP client if it exists."""
        if self._managed_client is not None:
            await self._managed_client.aclose()
