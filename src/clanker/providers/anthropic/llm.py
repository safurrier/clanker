"""Anthropic LLM adapter."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import httpx

from ...models import Message
from ...prompting import build_messages_with_persona
from ..errors import PermanentProviderError, TransientProviderError

if TYPE_CHECKING:
    from ...models import Context

DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-6"
ANTHROPIC_API_VERSION = "2023-06-01"


@dataclass
class AnthropicLLM:
    """Anthropic Messages API adapter."""

    api_key: str
    model: str = DEFAULT_ANTHROPIC_MODEL
    base_url: str = "https://api.anthropic.com/v1"
    timeout_s: float = 30.0
    max_tokens: int = 1024
    http_client: httpx.AsyncClient | None = None
    _managed_client: httpx.AsyncClient | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.http_client is None:
            self._managed_client = httpx.AsyncClient(timeout=self.timeout_s)

    async def generate(
        self, context: Context, messages: list[Message], params: dict | None = None
    ) -> Message:
        all_messages = build_messages_with_persona(context.persona, messages)

        system_content = ""
        user_messages: list[dict[str, str]] = []
        for msg in all_messages:
            if msg.role == "system":
                system_content = msg.content
            else:
                user_messages.append({"role": msg.role, "content": msg.content})

        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": user_messages,
        }
        if system_content:
            payload["system"] = system_content
        if params:
            payload.update(params)

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": ANTHROPIC_API_VERSION,
            "content-type": "application/json",
        }
        client = self.http_client or self._managed_client
        if client is None:
            raise RuntimeError("No HTTP client available")

        response = await client.post(
            f"{self.base_url}/messages",
            headers=headers,
            json=payload,
        )

        if response.status_code in {429, 500, 502, 503, 504}:
            raise TransientProviderError(
                f"Anthropic LLM transient error: {response.status_code}"
            )
        if response.status_code >= 400:
            raise PermanentProviderError(
                f"Anthropic LLM error: {response.status_code}"
            )

        data = response.json()
        content = _extract_content(data)
        return Message(role="assistant", content=content)

    async def aclose(self) -> None:
        if self._managed_client is not None:
            await self._managed_client.aclose()


def _extract_content(data: dict[str, Any]) -> str:
    content_blocks = data.get("content") or []
    for block in content_blocks:
        if isinstance(block, dict) and block.get("type") == "text":
            return str(block.get("text") or "")
    return ""
