"""Spike for voice VAD + chunking."""

import wave

from clanker.voice.chunker import chunk_segments
from clanker.voice.vad import detect_speech_segments


def main() -> None:
    with wave.open("tests/audio_fixtures/test_tone.wav", "rb") as wf:
        pcm_bytes = wf.readframes(wf.getnframes())
        sample_rate = wf.getframerate()

    segments = detect_speech_segments(pcm_bytes, sample_rate)
    chunks = chunk_segments(segments)

    for segment in segments:
        print("segment", segment)
    for chunk in chunks:
        print("chunk", chunk)


if __name__ == "__main__":
    main()
