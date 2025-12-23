"""Slash commands for Clanker."""

from __future__ import annotations

from collections.abc import Callable, Coroutine, Iterable
from dataclasses import dataclass

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

    commands = _build_command_specs(deps)
    for spec in commands:
        _register_command(tree, spec)

    bot.tree = tree


CommandCallback = Callable[..., Coroutine[object, object, None]]


@dataclass(frozen=True)
class CommandSpec:
    name: str
    description: str
    callback: CommandCallback
    describe: dict[str, str] | None = None


def _build_command_specs(deps: BotDependencies) -> Iterable[CommandSpec]:
    async def chat(interaction: discord.Interaction, prompt: str) -> None:
        await handle_chat(interaction, prompt, deps)

    async def speak(interaction: discord.Interaction, prompt: str) -> None:
        await handle_speak(interaction, prompt, deps)

    async def shitpost(
        interaction: discord.Interaction,
        topic: str,
        category: str | None = None,
    ) -> None:
        await handle_shitpost(interaction, topic, category, deps)

    async def join(interaction: discord.Interaction) -> None:
        await handle_join(interaction, deps)

    async def leave(interaction: discord.Interaction) -> None:
        await handle_leave(interaction, deps)

    async def admin_active_meetings(interaction: discord.Interaction) -> None:
        await handle_admin_active_meetings(interaction, deps)

    async def admin_stop_new_meetings(interaction: discord.Interaction) -> None:
        await handle_admin_stop_new_meetings(interaction, deps)

    async def admin_allow_new_meetings(interaction: discord.Interaction) -> None:
        await handle_admin_allow_new_meetings(interaction, deps)

    return [
        CommandSpec(
            name="chat",
            description="Chat with Clanker",
            callback=chat,
            describe={"prompt": "Prompt for Clanker"},
        ),
        CommandSpec(
            name="speak",
            description="Chat with TTS response",
            callback=speak,
            describe={"prompt": "Prompt for Clanker"},
        ),
        CommandSpec(
            name="shitpost",
            description="Generate a shitpost",
            callback=shitpost,
            describe={
                "topic": "Topic for the shitpost",
                "category": "Template category",
            },
        ),
        CommandSpec(
            name="join",
            description="Join your voice channel",
            callback=join,
        ),
        CommandSpec(
            name="leave",
            description="Leave the current voice channel",
            callback=leave,
        ),
        CommandSpec(
            name="admin_active_meetings",
            description="List active meetings",
            callback=admin_active_meetings,
        ),
        CommandSpec(
            name="admin_stop_new_meetings",
            description="Stop new meetings",
            callback=admin_stop_new_meetings,
        ),
        CommandSpec(
            name="admin_allow_new_meetings",
            description="Allow new meetings",
            callback=admin_allow_new_meetings,
        ),
    ]


def _register_command(tree: app_commands.CommandTree, spec: CommandSpec) -> None:
    callback = spec.callback
    if spec.describe:
        callback = app_commands.describe(**spec.describe)(callback)
    tree.add_command(
        app_commands.Command(
            name=spec.name,
            description=spec.description,
            callback=callback,
        )
    )
