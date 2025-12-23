"""Admin command handlers."""

from __future__ import annotations

import discord

from .messages import ResponseMessage
from .types import BotDependencies


async def handle_admin_active_meetings(
    interaction: discord.Interaction,
    deps: BotDependencies,
) -> None:
    if not _is_admin(interaction, deps):
        await interaction.response.send_message(ResponseMessage.NOT_AUTHORIZED)
        return
    active = deps.voice_manager.active_channel_id
    await interaction.response.send_message(
        f"Active voice channel: {active or ResponseMessage.ACTIVE_VOICE_NONE}"
    )


async def handle_admin_stop_new_meetings(
    interaction: discord.Interaction,
    deps: BotDependencies,
) -> None:
    if not _is_admin(interaction, deps):
        await interaction.response.send_message(ResponseMessage.NOT_AUTHORIZED)
        return
    if deps.admin_state:
        deps.admin_state.allow_new_meetings = False
    await interaction.response.send_message(ResponseMessage.NEW_MEETINGS_DISABLED)


async def handle_admin_allow_new_meetings(
    interaction: discord.Interaction,
    deps: BotDependencies,
) -> None:
    if not _is_admin(interaction, deps):
        await interaction.response.send_message(ResponseMessage.NOT_AUTHORIZED)
        return
    if deps.admin_state:
        deps.admin_state.allow_new_meetings = True
    await interaction.response.send_message(ResponseMessage.NEW_MEETINGS_ENABLED)


def _is_admin(interaction: discord.Interaction, deps: BotDependencies) -> bool:
    if not deps.admin_user_ids:
        return False
    if not interaction.user:
        return False
    return interaction.user.id in deps.admin_user_ids
