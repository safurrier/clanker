"""Transcribe command."""

from __future__ import annotations

import io
import wave
from pathlib import Path

import click

from clanker.providers.errors import PermanentProviderError, TransientProviderError
from clanker.voice.vad import EnergyVAD, detect_speech_segments, resolve_detector
from clanker_cli.main import CliContext, run_async
from clanker_cli.output import output_json, output_text


@click.command()
@click.argument("audio_file", type=click.Path(exists=True, path_type=Path))
@click.option("--vad/--no-vad", default=True, show_default=True, help="Use VAD.")
@click.option(
    "--vad-type",
    type=click.Choice(["silero", "energy"]),
    default="energy",
    show_default=True,
    help="VAD implementation.",
)
@click.option("--json", "use_json", is_flag=True, help="Output as JSON.")
@click.pass_obj
def transcribe(
    ctx: CliContext,
    audio_file: Path,
    vad: bool,
    vad_type: str,
    use_json: bool,
) -> None:
    """Transcribe an audio file (WAV)."""
    run_async(_transcribe(ctx, audio_file, vad, vad_type, use_json))


async def _transcribe(
    ctx: CliContext,
    audio_file: Path,
    use_vad: bool,
    vad_type: str,
    use_json: bool,
) -> None:
    pcm_bytes, sample_rate = _read_wav(audio_file)

    stt_name = ctx.config.provider_config.stt if ctx.config else "openai"
    try:
        stt = ctx.factory.get_stt(stt_name)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    if use_vad:
        detector = (
            resolve_detector(prefer_silero=True)
            if vad_type == "silero"
            else EnergyVAD()
        )
        segments = detect_speech_segments(pcm_bytes, sample_rate, detector=detector)
        if ctx.verbose:
            for seg in segments:
                click.echo(f"Speech: {seg.start_ms}ms - {seg.end_ms}ms", err=True)
        # Concatenate speech segments for transcription
        bytes_per_ms = sample_rate * 2 // 1000
        speech_audio = b"".join(
            pcm_bytes[seg.start_ms * bytes_per_ms : seg.end_ms * bytes_per_ms]
            for seg in segments
        )
        if not speech_audio:
            if use_json:
                output_json({"text": "", "segments": 0})
            else:
                output_text("(no speech detected)")
            return
        audio_to_transcribe = _pcm_to_wav(speech_audio, sample_rate)
    else:
        segments = []
        audio_to_transcribe = _pcm_to_wav(pcm_bytes, sample_rate)

    try:
        text = await stt.transcribe(audio_to_transcribe, sample_rate_hz=sample_rate)
    except (TransientProviderError, PermanentProviderError) as exc:
        raise click.ClickException(str(exc)) from exc

    if use_json:
        output_json(
            {
                "text": text,
                "segments": len(segments),
            }
        )
    else:
        output_text(text)


def _read_wav(path: Path) -> tuple[bytes, int]:
    """Read a WAV file and return (pcm_bytes, sample_rate)."""
    with wave.open(str(path), "rb") as wf:
        if wf.getsampwidth() != 2:
            raise click.ClickException("Only 16-bit WAV files are supported.")
        if wf.getnchannels() != 1:
            raise click.ClickException(
                "Only mono WAV files are supported. Convert with: "
                "ffmpeg -i input.wav -ac 1 output.wav"
            )
        sample_rate = wf.getframerate()
        pcm_bytes = wf.readframes(wf.getnframes())
    return pcm_bytes, sample_rate


def _pcm_to_wav(pcm_bytes: bytes, sample_rate: int) -> bytes:
    """Wrap raw PCM bytes in a WAV container (mono 16-bit)."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()
