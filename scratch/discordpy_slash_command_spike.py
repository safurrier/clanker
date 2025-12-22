"""Minimal slash command spike for discord.py."""

import os

import discord
from discord import app_commands


async def main() -> None:
    intents = discord.Intents.default()
    bot = discord.Client(intents=intents)
    tree = app_commands.CommandTree(bot)

    @tree.command(name="chat")
    async def chat(interaction: discord.Interaction, prompt: str) -> None:
        await interaction.response.send_message(f"Echo: {prompt}")

    @bot.event
    async def on_ready() -> None:
        await tree.sync()

    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("Missing DISCORD_TOKEN")
    await bot.start(token)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
