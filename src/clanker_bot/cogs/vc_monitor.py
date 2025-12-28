"""VC monitoring cog for auto-leave and nudge-to-join features.

Features:
- Auto-leave: Disconnect bot when it's alone in VC (with grace period)
- Nudge-to-join: Prompt users when 2+ humans are in VC without the bot
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import discord
from discord import ui
from loguru import logger


def is_bot_alone_in_channel(
    channel: discord.VoiceChannel | discord.StageChannel, bot_id: int
) -> bool:
    """Check if the bot is the only non-bot member in a voice channel.

    Args:
        channel: Voice channel to check.
        bot_id: The bot's user ID.

    Returns:
        True if no humans are in the channel (only bots or empty except for our bot).
    """
    for member in channel.members:
        # Skip the bot itself
        if member.id == bot_id:
            continue
        # If there's a human (non-bot), we're not alone
        if not member.bot:
            return False
    return True


def get_active_voice_channels(
    guild: discord.Guild, min_humans: int = 2
) -> list[discord.VoiceChannel | discord.StageChannel]:
    """Get voice channels with at least min_humans human members.

    Args:
        guild: The guild to check.
        min_humans: Minimum number of human (non-bot) members required.

    Returns:
        List of voice channels meeting the criteria.
    """
    active_channels: list[discord.VoiceChannel | discord.StageChannel] = []
    for channel in guild.voice_channels:
        human_count = sum(1 for m in channel.members if not m.bot)
        if human_count >= min_humans:
            active_channels.append(channel)
    return active_channels


@dataclass
class AutoLeaveManager:
    """Manages auto-leave with grace period.

    When the bot becomes alone in a VC, schedules a disconnect after
    a grace period. If a human joins during the grace period, the
    scheduled disconnect is cancelled.
    """

    grace_period_seconds: float = 30.0
    _pending_leaves: dict[int, asyncio.Task[None]] = field(default_factory=dict)

    def schedule_leave(
        self, voice_client: discord.VoiceClient, channel_id: int
    ) -> asyncio.Task[None]:
        """Schedule a disconnect after the grace period.

        Args:
            voice_client: The voice client to disconnect.
            channel_id: ID of the channel (for tracking).

        Returns:
            The scheduled task (can be cancelled).
        """
        # Cancel any existing pending leave for this channel
        self.cancel_leave(channel_id)

        async def _delayed_leave() -> None:
            logger.debug(
                "auto_leave.scheduled: channel={}, grace_period={}",
                channel_id,
                self.grace_period_seconds,
            )
            await asyncio.sleep(self.grace_period_seconds)
            if voice_client.is_connected():
                logger.info("auto_leave.disconnecting: channel={}", channel_id)
                await voice_client.disconnect(force=False)
            self._pending_leaves.pop(channel_id, None)

        task = asyncio.create_task(_delayed_leave())
        self._pending_leaves[channel_id] = task
        return task

    def cancel_leave(self, channel_id: int) -> bool:
        """Cancel a pending leave for a channel.

        Args:
            channel_id: ID of the channel.

        Returns:
            True if a pending leave was cancelled, False otherwise.
        """
        task = self._pending_leaves.pop(channel_id, None)
        if task is not None:
            task.cancel()
            logger.debug("auto_leave.cancelled: channel={}", channel_id)
            return True
        return False

    def has_pending_leave(self, channel_id: int) -> bool:
        """Check if there's a pending leave for a channel."""
        return channel_id in self._pending_leaves


@dataclass
class NudgeTracker:
    """Tracks nudged channels using session-based logic.

    A "session" represents a period when a channel has 2+ humans.
    Once nudged, the channel won't be nudged again until:
    - The session ends (channel drops below threshold)
    - The bot joins the channel

    This prevents spam while ensuring nudges happen for new gatherings.
    """

    # Active sessions: set of (guild_id, channel_id) that have been nudged
    _active_sessions: set[tuple[int, int]] = field(default_factory=set)

    def should_nudge(self, guild_id: int, channel_id: int) -> bool:
        """Check if a channel should be nudged.

        Args:
            guild_id: The guild ID.
            channel_id: The channel ID.

        Returns:
            True if this channel hasn't been nudged in the current session.
        """
        key = (guild_id, channel_id)
        return key not in self._active_sessions

    def mark_nudged(self, guild_id: int, channel_id: int) -> None:
        """Mark a channel as having been nudged in this session.

        Args:
            guild_id: The guild ID.
            channel_id: The channel ID.
        """
        key = (guild_id, channel_id)
        self._active_sessions.add(key)
        logger.debug("nudge.marked: guild={}, channel={}", guild_id, channel_id)

    def end_session(self, guild_id: int, channel_id: int) -> None:
        """End the session for a channel (dropped below threshold).

        Call this when a channel no longer meets the nudge criteria
        (e.g., drops to 1 or 0 humans). This allows a new nudge
        when the channel becomes active again.

        Args:
            guild_id: The guild ID.
            channel_id: The channel ID.
        """
        key = (guild_id, channel_id)
        self._active_sessions.discard(key)
        logger.debug("nudge.session_ended: guild={}, channel={}", guild_id, channel_id)

    def on_bot_joined(self, guild_id: int, channel_id: int) -> None:
        """Handle bot joining a channel.

        Clears the session since the nudge was successful.
        A new nudge can happen after bot leaves and a new session starts.

        Args:
            guild_id: The guild ID.
            channel_id: The channel ID.
        """
        key = (guild_id, channel_id)
        self._active_sessions.discard(key)
        logger.debug("nudge.bot_joined: guild={}, channel={}", guild_id, channel_id)


