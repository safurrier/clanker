"""Anthropic LLM adapter."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, TypeVar

import httpx

from ...models import Message
from ...prompting import build_messages_with_persona
from ..base import LLM, StructuredLLM
from ..errors import PermanentProviderError, TransientProviderError

if TYPE_CHECKING:
    from instructor import AsyncInstructor
    from pydantic import BaseModel

    from ...models import Context

T = TypeVar("T", bound="BaseModel")

DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_MAX_TOKENS = 1024


@dataclass
class AnthropicLLM(LLM, StructuredLLM):
    """Anthropic Messages API adapter.

    Supports both unstructured (generate) and structured (generate_structured)
    outputs. Structured outputs use the Instructor library internally for
    guaranteed schema compliance with Pydantic models.

    The Anthropic API differs from OpenAI in two key ways:
    - System prompt lives in a separate top-level ``system`` field, not as a
      message with role "system".
    - ``max_tokens`` is a required field on every request.
    """

    api_key: str
    model: str = DEFAULT_ANTHROPIC_MODEL
    timeout_s: float = 30.0
    http_client: httpx.AsyncClient | None = None
    _managed_client: httpx.AsyncClient | None = field(default=None, repr=False)
    _instructor_client: AsyncInstructor | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Initialize managed HTTP client if not provided."""
        if self.http_client is None:
            self._managed_client = httpx.AsyncClient(timeout=self.timeout_s)

    async def generate(
        self, context: Context, messages: list[Message], params: dict | None = None
    ) -> Message:
        all_messages = build_messages_with_persona(context.persona, messages)

        # Anthropic requires the system prompt in a separate top-level field.
        system_parts = [m.content for m in all_messages if m.role == "system"]
        system_content = "\n".join(system_parts) if system_parts else None
        conversation = [
            {"role": m.role, "content": m.content}
            for m in all_messages
            if m.role != "system"
        ]

        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": DEFAULT_MAX_TOKENS,
            "messages": conversation,
        }
        if system_content:
            payload["system"] = system_content
        if params:
            payload.update(params)

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        client = self.http_client or self._managed_client
        if client is None:
            raise RuntimeError("No HTTP client available")

        try:
            response = await client.post(
                ANTHROPIC_API_URL, headers=headers, json=payload
            )
        except httpx.RequestError as exc:
            raise TransientProviderError(f"Anthropic LLM network error: {exc}") from exc

        if response.status_code in {429, 500, 502, 503, 504}:
            raise TransientProviderError(
                f"Anthropic LLM transient error: {response.status_code}"
            )
        if response.status_code >= 400:
            raise PermanentProviderError(
                f"Anthropic LLM error: {response.status_code} - {response.text}"
            )

        data = response.json()
        content = _extract_content(data)
        return Message(role="assistant", content=content)

    async def generate_structured(
        self,
        response_model: type[T],
        messages: list[Message],
        max_retries: int = 2,
    ) -> T:
        """Generate a structured response matching the Pydantic model.

        Uses the Instructor library with the Anthropic SDK to guarantee schema
        compliance.  The instructor client is lazily initialized on first use.

        Args:
            response_model: Pydantic model class defining the output schema
            messages: Conversation messages to send to the LLM
            max_retries: Number of retries if validation fails (default: 2)

        Returns:
            Instance of response_model with validated data
        """
        client = self._get_instructor_client()
        # Messages dict matches MessageParam at runtime
        return await client.messages.create(  # type: ignore[return-value]
            model=self.model,
            max_tokens=DEFAULT_MAX_TOKENS,
            response_model=response_model,
            messages=[{"role": m.role, "content": m.content} for m in messages],  # type: ignore[arg-type]
            max_retries=max_retries,
        )

    def _get_instructor_client(self) -> AsyncInstructor:
        """Get or create the Instructor-patched async Anthropic client."""
        if self._instructor_client is None:
            import instructor
            from anthropic import AsyncAnthropic

            anthropic_client = AsyncAnthropic(
                api_key=self.api_key,
                timeout=self.timeout_s,
            )
            self._instructor_client = instructor.from_anthropic(anthropic_client)  # type: ignore[possibly-missing-attribute]
        return self._instructor_client

    async def aclose(self) -> None:
        """Close the managed HTTP client if it exists."""
        if self._managed_client is not None:
            await self._managed_client.aclose()


def _extract_content(data: dict[str, Any]) -> str:
    """Extract text content from an Anthropic Messages API response."""
    content_blocks = data.get("content") or []
    for block in content_blocks:
        if block.get("type") == "text":
            return str(block.get("text") or "")
    return ""
