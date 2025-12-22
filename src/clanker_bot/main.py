"""Entrypoint for running the Discord bot."""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

import discord
from aiohttp import web

from clanker.config import load_config
from clanker.models import Persona
from clanker.providers.factory import ProviderConfig, ProviderFactory

from .admin import AdminState
from .commands import BotDependencies, ClankerClient, register_commands
from .discord_adapter import VoiceSessionManager
from .health import HealthState, create_health_app
from .metrics import Metrics


def build_dependencies() -> BotDependencies:
    """Build dependencies from environment configuration."""
    config_path = os.getenv("CLANKER_CONFIG_PATH")
    if config_path:
        clanker_config = load_config(Path(config_path))
        provider_config = clanker_config.provider_config
        persona_config = next(
            persona
            for persona in clanker_config.personas
            if persona.id == clanker_config.default_persona_id
        )
        persona = Persona(
            id=persona_config.id,
            display_name=persona_config.display_name,
            system_prompt=persona_config.system_prompt,
            tts_voice=persona_config.tts_voice,
            providers=persona_config.providers,
        )
    else:
        provider_config = ProviderConfig(llm="openai", stt="openai", tts="elevenlabs")
        persona = Persona(
            id="default",
            display_name="Clanker",
            system_prompt="You are Clanker9000, a helpful bot.",
            tts_voice=None,
            providers=None,
        )
    factory = ProviderFactory()
    llm = factory.get_llm(provider_config.llm)
    stt = factory.get_stt(provider_config.stt)
    tts = factory.get_tts(provider_config.tts)
    image = factory.get_image(provider_config.image) if provider_config.image else None
    voice_manager = VoiceSessionManager()
    metrics = Metrics()
    admin_ids = _load_admin_ids()
    admin_state = AdminState()
    voice_ingest_enabled = os.getenv("CLANKER_VOICE_INGEST_ENABLED") == "1"
    return BotDependencies(
        llm=llm,
        stt=stt,
        tts=tts,
        image=image,
        persona=persona,
        voice_manager=voice_manager,
        metrics=metrics,
        admin_user_ids=admin_ids,
        admin_state=admin_state,
        voice_ingest_enabled=voice_ingest_enabled,
    )


def build_bot(deps: BotDependencies) -> ClankerClient:
    """Create the Discord client and register commands."""
    intents = discord.Intents.default()
    intents.message_content = False
    bot = ClankerClient(intents=intents)
    register_commands(bot, deps)

    @bot.event
    async def on_ready() -> None:
        if bot.user:
            await bot.tree.sync()

    return bot


async def run_health_server(state: HealthState) -> None:
    """Run the health endpoint server."""
    app = create_health_app(state)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="127.0.0.1", port=8080)
    await site.start()


def main() -> None:
    """Run the bot."""
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("Missing DISCORD_TOKEN")
    deps = build_dependencies()
    bot = build_bot(deps)
    state = HealthState(
        started_at=time.time(),
        active_voice_provider=deps.voice_manager.is_busy,
        version="0.1.0",
    )

    async def runner() -> None:
        await run_health_server(state)
        await bot.start(token)

    asyncio.run(runner())


if __name__ == "__main__":
    main()


def _load_admin_ids() -> set[int]:
    raw = os.getenv("CLANKER_ADMIN_IDS", "")
    if not raw:
        return set()
    result = set()
    for value in raw.split(","):
        value = value.strip()
        if not value:
            continue
        try:
            result.add(int(value))
        except ValueError:
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(f"Invalid admin ID in CLANKER_ADMIN_IDS: {value!r}")
    return result