class VCMonitorCog:
    """Discord cog for voice channel monitoring.

    Features:
    - Auto-leave when bot is alone in VC
    - Nudge-to-join when 2+ humans are in VC

    This cog is designed to be instantiated per-guild for isolation.
    """

    def __init__(
        self,
        bot: discord.Client,
        auto_leave_manager: AutoLeaveManager | None = None,
        nudge_tracker: NudgeTracker | None = None,
        on_nudge: Callable[
            [discord.Guild, discord.VoiceChannel | discord.StageChannel, int],
            Awaitable[None],
        ]
        | None = None,
        min_humans_for_nudge: int = 2,
    ) -> None:
        """Initialize the VC monitor cog.

        Args:
            bot: The Discord bot instance.
            auto_leave_manager: Manager for auto-leave with grace period.
            nudge_tracker: Tracker for nudge cooldowns.
            on_nudge: Async callback invoked when nudge conditions are met.
                      Receives (guild, channel, human_count).
            min_humans_for_nudge: Minimum humans required to trigger nudge.
        """
        self.bot = bot
        self.auto_leave = auto_leave_manager or AutoLeaveManager()
        self.nudge_tracker = nudge_tracker or NudgeTracker()
        self._on_nudge = on_nudge
        self.min_humans_for_nudge = min_humans_for_nudge

    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        """Handle voice state updates for auto-leave and nudge-to-join.

        Called when a member's voice state changes (join, leave, move).
        - Auto-leave: Checks if the bot should leave when left alone
        - Nudge-to-join: Checks if we should nudge when 2+ humans gather
        """
        guild = member.guild
        before_channel = before.channel
        after_channel = after.channel

        # --- Handle nudge-to-join (when bot is NOT in VC) ---
        await self._handle_nudge_logic(guild, member, before_channel, after_channel)

        # --- Handle auto-leave (when bot IS in VC) ---
        await self._handle_auto_leave_logic(
            guild, member, before_channel, after_channel
        )

    async def _handle_nudge_logic(
        self,
        guild: discord.Guild,
        member: discord.Member,
        before_channel: discord.VoiceChannel | discord.StageChannel | None,
        after_channel: discord.VoiceChannel | discord.StageChannel | None,
    ) -> None:
        """Handle nudge-to-join logic when bot is not in VC."""
        # Skip if no nudge callback configured
        if self._on_nudge is None:
            return

        # Skip bot events
        if member.bot:
            return

        # Check if bot is in any VC in this guild
        # Note: We use duck typing here to support both real discord.VoiceClient
        # and fake test doubles
        voice_client = guild.voice_client
        bot_channel_id: int | None = None
        if voice_client is not None:
            is_connected = getattr(voice_client, "is_connected", None)
            if callable(is_connected) and is_connected():
                vc_channel = getattr(voice_client, "channel", None)
                if vc_channel is not None and hasattr(vc_channel, "id"):
                    bot_channel_id = vc_channel.id

        # --- Handle channel leave: end session if below threshold ---
        if before_channel is not None:
            human_count = sum(1 for m in before_channel.members if not m.bot)
            if human_count < self.min_humans_for_nudge:
                self.nudge_tracker.end_session(guild.id, before_channel.id)
                logger.debug(
                    "nudge.session_check_leave: guild={}, channel={}, humans={}",
                    guild.id,
                    before_channel.id,
                    human_count,
                )

        # --- Handle channel join: check if we should nudge ---
        if after_channel is not None:
            # Don't nudge if bot is already in THIS channel
            if bot_channel_id is not None and bot_channel_id == after_channel.id:
                return

            human_count = sum(1 for m in after_channel.members if not m.bot)

            if human_count >= self.min_humans_for_nudge:
                # Check if we should nudge (not already nudged this session)
                if self.nudge_tracker.should_nudge(guild.id, after_channel.id):
                    logger.info(
                        "nudge.triggering: guild={}, channel={}, humans={}",
                        guild.id,
                        after_channel.id,
                        human_count,
                    )
                    self.nudge_tracker.mark_nudged(guild.id, after_channel.id)
                    await self._on_nudge(guild, after_channel, human_count)

    async def _handle_auto_leave_logic(
        self,
        guild: discord.Guild,
        member: discord.Member,
        before_channel: discord.VoiceChannel | discord.StageChannel | None,
        after_channel: discord.VoiceChannel | discord.StageChannel | None,
    ) -> None:
        """Handle auto-leave logic when bot is in VC."""
        # Get the bot's voice client for this guild
        voice_client = guild.voice_client
        if not isinstance(voice_client, discord.VoiceClient):
            return
        if not voice_client.is_connected():
            return

        # Get the channel the bot is in
        bot_channel = voice_client.channel
        if not isinstance(bot_channel, discord.VoiceChannel | discord.StageChannel):
            return

        # Someone left the bot's channel
        if before_channel is not None and before_channel.id == bot_channel.id:
            bot_user = self.bot.user
            if bot_user is not None and is_bot_alone_in_channel(
                bot_channel, bot_user.id
            ):
                # Bot is now alone, schedule leave
                self.auto_leave.schedule_leave(voice_client, bot_channel.id)
                logger.info(
                    "auto_leave.triggered: guild={}, channel={}",
                    guild.id,
                    bot_channel.id,
                )

        # Someone joined the bot's channel - cancel pending leave
        if after_channel is not None and after_channel.id == bot_channel.id:
            if not member.bot:
                # Human joined, cancel any pending leave
                if self.auto_leave.cancel_leave(bot_channel.id):
                    logger.info(
                        "auto_leave.cancelled_by_join: guild={}, channel={}",
                        guild.id,
                        bot_channel.id,
                    )


