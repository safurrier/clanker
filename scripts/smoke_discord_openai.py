"""Manual smoke test for Discord + OpenAI integration."""

import asyncio
import os

import discord

from clanker.providers.factory import ProviderConfig, ProviderFactory


async def main() -> None:
    token = os.getenv("DISCORD_TOKEN")
    api_key = os.getenv("OPENAI_API_KEY")
    if not token:
        raise RuntimeError("DISCORD_TOKEN not set")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")

    intents = discord.Intents.default()
    bot = discord.Client(intents=intents)
    factory = ProviderFactory()
    config = ProviderConfig(llm="openai", stt="openai", tts="elevenlabs")
    factory.get_llm(config.llm)
    factory.get_stt(config.stt)

    @bot.event
    async def on_ready() -> None:
        print("Bot ready. Run /chat in your test guild to validate.")

    await bot.start(token)


if __name__ == "__main__":
    asyncio.run(main())
