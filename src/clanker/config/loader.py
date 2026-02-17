"""Load YAML configuration for Clanker."""

from __future__ import annotations

from pathlib import Path

import yaml

from ..providers.factory import ProviderConfig
from .models import ClankerConfig, PersonaConfig


def load_config(path: Path) -> ClankerConfig:
    """Load Clanker configuration from YAML."""
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    providers = payload.get("providers") or {}
    provider_config = ProviderConfig(
        llm=_require_str(providers, "llm"),
        stt=_require_str(providers, "stt"),
        tts=_require_str(providers, "tts"),
        image=providers.get("image"),
    )
    personas_payload = payload.get("personas") or []
    personas = [
        PersonaConfig(
            id=_require_str(item, "id"),
            display_name=_require_str(item, "display_name"),
            system_prompt=_require_str(item, "system_prompt"),
            tts_voice=item.get("tts_voice"),
            providers=item.get("providers"),
        )
        for item in personas_payload
    ]
    default_persona_id = payload.get("default_persona") or _default_persona_id(personas)
    return ClankerConfig(
        provider_config=provider_config,
        personas=personas,
        default_persona_id=default_persona_id,
    )


def _default_persona_id(personas: list[PersonaConfig]) -> str:
    if not personas:
        raise ValueError("No personas defined in configuration")
    return personas[0].id


def _require_str(payload: dict, key: str) -> str:
    value = payload.get(key)
    if not value:
        raise ValueError(f"Missing required config field: {key}")
    return str(value)
