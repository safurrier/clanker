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
from discord import app_commands


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


def register_commands_minimal(tree: app_commands.CommandTree) -> None:
    """Register command definitions only (no handlers needed for sync)."""

    # Chat commands - need exact signatures for parameter extraction
    @app_commands.describe(prompt="Prompt for Clanker")
    async def chat(interaction: discord.Interaction, prompt: str) -> None:
        pass

    @app_commands.describe(prompt="Prompt for Clanker")
    async def speak(interaction: discord.Interaction, prompt: str) -> None:
        pass

    @app_commands.describe(
        n="Number of meme previews to generate (default 1, max 5)",
        guidance="Optional guidance for meme generation",
    )
    async def shitpost(
        interaction: discord.Interaction,
        n: int = 1,
        guidance: str | None = None,
    ) -> None:
        pass

    # Voice commands - no parameters
    async def join(interaction: discord.Interaction) -> None:
        pass

    async def leave(interaction: discord.Interaction) -> None:
        pass

    async def transcript(interaction: discord.Interaction) -> None:
        pass

    # Admin commands - no parameters
    async def admin_active_meetings(interaction: discord.Interaction) -> None:
        pass

    async def admin_stop_new_meetings(interaction: discord.Interaction) -> None:
        pass

    async def admin_allow_new_meetings(interaction: discord.Interaction) -> None:
        pass

    # Register all commands
    tree.add_command(
        app_commands.Command(name="chat", description="Chat with Clanker", callback=chat)
    )
    tree.add_command(
        app_commands.Command(
            name="speak", description="Chat with TTS response", callback=speak
        )
    )
    tree.add_command(
        app_commands.Command(
            name="shitpost",
            description="Generate meme previews with Post/Regenerate/Dismiss buttons",
            callback=shitpost,
        )
    )
    tree.add_command(
        app_commands.Command(
            name="join", description="Join your voice channel", callback=join
        )
    )
    tree.add_command(
        app_commands.Command(
            name="leave", description="Leave the current voice channel", callback=leave
        )
    )
    tree.add_command(
        app_commands.Command(
            name="transcript",
            description="Show recent voice transcripts (ephemeral)",
            callback=transcript,
        )
    )
    tree.add_command(
        app_commands.Command(
            name="admin_active_meetings",
            description="List active meetings",
            callback=admin_active_meetings,
        )
    )
    tree.add_command(
        app_commands.Command(
            name="admin_stop_new_meetings",
            description="Stop new meetings",
            callback=admin_stop_new_meetings,
        )
    )
    tree.add_command(
        app_commands.Command(
            name="admin_allow_new_meetings",
            description="Allow new meetings",
            callback=admin_allow_new_meetings,
        )
    )


class SyncClient(discord.Client):
    def __init__(
        self,
        *,
        sync_guild: bool,
        sync_global: bool,
        clear_guild: bool,
        guild_id: int | None,
    ):
        super().__init__(intents=discord.Intents.none())
        self.tree = app_commands.CommandTree(self)
        self.sync_guild = sync_guild
        self.sync_global = sync_global
        self.clear_guild = clear_guild
        self.guild_id = guild_id

    async def setup_hook(self) -> None:
        # Handle clearing first
        if self.clear_guild and self.guild_id:
            guild = discord.Object(id=self.guild_id)
            self.tree.clear_commands(guild=guild)
            await self.tree.sync(guild=guild)
            print(f"Cleared all commands from guild {self.guild_id}")
            await self.close()
            return

        register_commands_minimal(self.tree)

        if self.sync_guild and self.guild_id:
            guild = discord.Object(id=self.guild_id)
            # Copy global commands to the guild for instant sync
            self.tree.copy_global_to(guild=guild)
            cmds = await self.tree.sync(guild=guild)
            print(f"Synced {len(cmds)} commands to guild {self.guild_id}:")
            for cmd in cmds:
                print(f"  - /{cmd.name}")

        if self.sync_global:
            cmds = await self.tree.sync()
            print(f"Synced {len(cmds)} global commands (may take up to 1 hour):")
            for cmd in cmds:
                print(f"  - /{cmd.name}")

        await self.close()


async def main(sync_guild: bool, sync_global: bool, clear_guild: bool) -> None:
    token = get_token()
    guild_id = get_guild_id() if (sync_guild or clear_guild) else None

    client = SyncClient(
        sync_guild=sync_guild,
        sync_global=sync_global,
        clear_guild=clear_guild,
        guild_id=guild_id,
    )
    await client.login(token)
    await client.connect()


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
