"""Spike showing dpytest setup for discord bots."""

import discord
import discord.ext.test as dpytest
import pytest
from discord.ext import commands


@pytest.mark.asyncio()
async def test_basic_message() -> None:
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())

    @bot.command()
    async def ping(ctx: commands.Context) -> None:
        await ctx.send("pong")

    dpytest.configure(bot)
    await dpytest.message("!ping")
    assert dpytest.verify().message().content("pong")
