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


@dataclass(frozen=True)
class LibriSpeechSample:
    """LibriSpeech audio sample with ground truth transcript."""

    id: str
    speaker_id: str
    pcm_path: Path
    flac_path: Path | None
    transcript: str
    sample_rate: int


@dataclass(frozen=True)
class AMISpeakerSample:
    """AMI Corpus speaker audio sample."""

    speaker: str
    speaker_index: int
    pcm_path: Path
    wav_path: Path | None
    segments: list[tuple[float, float]]  # (start_sec, end_sec) pairs
    sample_rate: int


@dataclass(frozen=True)
class AMIMeetingSample:
    """AMI Corpus meeting with multiple speakers."""

    meeting_id: str
    speakers: list[AMISpeakerSample]
    mixed_pcm_path: Path | None
    total_duration_sec: float
    sample_rate: int


@pytest.fixture(scope="session")
def test_data_dir() -> Path:
    """Return path to test data directory."""
    return Path(__file__).parent / "data"


@pytest.fixture(scope="session")
def audio_metadata(test_data_dir: Path) -> dict:
    """Load test audio metadata."""
    with (test_data_dir / "metadata.json").open() as f:
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


# LibriSpeech fixtures


@pytest.fixture(scope="session")
def librispeech_dir(test_data_dir: Path) -> Path:
    """Return path to LibriSpeech test data directory."""
    return test_data_dir / "librispeech"


@pytest.fixture(scope="session")
def librispeech_available(librispeech_dir: Path) -> bool:
    """Check if LibriSpeech samples are available."""
    metadata_path = librispeech_dir / "metadata.json"
    if not metadata_path.exists():
        return False
    with metadata_path.open() as f:
        metadata = json.load(f)
    return len(metadata.get("samples", [])) > 0


@pytest.fixture(scope="session")
def librispeech_samples(
    librispeech_dir: Path, librispeech_available: bool
) -> list[LibriSpeechSample]:
    """Load all LibriSpeech test samples.

    Returns empty list if samples not downloaded.
    Use librispeech_available fixture to skip tests when unavailable.
    """
    if not librispeech_available:
        return []

    with (librispeech_dir / "metadata.json").open() as f:
        metadata = json.load(f)

    samples = []
    for sample_meta in metadata.get("samples", []):
        pcm_path = librispeech_dir / sample_meta["pcm_file"]
        flac_path = librispeech_dir / sample_meta.get("flac_file", "")

        if pcm_path.exists():
            samples.append(
                LibriSpeechSample(
                    id=sample_meta["id"],
                    speaker_id=sample_meta["speaker_id"],
                    pcm_path=pcm_path,
                    flac_path=flac_path if flac_path.exists() else None,
                    transcript=sample_meta["transcript"],
                    sample_rate=sample_meta.get("sample_rate", 16000),
                )
            )

    return samples


# AMI Corpus fixtures


@pytest.fixture(scope="session")
def ami_dir(test_data_dir: Path) -> Path:
    """Return path to AMI Corpus test data directory."""
    return test_data_dir / "ami"


@pytest.fixture(scope="session")
def ami_available(ami_dir: Path) -> bool:
    """Check if AMI Corpus samples are available."""
    metadata_path = ami_dir / "metadata.json"
    if not metadata_path.exists():
        return False
    with metadata_path.open() as f:
        metadata = json.load(f)
    return len(metadata.get("speakers", [])) > 0


@pytest.fixture(scope="session")
def ami_meeting_sample(ami_dir: Path, ami_available: bool) -> AMIMeetingSample | None:
    """Load AMI Corpus meeting sample with multiple speakers.

    Returns None if samples not downloaded.
    """
    if not ami_available:
        return None

    with (ami_dir / "metadata.json").open() as f:
        metadata = json.load(f)

    speakers = []
    for speaker_meta in metadata.get("speakers", []):
        pcm_path = ami_dir / speaker_meta["pcm_file"]
        wav_file = speaker_meta.get("wav_file")
        wav_path = ami_dir / wav_file if wav_file else None

        # Handle segment format (may be list of lists or list of tuples)
        segments = [
            (float(s[0]), float(s[1])) for s in speaker_meta.get("segments", [])
        ]

        if pcm_path.exists():
            speakers.append(
                AMISpeakerSample(
                    speaker=speaker_meta["speaker"],
                    speaker_index=speaker_meta.get("speaker_index", 0),
                    pcm_path=pcm_path,
                    wav_path=wav_path if wav_path and wav_path.exists() else None,
                    segments=segments,
                    sample_rate=speaker_meta.get("sample_rate", 16000),
                )
            )

    if not speakers:
        return None

    mixed_file = metadata.get("mixed_file")
    mixed_path = ami_dir / mixed_file if mixed_file else None

    return AMIMeetingSample(
        meeting_id=metadata.get("meeting_id", metadata.get("source", "synthetic")),
        speakers=speakers,
        mixed_pcm_path=mixed_path if mixed_path and mixed_path.exists() else None,
        total_duration_sec=metadata.get("total_duration_sec", 0.0),
        sample_rate=metadata.get("sample_rate", 16000),
    )
