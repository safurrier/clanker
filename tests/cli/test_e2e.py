"""End-to-end CLI tests that hit real APIs.

Run with: uv run pytest tests/cli/test_e2e.py -m network
Requires: OPENAI_API_KEY environment variable.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from clanker_cli.main import cli

pytestmark = pytest.mark.network

needs_openai = pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set",
)


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture(scope="module")
def wav_file() -> Path:
    """Return the test monologue WAV file."""
    path = Path(__file__).parent.parent / "data" / "sample1_monologue.wav"
    if not path.exists():
        pytest.skip("Test audio file not available")
    return path


# ── Chat ─────────────────────────────────────────────────────────────────


class TestChatE2E:
    @needs_openai
    def test_chat_returns_response(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["chat", "Say the word 'hello' and nothing else"])
        assert result.exit_code == 0
        assert len(result.output.strip()) > 0

    @needs_openai
    def test_chat_json_valid(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["chat", "--json", "What is 1+1?"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["role"] == "assistant"
        assert len(data["content"]) > 0

    @needs_openai
    def test_chat_stdin(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["chat"], input="Say hi\n")
        assert result.exit_code == 0
        assert len(result.output.strip()) > 0


# ── Shitpost ─────────────────────────────────────────────────────────────


class TestShitpostE2E:
    def test_list_templates_no_api_key(self, runner: CliRunner) -> None:
        """List templates works without any API key."""
        result = runner.invoke(cli, ["shitpost", "--list-templates"])
        assert result.exit_code == 0
        lines = result.output.strip().splitlines()
        assert len(lines) >= 1

    def test_list_templates_json(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["shitpost", "--list-templates", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert all("name" in t for t in data)

    @needs_openai
    def test_shitpost_generates_content(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["shitpost", "cats"])
        assert result.exit_code == 0
        assert len(result.output.strip()) > 0

    @needs_openai
    def test_shitpost_json(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["shitpost", "--json", "dogs"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "content" in data
        assert "template" in data


# ── Meme ─────────────────────────────────────────────────────────────────


class TestMemeE2E:
    def test_list_templates_no_api_key(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["meme", "--list-templates"])
        assert result.exit_code == 0
        assert len(result.output.strip().splitlines()) > 10

    def test_list_templates_json(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["meme", "--list-templates", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert all("template_id" in t for t in data)

    @needs_openai
    def test_meme_generates_url(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["meme", "programming"])
        assert result.exit_code == 0
        assert "memegen.link" in result.output

    @needs_openai
    def test_meme_json(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["meme", "--json", "mondays"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "url" in data
        assert "lines" in data
        assert "memegen.link" in data["url"]


# ── Transcribe ───────────────────────────────────────────────────────────


class TestTranscribeE2E:
    @needs_openai
    def test_transcribe_with_vad(self, runner: CliRunner, wav_file: Path) -> None:
        result = runner.invoke(cli, ["transcribe", str(wav_file)])
        assert result.exit_code == 0
        text = result.output.strip().lower()
        # sample1_monologue.wav says "Thank you for watching my video"
        assert "thank" in text or "video" in text or "watching" in text

    @needs_openai
    def test_transcribe_no_vad(self, runner: CliRunner, wav_file: Path) -> None:
        result = runner.invoke(cli, ["transcribe", "--no-vad", str(wav_file)])
        assert result.exit_code == 0
        assert len(result.output.strip()) > 0

    @needs_openai
    def test_transcribe_json(self, runner: CliRunner, wav_file: Path) -> None:
        result = runner.invoke(cli, ["transcribe", "--json", str(wav_file)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "text" in data
        assert "segments" in data

    def test_transcribe_nonexistent_file(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["transcribe", "/nonexistent.wav"])
        assert result.exit_code != 0


# ── Config ───────────────────────────────────────────────────────────────


class TestConfigE2E:
    def test_help_shows_all_commands(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        for cmd in ("chat", "speak", "shitpost", "meme", "transcribe", "config"):
            assert cmd in result.output

    def test_config_show_no_config_errors(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["config", "show"])
        assert result.exit_code != 0
        assert "config" in result.output.lower()

    def test_config_personas_no_config_errors(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["config", "personas"])
        assert result.exit_code != 0
