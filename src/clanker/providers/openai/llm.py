"""OpenAI LLM adapter."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, TypeVar

import httpx

from ...constants import DEFAULT_LLM_MODEL
from ...models import Message
from ...prompting import build_messages_with_persona
from ..base import LLM, StructuredLLM
from ..errors import PermanentProviderError, TransientProviderError

if TYPE_CHECKING:
    from instructor import AsyncInstructor
    from pydantic import BaseModel

    from ...models import Context

T = TypeVar("T", bound="BaseModel")


@dataclass
class OpenAILLM(LLM, StructuredLLM):
    """OpenAI Chat Completions adapter.

    Supports both unstructured (generate) and structured (generate_structured)
    outputs. Structured outputs use the Instructor library internally for
    guaranteed schema compliance with Pydantic models.
    """

    api_key: str
    model: str = DEFAULT_LLM_MODEL
    base_url: str = "https://api.openai.com/v1"
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
        try:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
        except httpx.RequestError as exc:
            raise TransientProviderError(f"OpenAI LLM network error: {exc}") from exc

        if response.status_code in {429, 500, 502, 503, 504}:
            raise TransientProviderError(
                f"OpenAI LLM transient error: {response.status_code}"
            )
        if response.status_code >= 400:
            raise PermanentProviderError(f"OpenAI LLM error: {response.status_code}")

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

        Uses the Instructor library to guarantee schema compliance.
        The instructor client is lazily initialized on first use.

        Args:
            response_model: Pydantic model class defining the output schema
            messages: Conversation messages to send to the LLM
            max_retries: Number of retries if validation fails (default: 2)

        Returns:
            Instance of response_model with validated data
        """
        client = self._get_instructor_client()
        # Messages dict matches ChatCompletionMessageParam at runtime
        return await client.chat.completions.create(
            model=self.model,
            response_model=response_model,
            messages=[{"role": m.role, "content": m.content} for m in messages],  # type: ignore[arg-type]
            max_retries=max_retries,
        )

    def _get_instructor_client(self) -> AsyncInstructor:
        """Get or create the Instructor-patched async OpenAI client."""
        if self._instructor_client is None:
            import instructor
            from openai import AsyncOpenAI

            openai_client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout_s,
            )
            self._instructor_client = instructor.from_openai(openai_client)
        return self._instructor_client

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
