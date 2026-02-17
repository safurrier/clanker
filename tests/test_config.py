"""Tests for configuration loading."""

from pathlib import Path

import pytest

from clanker.config import load_config


def test_load_config(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
providers:
  llm: openai
  stt: openai
  tts: elevenlabs
  image: memegen
personas:
  - id: default
    display_name: Clanker
    system_prompt: Hello
""",
        encoding="utf-8",
    )
    config = load_config(config_path)
    assert config.provider_config.llm == "openai"
    assert config.default_persona_id == "default"


def test_load_config_requires_persona(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
providers:
  llm: openai
  stt: openai
  tts: elevenlabs
personas: []
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="No personas"):
        load_config(config_path)
