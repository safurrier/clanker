"""Voice activity detection utilities."""

from __future__ import annotations

import audioop
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SpeechSegment:
    """Represents a segment of detected speech in milliseconds."""

    start_ms: int
    end_ms: int


class SpeechDetector(Protocol):
    """Protocol for speech detection implementations."""

    def detect(self, pcm_bytes: bytes, sample_rate_hz: int) -> list[SpeechSegment]:
        """Detect speech segments from raw PCM bytes."""


@dataclass(frozen=True)
class EnergyVAD:
    """Energy-based speech detector using RMS thresholding."""

    frame_ms: int = 30
    threshold: int = 500
    padding_ms: int = 300

    def detect(self, pcm_bytes: bytes, sample_rate_hz: int) -> list[SpeechSegment]:
        frame_size = int(sample_rate_hz * self.frame_ms / 1000) * 2
        padding_frames = max(1, self.padding_ms // self.frame_ms)
        segments: list[SpeechSegment] = []
        speech_start: int | None = None
        silence_frames = 0

        for index in range(0, len(pcm_bytes), frame_size):
            frame = pcm_bytes[index : index + frame_size]
            if len(frame) < frame_size:
                break
            rms = audioop.rms(frame, 2)
            is_speech = rms >= self.threshold
            frame_start_ms = int(index / 2 / sample_rate_hz * 1000)
            frame_end_ms = int((index + frame_size) / 2 / sample_rate_hz * 1000)

            if is_speech:
                if speech_start is None:
                    speech_start = frame_start_ms
                silence_frames = 0
            else:
                if speech_start is not None:
                    silence_frames += 1
                    if silence_frames >= padding_frames:
                        segments.append(
                            SpeechSegment(start_ms=speech_start, end_ms=frame_end_ms)
                        )
                        speech_start = None
                        silence_frames = 0

        if speech_start is not None:
            end_ms = int(len(pcm_bytes) / 2 / sample_rate_hz * 1000)
            segments.append(SpeechSegment(start_ms=speech_start, end_ms=end_ms))

        return segments


class SileroVAD:
    """Silero VAD-based speech detector (requires torch/numpy)."""

    def __init__(self, warmup: bool = False) -> None:
        self._model = None
        self._torch = None
        self._np = None
        if warmup:
            self._load()

    def _load(self) -> None:
        if self._model is not None:
            return

        try:
            import numpy as np
            import torch
        except ImportError as e:
            msg = (
                "Silero VAD requires torch and numpy. "
                "Install with: uv pip install 'clanker9000[voice]'"
            )
            raise RuntimeError(msg) from e

        try:
            model, _ = torch.hub.load(
                repo_or_dir="snakers4/silero-vad",
                model="silero_vad",
                force_reload=False,
                onnx=True,
            )
        except Exception as e:
            msg = (
                f"Failed to load Silero VAD model: {e}. "
                "Ensure you have network access or the model is cached."
            )
            raise RuntimeError(msg) from e

        self._model = model
        self._torch = torch
        self._np = np

    def detect(self, pcm_bytes: bytes, sample_rate_hz: int) -> list[SpeechSegment]:
        self._load()
        torch = self._torch
        np = self._np
        if torch is None or np is None or self._model is None:
            raise RuntimeError("Silero VAD failed to initialize.")

        samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype("float32") / 32768.0
        audio = torch.from_numpy(samples)
        if sample_rate_hz != 16000:
            audio = torch.nn.functional.interpolate(
                audio.unsqueeze(0).unsqueeze(0),
                scale_factor=16000 / sample_rate_hz,
                mode="linear",
                align_corners=False,
            ).squeeze()
            sample_rate_hz = 16000

        probs: list[float] = []
        window_size = 512
        for index in range(0, len(audio), window_size):
            window = audio[index : index + window_size]
            if len(window) < window_size:
                break
            probs.append(self._model(window, sample_rate_hz).item())

        self._model.reset_states()

        # Calculate actual window duration based on window size and sample rate
        window_duration_ms = int((window_size / sample_rate_hz) * 1000)

        segments: list[SpeechSegment] = []
        speaking_start: int | None = None
        for idx, prob in enumerate(probs):
            start_ms = idx * window_duration_ms
            end_ms = start_ms + window_duration_ms
            if prob >= 0.4:
                if speaking_start is None:
                    speaking_start = start_ms
            else:
                if speaking_start is not None:
                    segments.append(
                        SpeechSegment(start_ms=speaking_start, end_ms=end_ms)
                    )
                    speaking_start = None

        if speaking_start is not None:
            segments.append(
                SpeechSegment(
                    start_ms=speaking_start,
                    end_ms=int(len(audio) / sample_rate_hz * 1000),
                )
            )

        return segments


def detect_speech_segments(
    pcm_bytes: bytes,
    sample_rate_hz: int,
    detector: SpeechDetector | None = None,
) -> list[SpeechSegment]:
    """Detect speech segments using the provided detector."""
    return (detector or EnergyVAD()).detect(pcm_bytes, sample_rate_hz)


def resolve_detector(prefer_silero: bool = True) -> SpeechDetector:
    """Resolve the default speech detector, preferring Silero when available."""
    if not prefer_silero:
        return EnergyVAD()
    try:
        detector = SileroVAD()
        detector._load()
        return detector
    except Exception:
        return EnergyVAD()
