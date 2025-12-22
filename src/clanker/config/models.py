"""Config models for Clanker."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ..providers.factory import ProviderConfig


@dataclass(frozen=True)
class PersonaConfig:
    """Persona configuration loaded from YAML."""

    id: str
    display_name: str
    system_prompt: str
    tts_voice: str | None = None
    providers: Mapping[str, str] | None = None


@dataclass(frozen=True)
class ClankerConfig:
    """Top-level Clanker configuration."""

    provider_config: ProviderConfig
    personas: list[PersonaConfig]
    default_persona_id: str
