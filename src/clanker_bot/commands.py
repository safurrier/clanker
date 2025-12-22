"""Slash commands for Clanker."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Protocol, cast

import discord
from discord import app_commands

from clanker.models import Context, Message, Persona
from clanker.providers.image import ImageGen
from clanker.providers.llm import LLM
from clanker.providers.policy import Policy
from clanker.providers.stt import STT
from clanker.providers.tts import TTS
from clanker.respond import respond
from clanker.shitposts import (
    build_request,
    load_templates,
    render_shitpost,
    sample_template,
)

from .admin import AdminState
from .discord_adapter import VoiceSessionManager
from .metrics import Metrics
from .voice_ingest import start_voice_ingest, voice_client_cls


class ClankerClient(discord.Client):
    """Discord client with an attached command tree."""

    tree: app_commands.CommandTree


@dataclass(frozen=True)
class BotDependencies:
    """Dependencies for the bot commands."""

    llm: LLM
    stt: STT | None
    tts: TTS | None
    persona: Persona
    voice_manager: VoiceSessionManager
    image: ImageGen | None = None
    policy: Policy | None = None
    replay_log_path: Path | None = None
    metrics: Metrics | None = None
    admin_user_ids: set[int] | None = None
    admin_state: AdminState | None = None
    voice_ingest_enabled: bool = False


def build_context(
    interaction: discord.Interaction,
    persona: Persona,
    message: Message,
) -> Context:
    """Build a Context from a Discord interaction and prompt."""
    return Context(
        request_id=str(uuid.uuid4()),
        user_id=interaction.user.id,
        guild_id=interaction.guild_id,
        channel_id=interaction.channel_id or 0,
        persona=persona,
        messages=[message],
        metadata={"source": "discord"},
    )


def register_commands(bot: ClankerClient, deps: BotDependencies) -> None:
    """Register app commands on the Discord bot."""
    tree = app_commands.CommandTree(bot)

    @tree.command(name="chat", description="Chat with Clanker")
    @app_commands.describe(prompt="Prompt for Clanker")
    async def chat(interaction: discord.Interaction, prompt: str) -> None:
        await handle_chat(interaction, prompt, deps)

    @tree.command(name="speak", description="Chat with TTS response")
    @app_commands.describe(prompt="Prompt for Clanker")
    async def speak(interaction: discord.Interaction, prompt: str) -> None:
        await handle_speak(interaction, prompt, deps)

    @tree.command(name="shitpost", description="Generate a shitpost")
    @app_commands.describe(topic="Topic for the shitpost", category="Template category")
    async def shitpost(
        interaction: discord.Interaction,
        topic: str,
        category: str | None = None,
    ) -> None:
        await handle_shitpost(interaction, topic, category, deps)

    @tree.command(name="join", description="Join your voice channel")
    async def join(interaction: discord.Interaction) -> None:
        await handle_join(interaction, deps)

    @tree.command(name="leave", description="Leave the current voice channel")
    async def leave(interaction: discord.Interaction) -> None:
        await handle_leave(interaction, deps)

    @tree.command(name="admin_active_meetings", description="List active meetings")
    async def admin_active_meetings(interaction: discord.Interaction) -> None:
        await handle_admin_active_meetings(interaction, deps)

    @tree.command(name="admin_stop_new_meetings", description="Stop new meetings")
    async def admin_stop_new_meetings(interaction: discord.Interaction) -> None:
        await handle_admin_stop_new_meetings(interaction, deps)

    @tree.command(name="admin_allow_new_meetings", description="Allow new meetings")
    async def admin_allow_new_meetings(interaction: discord.Interaction) -> None:
        await handle_admin_allow_new_meetings(interaction, deps)

    bot.tree = tree


async def handle_chat(
    interaction: discord.Interaction,
    prompt: str,
    deps: BotDependencies,
) -> None:
    message = Message(role="user", content=prompt)
    context = build_context(interaction, deps.persona, message)
    _increment_metric(deps, "chat_requests")
    reply, _audio = await respond(
        context,
        deps.llm,
        policy=deps.policy,
        tts=None,
        replay_log_path=deps.replay_log_path,
    )
    thread = await _ensure_thread(interaction)
    if thread:
        await thread.send(reply.content)
        await interaction.response.send_message("Reply posted in thread.")
        return
    await interaction.response.send_message(reply.content)


async def handle_speak(
    interaction: discord.Interaction,
    prompt: str,
    deps: BotDependencies,
) -> None:
    message = Message(role="user", content=prompt)
    context = build_context(interaction, deps.persona, message)
    _increment_metric(deps, "speak_requests")
    reply, audio = await respond(
        context,
        deps.llm,
        policy=deps.policy,
        tts=deps.tts,
        replay_log_path=deps.replay_log_path,
    )
    thread = await _ensure_thread(interaction)
    if audio:
        file = discord.File(fp=BytesIO(audio), filename="speech.mp3")
        if thread:
            await thread.send(reply.content, file=file)
            await interaction.response.send_message("Reply posted in thread.")
            return
        await interaction.response.send_message(reply.content, file=file)
        return
    if thread:
        await thread.send(reply.content)
        await interaction.response.send_message("Reply posted in thread.")
        return
    await interaction.response.send_message(reply.content)


async def handle_shitpost(
    interaction: discord.Interaction,
    topic: str,
    category: str | None,
    deps: BotDependencies,
) -> None:
    templates = load_templates()
    template = sample_template(templates, category=category)
    request = build_request(template, topic)
    _increment_metric(deps, "shitpost_requests")
    reply = await render_shitpost(
        build_context(interaction, deps.persona, Message(role="user", content="")),
        deps.llm,
        request,
    )
    if deps.image and template.category == "meme":
        image_payload = await deps.image.generate(
            {"template": template.name, "text": reply.content}
        )
        if isinstance(image_payload, str):
            image_bytes = image_payload.encode()
        else:
            image_bytes = image_payload
        file = discord.File(fp=BytesIO(image_bytes), filename="meme.png")
        await interaction.response.send_message(reply.content, file=file)
        return
    await interaction.response.send_message(reply.content)


async def handle_join(
    interaction: discord.Interaction,
    deps: BotDependencies,
) -> None:
    logger = logging.getLogger(__name__)
    if deps.admin_state and not deps.admin_state.allow_new_meetings:
        await interaction.response.send_message("New meetings are disabled.")
        return
    if not interaction.user or not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message("Unable to resolve voice channel.")
        return
    voice_state = interaction.user.voice
    if not voice_state or not voice_state.channel:
        await interaction.response.send_message("Join a voice channel first.")
        return
    ingest_voice_client_cls = None
    if deps.voice_ingest_enabled:
        ingest_voice_client_cls = voice_client_cls()
    ok, status = await deps.voice_manager.join(
        voice_state.channel, voice_client_cls=ingest_voice_client_cls
    )
    if ok:
        response = "Joined voice channel."
        if deps.voice_ingest_enabled:
            if deps.stt is None:
                response += " (Transcription unavailable; STT not configured.)"
            elif ingest_voice_client_cls is None:
                response += " (Transcription unavailable in this host build.)"
            else:
                try:
                    voice_client = deps.voice_manager.voice_client
                    if voice_client is None:
                        raise RuntimeError("Voice client not available.")
                    await start_voice_ingest(voice_client, deps.stt)
                    response += " (Transcription enabled.)"
                except Exception:
                    logger.exception("Failed to start voice ingest.")
                    response += " (Transcription unavailable due to setup error.)"
        await interaction.response.send_message(response)
        return
    await interaction.response.send_message(status)


async def handle_leave(
    interaction: discord.Interaction,
    deps: BotDependencies,
) -> None:
    ok, status = await deps.voice_manager.leave()
    if ok:
        await interaction.response.send_message("Left voice channel.")
        return
    await interaction.response.send_message(status)


async def handle_admin_active_meetings(
    interaction: discord.Interaction,
    deps: BotDependencies,
) -> None:
    if not _is_admin(interaction, deps):
        await interaction.response.send_message("Not authorized.")
        return
    active = deps.voice_manager.active_channel_id
    await interaction.response.send_message(f"Active voice channel: {active or 'none'}")


async def handle_admin_stop_new_meetings(
    interaction: discord.Interaction,
    deps: BotDependencies,
) -> None:
    if not _is_admin(interaction, deps):
        await interaction.response.send_message("Not authorized.")
        return
    if deps.admin_state:
        deps.admin_state.allow_new_meetings = False
    await interaction.response.send_message("New meetings disabled.")


async def handle_admin_allow_new_meetings(
    interaction: discord.Interaction,
    deps: BotDependencies,
) -> None:
    if not _is_admin(interaction, deps):
        await interaction.response.send_message("Not authorized.")
        return
    if deps.admin_state:
        deps.admin_state.allow_new_meetings = True
    await interaction.response.send_message("New meetings enabled.")


def _is_admin(interaction: discord.Interaction, deps: BotDependencies) -> bool:
    if not deps.admin_user_ids:
        return False
    if not interaction.user:
        return False
    return interaction.user.id in deps.admin_user_ids


def _increment_metric(deps: BotDependencies, key: str) -> None:
    if deps.metrics:
        deps.metrics.increment(key)


class ThreadCreator(Protocol):
    async def create_thread(self, name: str, **kwargs: object) -> discord.Thread: ...


async def _ensure_thread(
    interaction: discord.Interaction,
) -> discord.Thread | None:
    channel = interaction.channel
    if channel and hasattr(channel, "create_thread"):
        creator = cast(ThreadCreator, channel)
        return await creator.create_thread(
            name=f"clanker-{uuid.uuid4().hex[:6]}",
            type=discord.ChannelType.public_thread,
        )
    return None
