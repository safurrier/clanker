"""dpytest coverage for command wiring."""

from __future__ import annotations

import discord
import discord.ext.test as dpytest
import pytest
from discord.ext import commands

from clanker.models import Context, Message, Persona
from clanker.respond import respond
from tests.fakes import FakeLLM


@pytest.mark.asyncio()
async def test_dpytest_chat_command() -> None:
    intents = discord.Intents.default()
    intents.members = True
    bot = commands.Bot(command_prefix="!", intents=intents)
    await bot._async_setup_hook()

    @bot.command(name="chat")
    async def chat(ctx: commands.Context, *, prompt: str) -> None:
        persona = Persona(
            id="test",
            display_name="Test",
            system_prompt="You are helpful.",
        )
        context = Context(
            request_id="req",
            user_id=ctx.author.id,
            guild_id=ctx.guild.id if ctx.guild else None,
            channel_id=ctx.channel.id,
            persona=persona,
            messages=[Message(role="user", content=prompt)],
            metadata={"source": "dpytest"},
        )
        reply, _audio = await respond(context, FakeLLM(reply_text="pong"))
        await ctx.send(reply.content)

    dpytest.configure(bot)
    config = dpytest.get_config()
    member = config.members[0]
    channel = next(
        chan for chan in config.channels if isinstance(chan, discord.TextChannel)
    )

    await dpytest.message("!chat hello", member=member, channel=channel)
    assert dpytest.verify().message().content("pong")
