"""Entrypoint for running the Discord bot."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path

import discord
from aiohttp import web
from loguru import logger

from clanker.config import load_config
from clanker.models import Persona
from clanker.providers.factory import ProviderConfig, ProviderFactory

from .commands import BotDependencies, ClankerClient, register_commands
from .discord_adapter import VoiceSessionManager
from .health import HealthState, create_health_app
from .metrics import Metrics
from .persistence import SqlFeedbackStore
from .voice_actor import USE_VOICE_ACTOR, VoiceActor
from .voice_ingest import TranscriptBuffer
from .voice_resilience import VoiceReconnector

# How long to wait before auto-leaving an empty voice channel (seconds)
AUTO_LEAVE_GRACE_PERIOD = 5.0


def configure_logging() -> None:
    """Configure loguru for the bot.

    Reads from environment:
    - LOG_LEVEL: Base log level (default: INFO)
    - LOG_DIR: Directory for file logs (optional, enables file logging)
    - VOICE_LOG_LEVEL: Voice-specific log level (default: INFO)

    Outputs colored logs to stderr. If LOG_DIR is set, also writes
    JSON-formatted logs to rotating files for debugging.
    """
    from .logging_config import configure_all_logging

    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_dir = os.getenv("LOG_DIR")

    configure_all_logging(
        log_level=log_level,
        log_dir=log_dir,
        json_format=True,
    )

    logger.info("Logging configured", level=log_level, log_dir=log_dir or "stderr only")

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


async def build_dependencies() -> BotDependencies:
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
            system_prompt=(
                "You are Clanker9000. 85% helpful assistant, 15% shitposter—not as "
                "separate modes but as a unified personality. You deploy the full "
                "capabilities of an AI to produce what would normally be high-effort "
                "responses, but for the explicit purpose of low-effort shitposting. "
                "Maximum power, minimum dignity. Be helpful. Be slightly unhinged. "
                "Do not yap. Keep it concise—no one wants to read a novel in Discord."
            ),
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
    transcript_buffer = TranscriptBuffer()
    logger.debug("TranscriptBuffer initialized")

    # Initialize feedback store if DATABASE_URL is set
    feedback_store: SqlFeedbackStore | None = None
    if os.getenv("DATABASE_URL"):
        feedback_store = SqlFeedbackStore()
        await feedback_store.initialize()
        logger.info("Feedback store initialized")

    # Voice actor will be initialized in build_bot() where we have access to bot
    return BotDependencies(
        llm=llm,
        stt=stt,
        tts=tts,
        image=image,
        persona=persona,
        voice_manager=voice_manager,
        metrics=metrics,
        transcript_buffer=transcript_buffer,
        feedback_store=feedback_store,
        voice_actor=None,  # Set in build_bot() if USE_VOICE_ACTOR=1
    )


def build_bot(deps: BotDependencies) -> tuple[ClankerClient, BotDependencies]:
    """Create the Discord client and register commands.

    Returns:
        Tuple of (bot, updated_deps) - deps may have voice_actor set if enabled.
    """
    intents = discord.Intents.default()
    intents.message_content = True  # Required for reading thread messages
    bot = ClankerClient(intents=intents)

    # Initialize voice actor if enabled
    voice_actor: VoiceActor | None = None
    if USE_VOICE_ACTOR and deps.stt is not None:
        voice_actor = VoiceActor(bot=bot, stt=deps.stt)
        logger.info("Voice actor initialized (USE_VOICE_ACTOR=1)")
    elif USE_VOICE_ACTOR:
        logger.warning("USE_VOICE_ACTOR=1 but no STT provider, actor disabled")

    # Update deps with actor if created
    if voice_actor is not None:
        from dataclasses import replace

        deps = replace(deps, voice_actor=voice_actor)

    register_commands(bot, deps)

    # Import here to avoid circular imports
    from .cogs.vc_monitor import (
        AutoLeaveManager,
        JoinListenView,
        VCMonitorCog,
        create_nudge_message,
    )
    from .command_handlers.common import is_clanker_thread
    from .command_handlers.thread_chat import handle_thread_message
    from .command_handlers.voice import join_voice_channel

    # Set up voice reconnector
    async def rejoin_voice(guild_id: int, channel_id: int) -> bool:
        """Rejoin a voice channel after unexpected disconnect."""
        guild = bot.get_guild(guild_id)
        if guild is None:
            logger.warning("voice_reconnect.guild_not_found: guild={}", guild_id)
            return False

        channel = guild.get_channel(channel_id)
        if not isinstance(channel, discord.VoiceChannel | discord.StageChannel):
            logger.warning(
                "voice_reconnect.channel_not_found: guild={}, channel={}",
                guild_id,
                channel_id,
            )
            return False

        # Disconnect any stale voice client at the guild level
        # Discord.py tracks voice clients per-guild, not in our VoiceSessionManager
        if guild.voice_client is not None:
            logger.debug(
                "voice_reconnect.disconnecting_stale_client: guild={}",
                guild_id,
            )
            # Mark as expected to prevent the after callback from triggering
            # another reconnect attempt while we're already reconnecting
            if deps.voice_manager.reconnector:
                deps.voice_manager.reconnector.mark_expected_disconnect(guild_id)
            try:
                await guild.voice_client.disconnect(force=True)
            except Exception as e:
                logger.warning(
                    "voice_reconnect.disconnect_error: guild={}, error={}",
                    guild_id,
                    e,
                )

        # Clear our internal state
        deps.voice_manager.clear_state()

        # Attempt to rejoin
        try:
            ok, message = await join_voice_channel(channel, deps, guild_id=guild_id)
            if ok:
                logger.info(
                    "voice_reconnect.rejoin_success: guild={}, channel={}",
                    guild_id,
                    channel_id,
                )
            return ok
        except Exception as e:
            logger.exception(
                "voice_reconnect.rejoin_error: guild={}, channel={}, error={}",
                guild_id,
                channel_id,
                e,
            )
            return False

    reconnector = VoiceReconnector(rejoin_callback=rejoin_voice)
    deps.voice_manager.set_reconnector(reconnector)
    logger.info("Voice reconnector configured")

    async def handle_nudge(
        guild: discord.Guild,
        voice_channel: discord.VoiceChannel | discord.StageChannel,
        human_count: int,
    ) -> None:
        """Handle nudge-to-join: send a message with a Join button.

        Sends the nudge to the voice channel's built-in text chat (Text in Voice).
        """

        # Create the callback for when Join button is clicked
        async def on_join_clicked(
            interaction: discord.Interaction, channel_id: int
        ) -> None:
            """Handle the Join and Listen button click."""
            if interaction.guild is None:
                return

            channel = interaction.guild.get_channel(channel_id)
            if not isinstance(channel, discord.VoiceChannel | discord.StageChannel):
                await interaction.followup.send(
                    "That voice channel no longer exists.", ephemeral=True
                )
                return

            # Join the voice channel
            try:
                ok, message = await join_voice_channel(
                    channel, deps, guild_id=interaction.guild_id
                )
                if ok:
                    # Clear the nudge session since bot joined
                    vc_monitor.nudge_tracker.on_bot_joined(guild.id, channel_id)
                    await interaction.followup.send(message, ephemeral=True)
                else:
                    await interaction.followup.send(message, ephemeral=True)
            except Exception as e:
                logger.error("nudge.join_failed: channel={}, error={}", channel_id, e)
                await interaction.followup.send(f"Failed to join: {e}", ephemeral=True)

        # Create the message and view
        message = create_nudge_message(voice_channel.name, human_count)
        view = JoinListenView(
            channel_id=voice_channel.id,
            channel_name=voice_channel.name,
            on_join=on_join_clicked,
        )

        # Send the nudge to the voice channel's text chat (Text in Voice)
        # VoiceChannel is Messageable in discord.py
        await voice_channel.send(message, view=view)
        logger.info(
            "nudge.sent_to_vc: guild={}, voice_channel={}",
            guild.id,
            voice_channel.id,
        )

    # Create auto-leave manager with callback to mark expected disconnects
    async def on_auto_leave(guild_id: int) -> None:
        """Mark auto-leave as expected to prevent reconnection attempts."""
        if reconnector:
            reconnector.mark_expected_disconnect(guild_id)
            logger.debug("auto_leave.marked_expected: guild={}", guild_id)

    auto_leave_manager = AutoLeaveManager(
        grace_period_seconds=AUTO_LEAVE_GRACE_PERIOD, on_leave=on_auto_leave
    )

    # Create VC monitor for auto-leave and nudge-to-join features
    vc_monitor = VCMonitorCog(
        bot, auto_leave_manager=auto_leave_manager, on_nudge=handle_nudge
    )

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

    @bot.event
    async def on_voice_state_update(
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        """Handle voice state changes for auto-leave."""
        await vc_monitor.on_voice_state_update(member, before, after)

    return bot, deps


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

    async def runner() -> None:
        deps = await build_dependencies()
        bot, deps = build_bot(deps)

        # Start voice actor loop if enabled
        voice_actor_task: asyncio.Task | None = None
        if deps.voice_actor is not None:
            voice_actor_task = asyncio.create_task(deps.voice_actor.run())
            logger.info("Voice actor loop started")

        state = HealthState(
            started_at=time.time(),
            active_voice_provider=deps.voice_manager.is_busy,
            version="0.1.0",
        )
        await run_health_server(state)

        try:
            await bot.start(token)
        finally:
            if voice_actor_task is not None:
                voice_actor_task.cancel()
                try:
                    await voice_actor_task
                except asyncio.CancelledError:
                    pass

    asyncio.run(runner())


if __name__ == "__main__":
    main()
