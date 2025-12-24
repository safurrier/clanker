"""Pytest fixtures for Clanker tests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from clanker.models import Context, Message, Persona


@pytest.fixture()
def persona() -> Persona:
    return Persona(
        id="test",
        display_name="Test Persona",
        system_prompt="You are a test persona.",
        tts_voice="voice",
        providers={},
    )


@pytest.fixture()
def context(persona: Persona) -> Context:
    return Context(
        request_id="req-1",
        user_id=123,
        guild_id=456,
        channel_id=789,
        persona=persona,
        messages=[Message(role="user", content="Hi")],
        metadata={},
    )


@dataclass
class FakeFollowup:
    """Capture followup messages for tests."""

    messages: list[str]

    async def send(self, content: str, **_kwargs: object) -> None:
        self.messages.append(content)


@dataclass
class FakeInteractionResponse:
    """Capture interaction responses for tests."""

    messages: list[str]
    deferred: bool = False

    async def send_message(self, content: str, **_kwargs: object) -> None:
        self.messages.append(content)

    async def defer(self, **_kwargs: object) -> None:
        self.deferred = True


@dataclass
class FakeThread:
    """Capture thread messages."""

    messages: list[str]

    async def send(self, content: str, **_kwargs: Any) -> None:
        self.messages.append(content)


@dataclass
class FakeChannel:
    """Fake channel that can create threads."""

    thread: FakeThread

    async def create_thread(self, name: str, **_kwargs: object) -> FakeThread:
        self.thread.messages.append(f"thread:{name}")
        return self.thread


@dataclass
class FakeInteraction:
    """Minimal interaction stub for command tests."""

    user: object
    guild_id: int | None
    channel_id: int | None
    response: FakeInteractionResponse
    followup: FakeFollowup
    channel: FakeChannel | None = None


@dataclass
class FakeUser:
    id: int


@pytest.fixture()
def fake_interaction() -> FakeInteraction:
    messages: list[str] = []
    response = FakeInteractionResponse(messages=messages)
    followup = FakeFollowup(messages=messages)
    thread = FakeThread(messages=[])
    channel = FakeChannel(thread=thread)
    return FakeInteraction(
        user=FakeUser(id=42),
        guild_id=999,
        channel_id=321,
        response=response,
        followup=followup,
        channel=channel,
    )


# Audio test fixtures


@dataclass(frozen=True)
class AudioSample:
    """Test audio sample with metadata."""

    path: Path
    pcm_path: Path
    sample_rate: int
    duration_sec: float
    transcript: str
    description: str
    metadata: dict


@pytest.fixture(scope="session")
def test_data_dir() -> Path:
    """Return path to test data directory."""
    return Path(__file__).parent / "data"


@pytest.fixture(scope="session")
def audio_metadata(test_data_dir: Path) -> dict:
    """Load test audio metadata."""
    with open(test_data_dir / "metadata.json") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def sample_monologue(test_data_dir: Path, audio_metadata: dict) -> AudioSample:
    """5 second monologue sample."""
    meta = audio_metadata["samples"][0]
    return AudioSample(
        path=test_data_dir / meta["filename"],
        pcm_path=test_data_dir / "sample1_monologue.pcm",
        sample_rate=meta["sample_rate"],
        duration_sec=meta["duration_sec"],
        transcript=meta["transcript"],
        description=meta["description"],
        metadata=meta,
    )


@pytest.fixture(scope="session")
def sample_paused(test_data_dir: Path, audio_metadata: dict) -> AudioSample:
    """Two utterances with 1 second pause."""
    meta = audio_metadata["samples"][1]
    return AudioSample(
        path=test_data_dir / meta["filename"],
        pcm_path=test_data_dir / "sample2_paused.pcm",
        sample_rate=meta["sample_rate"],
        duration_sec=meta["duration_sec"],
        transcript=meta["transcript"],
        description=meta["description"],
        metadata=meta,
    )


@pytest.fixture(scope="session")
def sample_multispeaker(test_data_dir: Path, audio_metadata: dict) -> AudioSample:
    """Multi-speaker conversation simulation."""
    meta = audio_metadata["samples"][2]
    return AudioSample(
        path=test_data_dir / meta["filename"],
        pcm_path=test_data_dir / "sample3_multispeaker.pcm",
        sample_rate=meta["sample_rate"],
        duration_sec=meta["duration_sec"],
        transcript=meta["transcript"],
        description=meta["description"],
        metadata=meta,
    )
