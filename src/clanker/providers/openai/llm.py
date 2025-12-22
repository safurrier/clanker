"""OpenAI LLM adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from ...constants import DEFAULT_LLM_MODEL
from ...models import Context, Message
from ...prompting import build_messages_with_persona
from ..base import LLM
from ..errors import PermanentProviderError, TransientProviderError


@dataclass
class OpenAILLM(LLM):
    """OpenAI Chat Completions adapter."""

    api_key: str
    model: str = DEFAULT_LLM_MODEL
    base_url: str = "https://api.openai.com/v1"
    timeout_s: float = 30.0
    http_client: httpx.AsyncClient | None = None
    _managed_client: httpx.AsyncClient | None = None

    def __post_init__(self) -> None:
        """Initialize managed HTTP client if not provided."""
        if self.http_client is None:
            self._managed_client = httpx.AsyncClient(timeout=self.timeout_s)

    async def generate(
        self, context: Context, messages: list[Message], params: dict | None = None
    ) -> Message:
        payload = {
            "model": self.model,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in build_messages_with_persona(context.persona, messages)
            ],
        }
        if params:
            payload.update(params)
        headers = {"Authorization": f"Bearer {self.api_key}"}
        client = self.http_client or self._managed_client
        if client is None:
            raise RuntimeError("No HTTP client available")
        response = await client.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=payload,
        )

        if response.status_code in {429, 500, 502, 503, 504}:
            raise TransientProviderError(
                f"OpenAI LLM transient error: {response.status_code}"
            )
        if response.status_code >= 400:
            raise PermanentProviderError(f"OpenAI LLM error: {response.status_code}")

        data = response.json()
        content = _extract_content(data)
        return Message(role="assistant", content=content)

    async def aclose(self) -> None:
        """Close the managed HTTP client if it exists."""
        if self._managed_client is not None:
            await self._managed_client.aclose()


def _extract_content(data: dict[str, Any]) -> str:
    choices = data.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return str(message.get("content") or "")
