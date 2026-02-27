#!/usr/bin/env python3
"""Sync Discord slash commands to a guild (instant) or globally.

Usage:
    # Sync to test guild (instant, for development)
    python scripts/sync_commands.py --guild

    # Sync globally (takes up to 1 hour to propagate)
    python scripts/sync_commands.py --global

    # Both
    python scripts/sync_commands.py --guild --global

Requires:
    DISCORD_TOKEN - Bot token
    DISCORD_GUILD_ID - Test guild ID (for --guild)
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

import discord

from clanker.models import Persona
from clanker_bot.admin import AdminState
from clanker_bot.commands import BotDependencies, ClankerClient, register_commands
from clanker_bot.discord_adapter import VoiceSessionManager
from clanker_bot.metrics import Metrics
from clanker_bot.voice_ingest import TranscriptBuffer
from tests.fakes import FakeLLM, FakeSTT, FakeTTS


def get_token() -> str:
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        print("Error: DISCORD_TOKEN not set", file=sys.stderr)
        sys.exit(1)
    return token


def get_guild_id() -> int:
    guild_id = os.environ.get("DISCORD_GUILD_ID")
    if not guild_id:
        print("Error: DISCORD_GUILD_ID not set", file=sys.stderr)
        sys.exit(1)
    return int(guild_id)


def build_fake_deps() -> BotDependencies:
    """Build fake dependencies for command registration."""
    return BotDependencies(
        llm=FakeLLM(),
        stt=FakeSTT(),
        tts=FakeTTS(),
        image=None,
        persona=Persona(
            id="sync",
            display_name="Sync",
            system_prompt="",
            tts_voice=None,
            providers=None,
        ),
        voice_manager=VoiceSessionManager(),
        metrics=Metrics(),
        admin_user_ids=set(),
        admin_state=AdminState(),
        transcript_buffer=TranscriptBuffer(),
    )


def build_sync_client() -> ClankerClient:
    """Create a ClankerClient with real command registration."""
    deps = build_fake_deps()
    client = ClankerClient(intents=discord.Intents.none())
    register_commands(client, deps)
    return client


async def sync_commands(
    client: ClankerClient,
    *,
    sync_guild: bool,
    sync_global: bool,
    clear_guild: bool,
    guild_id: int | None,
) -> None:
    """Sync commands using the client's command tree."""
    # Handle clearing first
    if clear_guild and guild_id:
        guild = discord.Object(id=guild_id)
        client.tree.clear_commands(guild=guild)
        await client.tree.sync(guild=guild)
        print(f"Cleared all commands from guild {guild_id}")
        return

    if sync_guild and guild_id:
        guild = discord.Object(id=guild_id)
        # Copy global commands to the guild for instant sync
        client.tree.copy_global_to(guild=guild)
        cmds = await client.tree.sync(guild=guild)
        print(f"Synced {len(cmds)} commands to guild {guild_id}:")
        for cmd in cmds:
            print(f"  - /{cmd.name}")

    if sync_global:
        cmds = await client.tree.sync()
        print(f"Synced {len(cmds)} global commands (may take up to 1 hour):")
        for cmd in cmds:
            print(f"  - /{cmd.name}")


async def main(sync_guild: bool, sync_global: bool, clear_guild: bool) -> None:
    token = get_token()
    guild_id = get_guild_id() if (sync_guild or clear_guild) else None

    # Build client with real command registration
    client = build_sync_client()

    # Connect and sync
    await client.login(token)
    await sync_commands(
        client,
        sync_guild=sync_guild,
        sync_global=sync_global,
        clear_guild=clear_guild,
        guild_id=guild_id,
    )
    await client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync Discord slash commands")
    parser.add_argument(
        "--guild",
        action="store_true",
        help="Sync to test guild (instant, requires DISCORD_GUILD_ID)",
    )
    parser.add_argument(
        "--global",
        dest="global_",
        action="store_true",
        help="Sync globally (takes up to 1 hour to propagate)",
    )
    parser.add_argument(
        "--clear-guild",
        action="store_true",
        help="Clear all commands from the guild (removes duplicates)",
    )
    args = parser.parse_args()

    if not args.guild and not args.global_ and not args.clear_guild:
        parser.error("Specify --guild, --global, and/or --clear-guild")

    asyncio.run(
        main(
            sync_guild=args.guild,
            sync_global=args.global_,
            clear_guild=args.clear_guild,
        )
    )
