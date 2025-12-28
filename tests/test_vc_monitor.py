"""Tests for VC monitoring cog (auto-leave and nudge-to-join)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# --- Fake Discord objects for testing ---


@dataclass
class FakeMember:
    """Fake Discord member."""

    id: int
    name: str = "TestUser"
    bot: bool = False

    @property
    def display_name(self) -> str:
        return self.name


@dataclass
class FakeVoiceState:
    """Fake voice state."""

    channel: FakeVoiceChannel | None = None


@dataclass
class FakeVoiceChannel:
    """Fake Discord voice channel."""

    id: int
    name: str = "General Voice"
    members: list[FakeMember] = field(default_factory=list)
    guild: FakeGuild | None = None

    @property
    def type(self) -> Any:
        """Return channel type that looks like voice."""
        return MagicMock(name="voice")


@dataclass
class FakeGuild:
    """Fake Discord guild."""

    id: int
    name: str = "Test Guild"
    voice_channels: list[FakeVoiceChannel] = field(default_factory=list)
    me: FakeMember | None = None


@dataclass
class FakeVoiceClient:
    """Fake Discord voice client."""

    channel: FakeVoiceChannel
    is_connected_value: bool = True
    disconnect_called: bool = False

    def is_connected(self) -> bool:
        return self.is_connected_value

    async def disconnect(self, *, force: bool = False) -> None:
        self.disconnect_called = True
        self.is_connected_value = False


class TestAutoLeave:
    """Tests for auto-leave when bot is alone in VC."""

    @pytest.mark.asyncio
    async def test_auto_leave_detects_bot_alone(self) -> None:
        """Auto-leave should detect when bot is the only member in VC."""
        from clanker_bot.cogs.vc_monitor import is_bot_alone_in_channel

        bot_member = FakeMember(id=123, name="Clanker9000", bot=True)
        channel = FakeVoiceChannel(id=1, members=[bot_member])

        assert is_bot_alone_in_channel(channel, bot_member.id) is True

    @pytest.mark.asyncio
    async def test_auto_leave_ignores_when_humans_present(self) -> None:
        """Auto-leave should not trigger when humans are in VC."""
        from clanker_bot.cogs.vc_monitor import is_bot_alone_in_channel

        bot_member = FakeMember(id=123, name="Clanker9000", bot=True)
        human_member = FakeMember(id=456, name="Human", bot=False)
        channel = FakeVoiceChannel(id=1, members=[bot_member, human_member])

        assert is_bot_alone_in_channel(channel, bot_member.id) is False

    @pytest.mark.asyncio
    async def test_auto_leave_ignores_other_bots(self) -> None:
        """Auto-leave should not count other bots as humans."""
        from clanker_bot.cogs.vc_monitor import is_bot_alone_in_channel

        bot_member = FakeMember(id=123, name="Clanker9000", bot=True)
        other_bot = FakeMember(id=789, name="MusicBot", bot=True)
        channel = FakeVoiceChannel(id=1, members=[bot_member, other_bot])

        # Only bots present - should trigger leave
        assert is_bot_alone_in_channel(channel, bot_member.id) is True

    @pytest.mark.asyncio
    async def test_auto_leave_grace_period_waits_before_disconnect(self) -> None:
        """Auto-leave should wait grace period before disconnecting."""
        from clanker_bot.cogs.vc_monitor import AutoLeaveManager

        bot_member = FakeMember(id=123, name="Clanker9000", bot=True)
        channel = FakeVoiceChannel(id=1, members=[bot_member])
        voice_client = FakeVoiceClient(channel=channel)

        manager = AutoLeaveManager(grace_period_seconds=0.1)

        # Schedule auto-leave
        task = manager.schedule_leave(voice_client, channel.id)

        # Immediately should not have left yet
        assert voice_client.disconnect_called is False

        # Wait for grace period
        await asyncio.sleep(0.15)

        # Should have disconnected
        assert voice_client.disconnect_called is True

    @pytest.mark.asyncio
    async def test_auto_leave_cancels_on_user_join(self) -> None:
        """Auto-leave should cancel if a human joins during grace period."""
        from clanker_bot.cogs.vc_monitor import AutoLeaveManager

        bot_member = FakeMember(id=123, name="Clanker9000", bot=True)
        channel = FakeVoiceChannel(id=1, members=[bot_member])
        voice_client = FakeVoiceClient(channel=channel)

        manager = AutoLeaveManager(grace_period_seconds=0.5)

        # Schedule auto-leave
        manager.schedule_leave(voice_client, channel.id)

        # Cancel before grace period ends
        await asyncio.sleep(0.1)
        manager.cancel_leave(channel.id)

        # Wait for what would have been the grace period
        await asyncio.sleep(0.5)

        # Should NOT have disconnected
        assert voice_client.disconnect_called is False


class TestNudgeToJoin:
    """Tests for nudge-to-join when 2+ users in VC."""

    @pytest.mark.asyncio
    async def test_detects_two_or_more_humans_in_vc(self) -> None:
        """Should detect when 2+ humans are in a VC."""
        from clanker_bot.cogs.vc_monitor import get_active_voice_channels

        human1 = FakeMember(id=1, name="User1", bot=False)
        human2 = FakeMember(id=2, name="User2", bot=False)
        bot = FakeMember(id=3, name="Bot", bot=True)

        channel = FakeVoiceChannel(id=100, members=[human1, human2, bot])
        guild = FakeGuild(id=1, voice_channels=[channel])

        active = get_active_voice_channels(guild, min_humans=2)
        assert len(active) == 1
        assert active[0] == channel

    @pytest.mark.asyncio
    async def test_ignores_channels_with_one_human(self) -> None:
        """Should not include channels with only 1 human."""
        from clanker_bot.cogs.vc_monitor import get_active_voice_channels

        human1 = FakeMember(id=1, name="User1", bot=False)
        channel = FakeVoiceChannel(id=100, members=[human1])
        guild = FakeGuild(id=1, voice_channels=[channel])

        active = get_active_voice_channels(guild, min_humans=2)
        assert len(active) == 0

    @pytest.mark.asyncio
    async def test_ignores_channels_with_only_bots(self) -> None:
        """Should not include channels with only bots."""
        from clanker_bot.cogs.vc_monitor import get_active_voice_channels

        bot1 = FakeMember(id=1, name="Bot1", bot=True)
        bot2 = FakeMember(id=2, name="Bot2", bot=True)
        channel = FakeVoiceChannel(id=100, members=[bot1, bot2])
        guild = FakeGuild(id=1, voice_channels=[channel])

        active = get_active_voice_channels(guild, min_humans=2)
        assert len(active) == 0

    def test_tracks_nudged_channels_to_avoid_spam(self) -> None:
        """Should not nudge the same active session repeatedly."""
        from clanker_bot.cogs.vc_monitor import NudgeTracker

        tracker = NudgeTracker()

        # First time - should nudge
        assert tracker.should_nudge(guild_id=1, channel_id=100) is True

        # Mark as nudged (session is now active)
        tracker.mark_nudged(guild_id=1, channel_id=100)

        # Should not nudge again during same session
        assert tracker.should_nudge(guild_id=1, channel_id=100) is False

    def test_resets_when_session_ends(self) -> None:
        """Should allow nudge after session ends (channel goes inactive)."""
        from clanker_bot.cogs.vc_monitor import NudgeTracker

        tracker = NudgeTracker()

        # Nudge and mark
        tracker.mark_nudged(guild_id=1, channel_id=100)
        assert tracker.should_nudge(guild_id=1, channel_id=100) is False

        # Session ends (channel drops below threshold)
        tracker.end_session(guild_id=1, channel_id=100)

        # New session - should nudge again
        assert tracker.should_nudge(guild_id=1, channel_id=100) is True

    def test_resets_when_bot_joins(self) -> None:
        """Should reset nudge when bot joins the channel."""
        from clanker_bot.cogs.vc_monitor import NudgeTracker

        tracker = NudgeTracker()

        tracker.mark_nudged(guild_id=1, channel_id=100)
        assert tracker.should_nudge(guild_id=1, channel_id=100) is False

        # Bot joins - session fulfilled
        tracker.on_bot_joined(guild_id=1, channel_id=100)

        # After bot leaves and new session starts, should nudge again
        assert tracker.should_nudge(guild_id=1, channel_id=100) is True

    def test_independent_sessions_per_channel(self) -> None:
        """Different channels should have independent sessions."""
        from clanker_bot.cogs.vc_monitor import NudgeTracker

        tracker = NudgeTracker()

        # Nudge channel 100
        tracker.mark_nudged(guild_id=1, channel_id=100)

        # Channel 200 should still be nudgeable
        assert tracker.should_nudge(guild_id=1, channel_id=200) is True

        # End session for channel 100
        tracker.end_session(guild_id=1, channel_id=100)

        # Channel 100 should be nudgeable again
        assert tracker.should_nudge(guild_id=1, channel_id=100) is True


class TestJoinListenView:
    """Tests for the Join and Listen button view."""

    @pytest.mark.asyncio
    async def test_view_creates_with_correct_timeout(self) -> None:
        """View should have 5-minute timeout for auto-dismiss."""
        from clanker_bot.cogs.vc_monitor import JoinListenView

        view = JoinListenView(
            channel_id=100,
            channel_name="General Voice",
            on_join=AsyncMock(),
        )
        # 5 minutes = 300 seconds
        assert view.timeout == 300.0

    @pytest.mark.asyncio
    async def test_view_has_join_button(self) -> None:
        """View should have a 'Join and Listen' button."""
        from clanker_bot.cogs.vc_monitor import JoinListenView

        view = JoinListenView(
            channel_id=100,
            channel_name="General Voice",
            on_join=AsyncMock(),
        )
        # Should have at least one button child
        assert len(view.children) >= 1
        button = view.children[0]
        assert "Join" in button.label or "Listen" in button.label

    @pytest.mark.asyncio
    async def test_join_button_calls_callback(self) -> None:
        """Clicking join button should invoke the callback."""
        from clanker_bot.cogs.vc_monitor import JoinListenView

        callback = AsyncMock()
        view = JoinListenView(
            channel_id=100,
            channel_name="General Voice",
            on_join=callback,
        )

        # Simulate button click with mock interaction
        mock_interaction = MagicMock()
        mock_interaction.response = MagicMock()
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.followup = MagicMock()
        mock_interaction.followup.send = AsyncMock()
        mock_interaction.message = MagicMock()
        mock_interaction.message.delete = AsyncMock()

        # Get the button and invoke its callback
        button = view.children[0]
        await button.callback(mock_interaction)

        # Callback should have been called
        callback.assert_called_once()


class TestNudgeMessage:
    """Tests for nudge message generation."""

    def test_generates_appropriate_message(self) -> None:
        """Nudge message should mention the voice channel."""
        from clanker_bot.cogs.vc_monitor import create_nudge_message

        message = create_nudge_message(
            channel_name="Gaming Voice",
            member_count=3,
        )

        assert "Gaming Voice" in message
        assert "3" in message or "three" in message.lower()

    def test_message_mentions_shitpost_feature(self) -> None:
        """Nudge message should mention /shitpost capability."""
        from clanker_bot.cogs.vc_monitor import create_nudge_message

        message = create_nudge_message(
            channel_name="General Voice",
            member_count=2,
        )

        assert "shitpost" in message.lower() or "meme" in message.lower()


class TestNudgeIntegration:
    """Integration tests for nudge-to-join in VCMonitorCog."""

    @pytest.mark.asyncio
    async def test_nudge_triggered_when_second_human_joins(self) -> None:
        """Nudge should be triggered when 2nd human joins a VC."""
        from clanker_bot.cogs.vc_monitor import NudgeTracker, VCMonitorCog

        # Create fake guild with voice channel
        human1 = FakeMember(id=1, name="User1", bot=False)
        human2 = FakeMember(id=2, name="User2", bot=False)
        channel = FakeVoiceChannel(id=100, name="General Voice", members=[human1, human2])
        guild = FakeGuild(id=1, voice_channels=[channel])
        channel.guild = guild

        # Create mock bot without voice client (bot not in VC)
        mock_bot = MagicMock()
        mock_bot.user = FakeMember(id=999, name="Clanker9000", bot=True)

        # Mock send_nudge to track calls
        nudge_callback = AsyncMock()

        nudge_tracker = NudgeTracker()
        cog = VCMonitorCog(
            bot=mock_bot,
            nudge_tracker=nudge_tracker,
            on_nudge=nudge_callback,
        )

        # Simulate human2 joining channel (before: None, after: channel)
        before = FakeVoiceState(channel=None)
        after = FakeVoiceState(channel=channel)

        # Create member with guild reference
        human2_member = MagicMock()
        human2_member.id = human2.id
        human2_member.bot = False
        human2_member.guild = guild
        guild.voice_client = None  # Bot not in VC

        await cog.on_voice_state_update(human2_member, before, after)

        # Nudge should have been triggered
        nudge_callback.assert_called_once()
        call_args = nudge_callback.call_args
        assert call_args[0][0] == guild  # First arg is guild
        assert call_args[0][1].id == channel.id  # Second arg is channel

    @pytest.mark.asyncio
    async def test_nudge_not_triggered_when_bot_already_in_vc(self) -> None:
        """Nudge should NOT trigger if bot is already in the VC."""
        from clanker_bot.cogs.vc_monitor import NudgeTracker, VCMonitorCog

        human1 = FakeMember(id=1, name="User1", bot=False)
        human2 = FakeMember(id=2, name="User2", bot=False)
        bot_member = FakeMember(id=999, name="Clanker9000", bot=True)
        channel = FakeVoiceChannel(
            id=100, name="General Voice", members=[human1, human2, bot_member]
        )
        guild = FakeGuild(id=1, voice_channels=[channel])
        channel.guild = guild

        mock_bot = MagicMock()
        mock_bot.user = bot_member

        # Bot IS in this VC
        voice_client = FakeVoiceClient(channel=channel)
        guild.voice_client = voice_client

        nudge_callback = AsyncMock()
        cog = VCMonitorCog(
            bot=mock_bot,
            nudge_tracker=NudgeTracker(),
            on_nudge=nudge_callback,
        )

        before = FakeVoiceState(channel=None)
        after = FakeVoiceState(channel=channel)

        human2_member = MagicMock()
        human2_member.id = human2.id
        human2_member.bot = False
        human2_member.guild = guild

        await cog.on_voice_state_update(human2_member, before, after)

        # Nudge should NOT be called - bot is already there
        nudge_callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_nudge_not_repeated_for_same_session(self) -> None:
        """Nudge should only happen once per session."""
        from clanker_bot.cogs.vc_monitor import NudgeTracker, VCMonitorCog

        human1 = FakeMember(id=1, name="User1", bot=False)
        human2 = FakeMember(id=2, name="User2", bot=False)
        human3 = FakeMember(id=3, name="User3", bot=False)
        channel = FakeVoiceChannel(id=100, name="General Voice", members=[human1, human2])
        guild = FakeGuild(id=1, voice_channels=[channel])
        channel.guild = guild

        mock_bot = MagicMock()
        mock_bot.user = FakeMember(id=999, name="Clanker9000", bot=True)
        guild.voice_client = None

        nudge_callback = AsyncMock()
        nudge_tracker = NudgeTracker()
        cog = VCMonitorCog(
            bot=mock_bot,
            nudge_tracker=nudge_tracker,
            on_nudge=nudge_callback,
        )

        # First join triggers nudge
        before = FakeVoiceState(channel=None)
        after = FakeVoiceState(channel=channel)

        human2_member = MagicMock()
        human2_member.id = human2.id
        human2_member.bot = False
        human2_member.guild = guild

        await cog.on_voice_state_update(human2_member, before, after)
        assert nudge_callback.call_count == 1

        # Third human joins - should NOT trigger another nudge
        channel.members.append(human3)
        human3_member = MagicMock()
        human3_member.id = human3.id
        human3_member.bot = False
        human3_member.guild = guild

        await cog.on_voice_state_update(human3_member, before, after)
        # Still only 1 call - no repeat nudge
        assert nudge_callback.call_count == 1

    @pytest.mark.asyncio
    async def test_session_ends_when_humans_drop_below_threshold(self) -> None:
        """Session should end when humans drop below 2, allowing future nudges."""
        from clanker_bot.cogs.vc_monitor import NudgeTracker, VCMonitorCog

        human1 = FakeMember(id=1, name="User1", bot=False)
        human2 = FakeMember(id=2, name="User2", bot=False)
        channel = FakeVoiceChannel(id=100, name="General Voice", members=[human1, human2])
        guild = FakeGuild(id=1, voice_channels=[channel])
        channel.guild = guild

        mock_bot = MagicMock()
        mock_bot.user = FakeMember(id=999, name="Clanker9000", bot=True)
        guild.voice_client = None

        nudge_callback = AsyncMock()
        nudge_tracker = NudgeTracker()
        cog = VCMonitorCog(
            bot=mock_bot,
            nudge_tracker=nudge_tracker,
            on_nudge=nudge_callback,
        )

        # First: human2 joins, nudge triggered
        before_join = FakeVoiceState(channel=None)
        after_join = FakeVoiceState(channel=channel)

        human2_member = MagicMock()
        human2_member.id = human2.id
        human2_member.bot = False
        human2_member.guild = guild

        await cog.on_voice_state_update(human2_member, before_join, after_join)
        assert nudge_callback.call_count == 1

        # Second: human2 leaves, only 1 human left - session ends
        channel.members = [human1]
        before_leave = FakeVoiceState(channel=channel)
        after_leave = FakeVoiceState(channel=None)

        await cog.on_voice_state_update(human2_member, before_leave, after_leave)

        # Third: human2 rejoins - should trigger NEW nudge
        channel.members = [human1, human2]
        await cog.on_voice_state_update(human2_member, before_join, after_join)
        assert nudge_callback.call_count == 2

    @pytest.mark.asyncio
    async def test_nudge_only_for_first_human_join(self) -> None:
        """Nudge should only trigger when going from 1 to 2+ humans, not 0 to 1."""
        from clanker_bot.cogs.vc_monitor import NudgeTracker, VCMonitorCog

        human1 = FakeMember(id=1, name="User1", bot=False)
        # Channel with only 1 human
        channel = FakeVoiceChannel(id=100, name="General Voice", members=[human1])
        guild = FakeGuild(id=1, voice_channels=[channel])
        channel.guild = guild

        mock_bot = MagicMock()
        mock_bot.user = FakeMember(id=999, name="Clanker9000", bot=True)
        guild.voice_client = None

        nudge_callback = AsyncMock()
        cog = VCMonitorCog(
            bot=mock_bot,
            nudge_tracker=NudgeTracker(),
            on_nudge=nudge_callback,
        )

        # First human joins - should NOT nudge (only 1 human)
        before = FakeVoiceState(channel=None)
        after = FakeVoiceState(channel=channel)

        human1_member = MagicMock()
        human1_member.id = human1.id
        human1_member.bot = False
        human1_member.guild = guild

        await cog.on_voice_state_update(human1_member, before, after)
        nudge_callback.assert_not_called()