def find_nudge_text_channel(
    guild: discord.Guild,
    voice_channel: discord.VoiceChannel | discord.StageChannel,
) -> discord.TextChannel | None:
    """Find the best text channel to send a nudge message.

    Priority:
    1. A text channel with the same name as the voice channel
    2. A text channel named "general", "chat", or "bot-commands"
    3. The guild's system channel
    4. The first text channel the bot can send messages in

    Args:
        guild: The guild to search.
        voice_channel: The voice channel users are gathering in.

    Returns:
        A text channel to send the nudge, or None if no suitable channel found.
    """
    # 1. Look for a text channel with the same name
    for channel in guild.text_channels:
        if channel.name.lower() == voice_channel.name.lower():
            if channel.permissions_for(guild.me).send_messages:
                return channel

    # 2. Look for common general channels
    common_names = ["general", "chat", "bot-commands", "bots", "bot"]
    for name in common_names:
        for channel in guild.text_channels:
            if channel.name.lower() == name:
                if channel.permissions_for(guild.me).send_messages:
                    return channel

    # 3. Try the system channel
    if guild.system_channel:
        if guild.system_channel.permissions_for(guild.me).send_messages:
            return guild.system_channel

    # 4. First text channel we can send to
    for channel in guild.text_channels:
        if channel.permissions_for(guild.me).send_messages:
            return channel

    return None


def create_nudge_message(channel_name: str, member_count: int) -> str:
    """Create a nudge message for a voice channel.

    Args:
        channel_name: Name of the voice channel.
        member_count: Number of humans in the channel.

    Returns:
        A friendly message encouraging the bot to join.
    """
    return (
        f"👋 **{member_count} people** are chatting in **{channel_name}**!\n"
        "Want me to join and listen? I can transcribe your conversation "
        "and help generate memes with `/shitpost`."
    )


class JoinListenView(ui.View):
    """Discord UI View with a 'Join and Listen' button.

    Displays a button that, when clicked, triggers the bot to join
    the specified voice channel and start listening.

    Auto-dismisses after 5 minutes (300 seconds).
    """

    def __init__(
        self,
        channel_id: int,
        channel_name: str,
        on_join: Callable[[discord.Interaction, int], Awaitable[None]],
    ) -> None:
        """Initialize the view.

        Args:
            channel_id: ID of the voice channel to join.
            channel_name: Name of the voice channel (for display).
            on_join: Async callback invoked when join button is clicked.
                     Receives (interaction, channel_id).
        """
        super().__init__(timeout=300.0)  # 5 minutes
        self.channel_id = channel_id
        self.channel_name = channel_name
        self._on_join = on_join

    @ui.button(label="🎤 Join and Listen", style=discord.ButtonStyle.primary)
    async def join_button(
        self, interaction: discord.Interaction, button: ui.Button[JoinListenView]
    ) -> None:
        """Handle the join button click."""
        logger.info(
            "nudge.join_clicked: channel={}, user={}",
            self.channel_id,
            interaction.user.id if interaction.user else None,
        )

        # Defer to allow time for join operation
        await interaction.response.defer()

        # Invoke the callback
        await self._on_join(interaction, self.channel_id)

        # Delete the nudge message after joining
        if interaction.message:
            try:
                await interaction.message.delete()
            except discord.HTTPException:
                pass  # Message may already be deleted

    async def on_timeout(self) -> None:
        """Handle view timeout (auto-dismiss)."""
        logger.debug("nudge.view_timeout: channel={}", self.channel_id)
        # View is automatically disabled after timeout
