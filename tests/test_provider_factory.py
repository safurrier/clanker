"""Tests for ProviderFactory."""

import pytest

from clanker.providers.factory import ProviderConfig, ProviderFactory


def test_factory_requires_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    factory = ProviderFactory()
    config = ProviderConfig(llm="openai", stt="openai", tts="elevenlabs")
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        factory.get_llm(config.llm)
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        factory.get_stt(config.stt)
    with pytest.raises(ValueError, match="ELEVENLABS_API_KEY"):
        factory.get_tts(config.tts)


def test_factory_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test")
    factory = ProviderFactory()
    config = ProviderConfig(llm="openai", stt="openai", tts="elevenlabs")
    assert factory.get_llm(config.llm)
    assert factory.get_stt(config.stt)
    assert factory.get_tts(config.tts)
