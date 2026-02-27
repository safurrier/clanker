# Provider System

How providers work, how to add new ones, and the factory pattern.

## Overview

Providers are the integration layer between the Clanker SDK and external APIs. They are defined as Python `Protocol` classes for loose coupling and easy testing.

## Provider Protocols

All protocols in `src/clanker/providers/base.py`:

### LLM
```python
class LLM(Protocol):
    async def generate(
        self, context: Context, messages: list[Message], params: dict | None = None
    ) -> Message: ...
```

### StructuredLLM
```python
@runtime_checkable
class StructuredLLM(Protocol):
    async def generate_structured(
        self, response_model: type[T], messages: list[Message], max_retries: int = 2
    ) -> T: ...
```
Separate protocol for LLMs supporting structured outputs via Pydantic models (uses Instructor library). Not all LLM implementations need to support this.

### STT
```python
class STT(Protocol):
    async def transcribe(
        self, audio_bytes: bytes, sample_rate_hz: int = 16000, params: dict | None = None
    ) -> str: ...
```
`audio_bytes` must be WAV-formatted (not raw PCM).

### TTS
```python
class TTS(Protocol):
    async def synthesize(
        self, text: str, voice: str, params: dict | None = None
    ) -> bytes: ...
```

### ImageGen
```python
class ImageGen(Protocol):
    async def generate(self, params: dict) -> bytes | str: ...
```

## Current Implementations

| Protocol | Provider | Module | Required Env |
|----------|----------|--------|-------------|
| LLM | OpenAI | `providers/openai/llm.py` | `OPENAI_API_KEY` |
| LLM | Anthropic | `providers/anthropic/llm.py` | `ANTHROPIC_API_KEY` |
| StructuredLLM | OpenAI | `providers/openai/llm.py` | `OPENAI_API_KEY` |
| StructuredLLM | Anthropic | `providers/anthropic/llm.py` | `ANTHROPIC_API_KEY` |
| STT | OpenAI Whisper | `providers/openai/stt.py` | `OPENAI_API_KEY` |
| TTS | ElevenLabs | `providers/elevenlabs/tts.py` | `ELEVENLABS_API_KEY` |
| ImageGen | Memegen | `providers/memegen/image.py` | None |

## ProviderFactory

`src/clanker/providers/factory.py` — central registry that constructs providers lazily:

```python
class ProviderFactory:
    def get_llm(self, name: str) -> LLM: ...
    def get_stt(self, name: str) -> STT: ...
    def get_tts(self, name: str) -> TTS: ...
    def get_image(self, name: str) -> ImageGen: ...
    def validate(self, config: ProviderConfig) -> None: ...
```

Key behaviors:
- **Lazy construction**: Providers are built when requested, not at factory creation. This lets commands like `config show` work without API keys.
- **Environment validation**: `_require_env()` checks for required env vars at construction time, raising `ValueError` if missing.
- **Registry pattern**: Each provider type has a `dict[str, Callable[[], T]]` mapping names to builder functions.

### ProviderConfig
```python
@dataclass(frozen=True)
class ProviderConfig:
    llm: str          # e.g., "openai"
    stt: str          # e.g., "openai"
    tts: str          # e.g., "elevenlabs"
    image: str | None  # e.g., "memegen"
```

## Error Handling

`src/clanker/providers/errors.py` defines:

- `TransientProviderError` — temporary failures (rate limits, timeouts). Can be retried.
- `PermanentProviderError` — permanent failures (invalid API key, unsupported operation). Should not retry.

Both the CLI and Discord bot catch these and convert to user-friendly error messages.

## Adding a New Provider

### 1. Create the implementation

```python
# src/clanker/providers/anthropic/llm.py
from __future__ import annotations

from dataclasses import dataclass

import httpx

from ..base import LLM
from ..errors import PermanentProviderError, TransientProviderError
from ...models import Context, Message


@dataclass(frozen=True)
class AnthropicLLM:
    api_key: str
    model: str = "claude-sonnet-4-5-20250514"

    async def generate(
        self, context: Context, messages: list[Message], params: dict | None = None
    ) -> Message:
        async with httpx.AsyncClient() as client:
            # ... implementation
            pass
```

### 2. Register in factory

```python
# In ProviderFactory.__init__():
self._llm_registry["anthropic"] = lambda: AnthropicLLM(
    api_key=_require_env("ANTHROPIC_API_KEY")
)
```

### 3. Add a test fake

```python
# tests/fakes.py
@dataclass
class FakeAnthropicLLM:
    reply_text: str = "fake response"

    async def generate(self, context, messages, params=None):
        return Message(role="assistant", content=self.reply_text)
```

### 4. Add tests

- Unit test the adapter with mocked HTTP
- Add to `tests/test_provider_factory.py` for factory registration
- Add network smoke test in `tests/network/` if desired

## Audio Utilities

`src/clanker/providers/audio_utils.py` provides format conversion used by voice pipeline:

- `stereo_to_mono(pcm_bytes)` — average left/right channels
- `convert_pcm(data, from_format, to_format)` — full format conversion
- `resample_pcm(data, from_rate, to_rate)` — sample rate conversion

These are provider-adjacent utilities used between Discord audio capture and STT providers.

## Test Fakes

`tests/fakes.py` provides protocol-compatible test doubles:

| Fake | Protocol | Default Behavior |
|------|----------|-----------------|
| `FakeLLM` | `LLM` | Returns `Message(role="assistant", content=reply_text)` |
| `FakeSTT` | `STT` | Returns configured transcript string |
| `FakeTTS` | `TTS` | Returns configured audio bytes |
| `FakeImage` | `ImageGen` | Returns mock image data |

These satisfy the Protocol contracts via structural typing — no inheritance needed.
