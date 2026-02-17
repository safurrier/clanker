"""Tests for the Clanker CLI commands."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from clanker_cli.main import cli
from tests.fakes import FakeLLM, FakeSTT, FakeTTS


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


# ── Helpers ──────────────────────────────────────────────────────────────


def _patch_factory(
    llm: FakeLLM | None = None,
    stt: FakeSTT | None = None,
    tts: FakeTTS | None = None,
):
    """Patch ProviderFactory methods to return fakes."""
    llm = llm or FakeLLM()
    stt = stt or FakeSTT()
    tts = tts or FakeTTS()
    return (
        patch(
            "clanker.providers.factory.ProviderFactory.get_llm",
            return_value=llm,
        ),
        patch(
            "clanker.providers.factory.ProviderFactory.get_stt",
            return_value=stt,
        ),
        patch(
            "clanker.providers.factory.ProviderFactory.get_tts",
            return_value=tts,
        ),
    )


# ── Chat ─────────────────────────────────────────────────────────────────


class TestChat:
    def test_chat_basic(self, runner: CliRunner) -> None:
        p_llm, p_stt, p_tts = _patch_factory(FakeLLM(reply_text="Hi from CLI"))
        with p_llm, p_stt, p_tts:
            result = runner.invoke(cli, ["chat", "Hello"])
        assert result.exit_code == 0
        assert "Hi from CLI" in result.output

    def test_chat_json(self, runner: CliRunner) -> None:
        p_llm, p_stt, p_tts = _patch_factory(FakeLLM(reply_text="response"))
        with p_llm, p_stt, p_tts:
            result = runner.invoke(cli, ["chat", "--json", "Hello"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["content"] == "response"
        assert data["role"] == "assistant"

    def test_chat_stdin(self, runner: CliRunner) -> None:
        p_llm, p_stt, p_tts = _patch_factory(FakeLLM(reply_text="stdin reply"))
        with p_llm, p_stt, p_tts:
            result = runner.invoke(cli, ["chat"], input="piped prompt\n")
        assert result.exit_code == 0
        assert "stdin reply" in result.output

    def test_chat_no_prompt_no_stdin(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["chat"])
        assert result.exit_code != 0

    def test_chat_missing_api_key(self, runner: CliRunner) -> None:
        with patch.dict("os.environ", {}, clear=True):
            result = runner.invoke(cli, ["chat", "Hello"])
        assert result.exit_code != 0
        assert "OPENAI_API_KEY" in result.output or "Error" in result.output


# ── Speak ────────────────────────────────────────────────────────────────


class TestSpeak:
    def test_speak_basic(self, runner: CliRunner, tmp_path: Path) -> None:
        out = tmp_path / "out.mp3"
        p_llm, p_stt, p_tts = _patch_factory(
            llm=FakeLLM(reply_text="spoken text"),
            tts=FakeTTS(audio_bytes=b"fake-audio"),
        )
        with p_llm, p_stt, p_tts:
            result = runner.invoke(
                cli, ["speak", "--voice", "v1", "-o", str(out), "Say something"]
            )
        assert result.exit_code == 0
        assert "spoken text" in result.output
        assert out.read_bytes() == b"fake-audio"

    def test_speak_no_voice_errors(self, runner: CliRunner) -> None:
        # Default persona has no tts_voice and no --voice flag
        p_llm, p_stt, p_tts = _patch_factory()
        with p_llm, p_stt, p_tts:
            result = runner.invoke(cli, ["speak", "Hello"])
        assert result.exit_code != 0
        assert "voice" in result.output.lower() or "voice" in result.stderr.lower()


# ── Shitpost ─────────────────────────────────────────────────────────────


class TestShitpost:
    def test_list_templates(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["shitpost", "--list-templates"])
        assert result.exit_code == 0
        assert len(result.output.strip().splitlines()) > 0

    def test_list_templates_json(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["shitpost", "--list-templates", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert "name" in data[0]

    def test_shitpost_generate(self, runner: CliRunner) -> None:
        p_llm, p_stt, p_tts = _patch_factory(
            FakeLLM(reply_text="epic shitpost content")
        )
        with p_llm, p_stt, p_tts:
            result = runner.invoke(cli, ["shitpost", "cats"])
        assert result.exit_code == 0
        assert "epic shitpost content" in result.output

    def test_shitpost_generate_json(self, runner: CliRunner) -> None:
        p_llm, p_stt, p_tts = _patch_factory(FakeLLM(reply_text="content"))
        with p_llm, p_stt, p_tts:
            result = runner.invoke(cli, ["shitpost", "--json", "cats"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["content"] == "content"
        assert "template" in data


# ── Meme ─────────────────────────────────────────────────────────────────


class TestMeme:
    def test_list_templates(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["meme", "--list-templates"])
        assert result.exit_code == 0
        assert len(result.output.strip().splitlines()) > 0

    def test_list_templates_json(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["meme", "--list-templates", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert "template_id" in data[0]

    def test_meme_generate(self, runner: CliRunner) -> None:
        fake_llm = FakeLLM(reply_text='["top text", "bottom text"]')
        p_llm, p_stt, p_tts = _patch_factory(llm=fake_llm)
        with p_llm, p_stt, p_tts:
            result = runner.invoke(cli, ["meme", "developers"])
        assert result.exit_code == 0
        assert "memegen.link" in result.output


# ── Transcribe ───────────────────────────────────────────────────────────


class TestTranscribe:
    @pytest.fixture()
    def wav_file(self, tmp_path: Path) -> Path:
        """Create a minimal mono 16-bit WAV file."""
        import wave

        path = tmp_path / "test.wav"
        sample_rate = 16000
        # 0.1 seconds of silence (1600 samples)
        samples = b"\x00\x00" * 1600
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(samples)
        return path

    def test_transcribe_basic(self, runner: CliRunner, wav_file: Path) -> None:
        p_llm, p_stt, p_tts = _patch_factory(stt=FakeSTT(transcript="hello world"))
        with p_llm, p_stt, p_tts:
            result = runner.invoke(cli, ["transcribe", "--no-vad", str(wav_file)])
        assert result.exit_code == 0
        assert "hello world" in result.output

    def test_transcribe_json(self, runner: CliRunner, wav_file: Path) -> None:
        p_llm, p_stt, p_tts = _patch_factory(stt=FakeSTT(transcript="hello"))
        with p_llm, p_stt, p_tts:
            result = runner.invoke(
                cli, ["transcribe", "--no-vad", "--json", str(wav_file)]
            )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["text"] == "hello"

    def test_transcribe_with_vad(self, runner: CliRunner, wav_file: Path) -> None:
        p_llm, p_stt, p_tts = _patch_factory(stt=FakeSTT(transcript="vad"))
        with p_llm, p_stt, p_tts:
            result = runner.invoke(cli, ["transcribe", str(wav_file)])
        # VAD on silence should detect no speech
        assert result.exit_code == 0

    def test_transcribe_nonexistent_file(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["transcribe", "/nonexistent.wav"])
        assert result.exit_code != 0


# ── Config ───────────────────────────────────────────────────────────────


class TestConfig:
    @pytest.fixture()
    def config_file(self, tmp_path: Path) -> Path:
        path = tmp_path / "config.yaml"
        path.write_text(
            textwrap.dedent("""\
            providers:
              llm: openai
              stt: openai
              tts: elevenlabs
            personas:
              - id: test
                display_name: Test Bot
                system_prompt: You are a test bot.
                tts_voice: voice123
        """)
        )
        return path

    def test_config_show(self, runner: CliRunner, config_file: Path) -> None:
        result = runner.invoke(cli, ["--config", str(config_file), "config", "show"])
        assert result.exit_code == 0
        assert "openai" in result.output
        assert "test" in result.output

    def test_config_show_no_config(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["config", "show"])
        assert result.exit_code != 0

    def test_config_personas(self, runner: CliRunner, config_file: Path) -> None:
        result = runner.invoke(
            cli, ["--config", str(config_file), "config", "personas"]
        )
        assert result.exit_code == 0
        assert "test" in result.output
        assert "Test Bot" in result.output

    def test_config_validate_valid(self, runner: CliRunner, config_file: Path) -> None:
        with patch.dict(
            "os.environ",
            {"OPENAI_API_KEY": "test-key", "ELEVENLABS_API_KEY": "test-key"},
        ):
            result = runner.invoke(cli, ["config", "validate", str(config_file)])
        assert result.exit_code == 0
        assert "valid" in result.output.lower()

    def test_config_validate_missing_env(
        self, runner: CliRunner, config_file: Path
    ) -> None:
        with patch.dict("os.environ", {}, clear=True):
            result = runner.invoke(cli, ["config", "validate", str(config_file)])
        assert result.exit_code != 0


# ── Top-level Options ────────────────────────────────────────────────────


class TestTopLevel:
    def test_help(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "chat" in result.output
        assert "speak" in result.output
        assert "shitpost" in result.output
        assert "meme" in result.output
        assert "transcribe" in result.output
        assert "config" in result.output

    def test_config_flag(self, runner: CliRunner, tmp_path: Path) -> None:
        cfg = tmp_path / "config.yaml"
        cfg.write_text(
            textwrap.dedent("""\
            providers:
              llm: openai
              stt: openai
              tts: elevenlabs
            personas:
              - id: custom
                display_name: Custom
                system_prompt: custom prompt
        """)
        )
        p_llm, p_stt, p_tts = _patch_factory(FakeLLM(reply_text="ok"))
        with p_llm, p_stt, p_tts:
            result = runner.invoke(cli, ["--config", str(cfg), "chat", "hi"])
        assert result.exit_code == 0

    def test_invalid_persona(self, runner: CliRunner, tmp_path: Path) -> None:
        cfg = tmp_path / "config.yaml"
        cfg.write_text(
            textwrap.dedent("""\
            providers:
              llm: openai
              stt: openai
              tts: elevenlabs
            personas:
              - id: alpha
                display_name: Alpha
                system_prompt: prompt
        """)
        )
        result = runner.invoke(
            cli, ["--config", str(cfg), "--persona", "nope", "chat", "hi"]
        )
        assert result.exit_code != 0
        assert "nope" in result.output or "nope" in result.stderr
