"""Entrypoint for running the Discord bot."""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

import discord
from aiohttp import web
from loguru import logger

from clanker.config import load_config
from clanker.models import Persona
from clanker.providers.factory import ProviderConfig, ProviderFactory

from .admin import AdminState
from .commands import BotDependencies, ClankerClient, register_commands
from .discord_adapter import VoiceSessionManager
from .health import HealthState, create_health_app
from .metrics import Metrics
from .voice_ingest import TranscriptBuffer


def configure_logging() -> None:
    """Configure loguru for the bot.

    Reads LOG_LEVEL from environment (default: INFO).
    Outputs colored logs to stderr.
    """
    import logging

    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    # Remove default handler and add configured one
    logger.remove()
    logger.add(
        sys.stderr,
        level=log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
        colorize=True,
    )
    logger.info("Logging configured", level=log_level)

    # Also configure stdlib logging for voice_recv to see packet-level debug info
    if log_level == "DEBUG":
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s | %(levelname)-8s | %(name)s - %(message)s",
        )
        # Enable voice_recv debug logs
        logging.getLogger("discord.ext.voice_recv").setLevel(logging.DEBUG)
        logging.getLogger("discord.gateway").setLevel(logging.DEBUG)
        logging.getLogger("discord.voice_state").setLevel(logging.DEBUG)


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
        provider_config = ProviderConfig(
            llm="openai", stt="openai", tts="elevenlabs", image="memegen"
        )
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

    llm_name = provider_config.llm
    stt_name = provider_config.stt
    tts_name = provider_config.tts
    image_name = provider_config.image or "none"
    logger.info(
        "Providers configured: llm={}, stt={}, tts={}, image={}",
        llm_name,
        stt_name,
        tts_name,
        image_name,
        llm=llm_name,
        stt=stt_name,
        tts=tts_name,
        image=image_name,
    )

    voice_manager = VoiceSessionManager()
    metrics = Metrics()
    admin_ids = _load_admin_ids()
    admin_state = AdminState()
    transcript_buffer = TranscriptBuffer()
    logger.debug("TranscriptBuffer initialized")
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
        transcript_buffer=transcript_buffer,
    )


def build_bot(deps: BotDependencies) -> ClankerClient:
    """Create the Discord client and register commands."""
    intents = discord.Intents.default()
    intents.message_content = True  # Required for reading thread messages
    bot = ClankerClient(intents=intents)
    register_commands(bot, deps)

    # Import here to avoid circular imports
    from .command_handlers.common import is_clanker_thread
    from .command_handlers.thread_chat import handle_thread_message

    @bot.event
    async def on_ready() -> None:
        if bot.user:
            logger.info("Bot ready as {}", bot.user.name)
            await bot.tree.sync()
            commands = await bot.tree.fetch_commands()
            logger.info(
                "Synced {} commands: {}", len(commands), [c.name for c in commands]
            )

    @bot.event
    async def on_message(message: discord.Message) -> None:
        """Auto-reply in clanker threads."""
        # Ignore bot's own messages
        if message.author.bot:
            return

        # Ignore DMs
        if not message.guild:
            return

        # Only respond in clanker threads
        if not is_clanker_thread(message.channel):
            return

        # Ignore empty messages
        if not message.content.strip():
            return

        # Process the message
        await handle_thread_message(message, deps)

    return bot


async def run_health_server(state: HealthState) -> None:
    """Run the health endpoint server."""
    app = create_health_app(state)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="127.0.0.1", port=8080)
    await site.start()


def _load_opus() -> None:
    """Load the Opus codec for Discord voice.

    Discord voice uses Opus for audio encoding/decoding. This must be loaded
    before any voice operations. Raises RuntimeError if opus is not available.
    """
    if discord.opus.is_loaded():
        logger.debug("Opus already loaded")
        return

    # Let discord.py find and load opus
    discord.opus._load_default()

    if not discord.opus.is_loaded():
        raise RuntimeError(
            "Opus codec not found. Install libopus: apt install libopus0"
        )

    logger.info("Opus codec loaded")


def main() -> None:
    """Run the bot."""
    configure_logging()
    logger.info("Clanker9000 starting up...")

    _load_opus()

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


def _load_admin_ids() -> set[int]:
    """Load admin user IDs from environment variable."""
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
            logger.warning("Invalid admin ID in CLANKER_ADMIN_IDS: {!r}", value)
    return result


if __name__ == "__main__":
    main()
