"""Slash commands for Clanker."""

from __future__ import annotations

import discord
from discord import app_commands

from .command_handlers import (
    BotDependencies,
    ResponseMessage,
    handle_admin_active_meetings,
    handle_admin_allow_new_meetings,
    handle_admin_stop_new_meetings,
    handle_chat,
    handle_join,
    handle_leave,
    handle_shitpost,
    handle_speak,
)

__all__ = ["BotDependencies", "ClankerClient", "ResponseMessage", "register_commands"]


class ClankerClient(discord.Client):
    """Discord client with an attached command tree."""

    tree: app_commands.CommandTree


def register_commands(bot: ClankerClient, deps: BotDependencies) -> None:
    """Register app commands on the Discord bot."""
    tree = app_commands.CommandTree(bot)

    # Chat commands
    @app_commands.describe(prompt="Prompt for Clanker")
    async def chat(interaction: discord.Interaction, prompt: str) -> None:
        await handle_chat(interaction, prompt, deps)

    tree.add_command(
        app_commands.Command(
            name="chat",
            description="Chat with Clanker",
            callback=chat,
        )
    )

    @app_commands.describe(prompt="Prompt for Clanker")
    async def speak(interaction: discord.Interaction, prompt: str) -> None:
        await handle_speak(interaction, prompt, deps)

    tree.add_command(
        app_commands.Command(
            name="speak",
            description="Chat with TTS response",
            callback=speak,
        )
    )

    @app_commands.describe(topic="Topic for the shitpost", category="Template category")
    async def shitpost(
        interaction: discord.Interaction,
        topic: str,
        category: str | None = None,
    ) -> None:
        await handle_shitpost(interaction, topic, category, deps)

    tree.add_command(
        app_commands.Command(
            name="shitpost",
            description="Generate a shitpost",
            callback=shitpost,
        )
    )

    # Voice commands
    async def join(interaction: discord.Interaction) -> None:
        await handle_join(interaction, deps)

    tree.add_command(
        app_commands.Command(
            name="join",
            description="Join your voice channel",
            callback=join,
        )
    )

    async def leave(interaction: discord.Interaction) -> None:
        await handle_leave(interaction, deps)

    tree.add_command(
        app_commands.Command(
            name="leave",
            description="Leave the current voice channel",
            callback=leave,
        )
    )

    # Admin commands
    async def admin_active_meetings(interaction: discord.Interaction) -> None:
        await handle_admin_active_meetings(interaction, deps)

    tree.add_command(
        app_commands.Command(
            name="admin_active_meetings",
            description="List active meetings",
            callback=admin_active_meetings,
        )
    )

    async def admin_stop_new_meetings(interaction: discord.Interaction) -> None:
        await handle_admin_stop_new_meetings(interaction, deps)

    tree.add_command(
        app_commands.Command(
            name="admin_stop_new_meetings",
            description="Stop new meetings",
            callback=admin_stop_new_meetings,
        )
    )

    async def admin_allow_new_meetings(interaction: discord.Interaction) -> None:
        await handle_admin_allow_new_meetings(interaction, deps)

    tree.add_command(
        app_commands.Command(
            name="admin_allow_new_meetings",
            description="Allow new meetings",
            callback=admin_allow_new_meetings,
        )
    )

    bot.tree = tree
