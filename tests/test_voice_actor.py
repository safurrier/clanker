"""Tests for VoiceActor message-based voice management.

Tests cover:
- Message type definitions and immutability
- Actor state management
- Public API (join, leave, post_audio)
- Message handling and state transitions
- Timer tasks
- Sink adapter
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.fakes import FakeSTT

# --- Message Type Tests ---


class TestMessageTypes:
    """Test message type definitions and immutability."""

    def test_join_request_is_frozen(self) -> None:
        """JoinRequest should be immutable."""
        from clanker_bot.voice_actor import JoinRequest

        response_queue: asyncio.Queue = asyncio.Queue()
        msg = JoinRequest(channel_id=123, guild_id=456, response_queue=response_queue)

        with pytest.raises(AttributeError):
            msg.channel_id = 789  # type: ignore[misc]

    def test_leave_request_is_frozen(self) -> None:
        """LeaveRequest should be immutable."""
        from clanker_bot.voice_actor import LeaveRequest

        response_queue: asyncio.Queue = asyncio.Queue()
        msg = LeaveRequest(response_queue=response_queue)

        with pytest.raises(AttributeError):
            msg.response_queue = asyncio.Queue()  # type: ignore[misc]

    def test_audio_received_captures_timestamp(self) -> None:
        """AudioReceived should store timestamp."""
        from clanker_bot.voice_actor import AudioReceived

        now = datetime.now()
        msg = AudioReceived(user_id=1, pcm_bytes=b"\x00\x00", timestamp=now)

        assert msg.user_id == 1
        assert msg.pcm_bytes == b"\x00\x00"
        assert msg.timestamp == now

    def test_audio_received_is_frozen(self) -> None:
        """AudioReceived should be immutable."""
        from clanker_bot.voice_actor import AudioReceived

        msg = AudioReceived(user_id=1, pcm_bytes=b"\x00\x00", timestamp=datetime.now())

        with pytest.raises(AttributeError):
            msg.user_id = 2  # type: ignore[misc]

    def test_reconnect_attempt_tracks_attempt_number(self) -> None:
        """ReconnectAttempt should track which attempt this is."""
        from clanker_bot.voice_actor import ReconnectAttempt

        msg = ReconnectAttempt(attempt=2)
        assert msg.attempt == 2

    def test_stale_timeout_captures_silence_duration(self) -> None:
        """StaleTimeout should capture how long audio was stale."""
        from clanker_bot.voice_actor import StaleTimeout

        msg = StaleTimeout(silence_seconds=120.5)
        assert msg.silence_seconds == 120.5

    def test_disconnect_detected_captures_error(self) -> None:
        """DisconnectDetected should capture the error."""
        from clanker_bot.voice_actor import DisconnectDetected

        error = Exception("Connection lost")
        msg = DisconnectDetected(error=error)
        assert msg.error is error

        msg_none = DisconnectDetected(error=None)
        assert msg_none.error is None

    def test_send_keepalive_is_singleton_like(self) -> None:
        """SendKeepalive should be a simple marker message."""
        from clanker_bot.voice_actor import SendKeepalive

        msg = SendKeepalive()
        assert msg is not None

    def test_process_buffers_is_singleton_like(self) -> None:
        """ProcessBuffers should be a simple marker message."""
        from clanker_bot.voice_actor import ProcessBuffers

        msg = ProcessBuffers()
        assert msg is not None


class TestResultTypes:
    """Test result type definitions."""

    def test_join_result_success(self) -> None:
        """JoinResult should represent success."""
        from clanker_bot.voice_actor import JoinResult

        result = JoinResult(success=True)
        assert result.success is True
        assert result.error is None

    def test_join_result_failure(self) -> None:
        """JoinResult should represent failure with error."""
        from clanker_bot.voice_actor import JoinResult

        result = JoinResult(success=False, error="Already connected")
        assert result.success is False
        assert result.error == "Already connected"

    def test_leave_result_success(self) -> None:
        """LeaveResult should represent success."""
        from clanker_bot.voice_actor import LeaveResult

        result = LeaveResult(success=True)
        assert result.success is True


# --- Actor State Tests ---


class TestVoiceActorState:
    """Test VoiceActor state management."""

    def test_actor_starts_disconnected(self) -> None:
        """Actor should start in disconnected state."""
        from clanker_bot.voice_actor import VoiceActor, VoiceStatus

        bot = MagicMock()
        actor = VoiceActor(bot=bot, stt=FakeSTT())

        assert actor.status == VoiceStatus.DISCONNECTED
        assert actor.guild_id is None
        assert actor.channel_id is None
        assert actor.voice_client is None

    def test_actor_has_empty_inbox_initially(self) -> None:
        """Actor should start with empty message queue."""
        from clanker_bot.voice_actor import VoiceActor

        bot = MagicMock()
        actor = VoiceActor(bot=bot, stt=FakeSTT())

        assert actor._inbox.empty()

    def test_actor_initializes_detector(self) -> None:
        """Actor should initialize a detector if not provided."""
        from clanker_bot.voice_actor import VoiceActor

        bot = MagicMock()
        actor = VoiceActor(bot=bot, stt=FakeSTT())

        assert actor.detector is not None

    def test_actor_uses_provided_detector(self) -> None:
        """Actor should use provided detector."""
        from clanker_bot.voice_actor import VoiceActor

        bot = MagicMock()
        fake_detector = MagicMock()
        actor = VoiceActor(bot=bot, stt=FakeSTT(), detector=fake_detector)

        assert actor.detector is fake_detector


# --- Public API Tests ---


class TestVoiceActorPublicAPI:
    """Test VoiceActor public methods."""

    @pytest.mark.asyncio
    async def test_join_posts_message_and_waits_for_result(self) -> None:
        """join() should post JoinRequest and return result."""
        from clanker_bot.voice_actor import JoinRequest, JoinResult, VoiceActor

        bot = MagicMock()
        actor = VoiceActor(bot=bot, stt=FakeSTT())

        # Mock handler that responds immediately
        async def mock_handler() -> None:
            msg = await actor._inbox.get()
            assert isinstance(msg, JoinRequest)
            assert msg.channel_id == 123
            assert msg.guild_id == 456
            await msg.response_queue.put(JoinResult(success=True))

        handler_task = asyncio.create_task(mock_handler())

        result = await actor.join(channel_id=123, guild_id=456)

        assert result.success is True
        await handler_task

    @pytest.mark.asyncio
    async def test_leave_posts_message_and_waits_for_result(self) -> None:
        """leave() should post LeaveRequest and return result."""
        from clanker_bot.voice_actor import LeaveRequest, LeaveResult, VoiceActor

        bot = MagicMock()
        actor = VoiceActor(bot=bot, stt=FakeSTT())

        async def mock_handler() -> None:
            msg = await actor._inbox.get()
            assert isinstance(msg, LeaveRequest)
            await msg.response_queue.put(LeaveResult(success=True))

        handler_task = asyncio.create_task(mock_handler())

        result = await actor.leave()

        assert result.success is True
        await handler_task

    @pytest.mark.asyncio
    async def test_post_audio_is_nonblocking(self) -> None:
        """post_audio() should not block (fire and forget)."""
        from clanker_bot.voice_actor import AudioReceived, VoiceActor

        bot = MagicMock()
        actor = VoiceActor(bot=bot, stt=FakeSTT())

        # Should not block even with no consumer
        actor.post_audio(user_id=1, pcm_bytes=b"\x00\x00")

        # Message should be in queue
        assert not actor._inbox.empty()
        msg = await actor._inbox.get()
        assert isinstance(msg, AudioReceived)
        assert msg.user_id == 1
        assert msg.pcm_bytes == b"\x00\x00"

    @pytest.mark.asyncio
    async def test_post_disconnect_is_nonblocking(self) -> None:
        """post_disconnect() should not block."""
        from clanker_bot.voice_actor import DisconnectDetected, VoiceActor

        bot = MagicMock()
        actor = VoiceActor(bot=bot, stt=FakeSTT())

        error = Exception("Connection lost")
        actor.post_disconnect(error)

        msg = await actor._inbox.get()
        assert isinstance(msg, DisconnectDetected)
        assert msg.error is error

    def test_get_transcripts_returns_buffer_contents(self) -> None:
        """get_transcripts() should return transcript buffer for guild."""
        from clanker.voice.chunker import AudioChunk
        from clanker.voice.worker import TranscriptEvent
        from clanker_bot.voice_actor import VoiceActor

        bot = MagicMock()
        actor = VoiceActor(bot=bot, stt=FakeSTT())

        # Manually add transcript for testing
        now = datetime.now()
        event = TranscriptEvent(
            speaker_id=1,
            chunk_id="test-chunk-1",
            text="hello",
            chunk=AudioChunk(start_ms=0, end_ms=1000),
            start_time=now,
            end_time=now,
        )
        actor._transcript_buffer.add(guild_id=456, event=event)

        transcripts = actor.get_transcripts(guild_id=456)

        assert len(transcripts) == 1
        assert transcripts[0].text == "hello"

    def test_get_transcripts_empty_for_unknown_guild(self) -> None:
        """get_transcripts() should return empty list for unknown guild."""
        from clanker_bot.voice_actor import VoiceActor

        bot = MagicMock()
        actor = VoiceActor(bot=bot, stt=FakeSTT())

        transcripts = actor.get_transcripts(guild_id=999)

        assert transcripts == []


# --- Message Handler Tests ---


class TestMessageHandling:
    """Test VoiceActor message processing."""

    @pytest.mark.asyncio
    async def test_handle_logs_every_message(self) -> None:
        """_handle should log message type and status."""
        from clanker_bot.voice_actor import SendKeepalive, VoiceActor

        bot = MagicMock()
        actor = VoiceActor(bot=bot, stt=FakeSTT())

        with patch("clanker_bot.voice_actor.logger") as mock_logger:
            await actor._handle(SendKeepalive())

            mock_logger.debug.assert_called()
            call_args = str(mock_logger.debug.call_args)
            assert "SendKeepalive" in call_args or "voice.msg" in call_args

    @pytest.mark.asyncio
    async def test_audio_received_updates_last_audio_time(self) -> None:
        """AudioReceived should update _last_audio_time when connected."""
        from clanker_bot.voice_actor import AudioReceived, VoiceActor, VoiceStatus

        bot = MagicMock()
        actor = VoiceActor(bot=bot, stt=FakeSTT())
        actor._status = VoiceStatus.CONNECTED

        assert actor._last_audio_time is None

        now = datetime.now()
        await actor._handle(AudioReceived(user_id=1, pcm_bytes=b"\x00", timestamp=now))

        assert actor._last_audio_time == now

    @pytest.mark.asyncio
    async def test_audio_received_buffers_audio(self) -> None:
        """AudioReceived should buffer audio data."""
        from clanker_bot.voice_actor import AudioReceived, VoiceActor, VoiceStatus

        bot = MagicMock()
        actor = VoiceActor(bot=bot, stt=FakeSTT())
        actor._status = VoiceStatus.CONNECTED

        await actor._handle(
            AudioReceived(user_id=1, pcm_bytes=b"\x01\x02", timestamp=datetime.now())
        )
        await actor._handle(
            AudioReceived(user_id=1, pcm_bytes=b"\x03\x04", timestamp=datetime.now())
        )

        assert 1 in actor._audio_buffers
        assert bytes(actor._audio_buffers[1].pcm_bytes) == b"\x01\x02\x03\x04"

    @pytest.mark.asyncio
    async def test_audio_received_ignored_when_disconnected(self) -> None:
        """AudioReceived should be ignored when not connected."""
        from clanker_bot.voice_actor import AudioReceived, VoiceActor, VoiceStatus

        bot = MagicMock()
        actor = VoiceActor(bot=bot, stt=FakeSTT())
        assert actor._status == VoiceStatus.DISCONNECTED

        await actor._handle(
            AudioReceived(user_id=1, pcm_bytes=b"\x00", timestamp=datetime.now())
        )

        assert actor._last_audio_time is None
        assert 1 not in actor._audio_buffers

    @pytest.mark.asyncio
    async def test_stale_timeout_transitions_to_reconnecting(self) -> None:
        """StaleTimeout should transition from CONNECTED to RECONNECTING."""
        from clanker_bot.voice_actor import (
            ReconnectAttempt,
            StaleTimeout,
            VoiceActor,
            VoiceStatus,
        )

        bot = MagicMock()
        actor = VoiceActor(bot=bot, stt=FakeSTT())
        actor._status = VoiceStatus.CONNECTED
        actor._guild_id = 456
        actor._channel_id = 123
        actor._voice_client = MagicMock()
        actor._voice_client.is_connected.return_value = True
        actor._voice_client.disconnect = AsyncMock()

        await actor._handle(StaleTimeout(silence_seconds=120.0))

        assert actor._status == VoiceStatus.RECONNECTING
        assert actor._reconnect_attempt == 0

        # Should have posted a ReconnectAttempt message
        msg = await actor._inbox.get()
        assert isinstance(msg, ReconnectAttempt)
        assert msg.attempt == 1

    @pytest.mark.asyncio
    async def test_stale_timeout_ignored_when_not_connected(self) -> None:
        """StaleTimeout should be ignored when not in CONNECTED state."""
        from clanker_bot.voice_actor import StaleTimeout, VoiceActor, VoiceStatus

        bot = MagicMock()
        actor = VoiceActor(bot=bot, stt=FakeSTT())
        actor._status = VoiceStatus.DISCONNECTED

        await actor._handle(StaleTimeout(silence_seconds=120.0))

        # Should remain disconnected
        assert actor._status == VoiceStatus.DISCONNECTED


# --- Join Handler Tests ---


class TestJoinHandler:
    """Test _handle_join implementation."""

    @pytest.mark.asyncio
    async def test_join_succeeds_from_disconnected(self) -> None:
        """Join should succeed when disconnected."""
        import discord

        from clanker_bot.voice_actor import VoiceActor, VoiceStatus

        bot = MagicMock()
        actor = VoiceActor(bot=bot, stt=FakeSTT())

        # Mock channel and voice client — spec so isinstance() works
        mock_channel = MagicMock(spec=discord.VoiceChannel)
        mock_voice_client = MagicMock()
        mock_channel.connect = AsyncMock(return_value=mock_voice_client)
        mock_channel.guild.id = 456
        mock_channel.id = 123

        bot.get_channel.return_value = mock_channel

        result = await actor._handle_join(channel_id=123, guild_id=456)

        assert result.success is True
        assert actor._status == VoiceStatus.CONNECTED
        assert actor._guild_id == 456
        assert actor._channel_id == 123
        mock_voice_client.listen.assert_called_once()

    @pytest.mark.asyncio
    async def test_join_fails_when_already_connected(self) -> None:
        """Join should fail when already in a channel."""
        from clanker_bot.voice_actor import VoiceActor, VoiceStatus

        bot = MagicMock()
        actor = VoiceActor(bot=bot, stt=FakeSTT())
        actor._status = VoiceStatus.CONNECTED

        result = await actor._handle_join(channel_id=123, guild_id=456)

        assert result.success is False
        assert "already" in result.error.lower()

    @pytest.mark.asyncio
    async def test_join_fails_when_channel_not_found(self) -> None:
        """Join should fail when channel doesn't exist."""
        from clanker_bot.voice_actor import VoiceActor, VoiceStatus

        bot = MagicMock()
        bot.get_channel.return_value = None
        actor = VoiceActor(bot=bot, stt=FakeSTT())

        result = await actor._handle_join(channel_id=123, guild_id=456)

        assert result.success is False
        assert "not found" in result.error.lower()
        assert actor._status == VoiceStatus.DISCONNECTED

    @pytest.mark.asyncio
    async def test_join_handles_connection_error(self) -> None:
        """Join should handle Discord connection errors gracefully."""
        import discord

        from clanker_bot.voice_actor import VoiceActor, VoiceStatus

        bot = MagicMock()
        mock_channel = MagicMock(spec=discord.VoiceChannel)
        mock_channel.connect = AsyncMock(side_effect=Exception("Connection refused"))
        bot.get_channel.return_value = mock_channel

        actor = VoiceActor(bot=bot, stt=FakeSTT())

        result = await actor._handle_join(channel_id=123, guild_id=456)

        assert result.success is False
        assert "Connection refused" in result.error
        assert actor._status == VoiceStatus.DISCONNECTED


# --- Leave Handler Tests ---


class TestLeaveHandler:
    """Test _handle_leave implementation."""

    @pytest.mark.asyncio
    async def test_leave_succeeds_when_connected(self) -> None:
        """Leave should succeed when connected."""
        from clanker_bot.voice_actor import VoiceActor, VoiceStatus

        bot = MagicMock()
        actor = VoiceActor(bot=bot, stt=FakeSTT())
        actor._status = VoiceStatus.CONNECTED
        actor._guild_id = 456
        actor._channel_id = 123

        mock_voice_client = MagicMock()
        mock_voice_client.is_connected.return_value = True
        mock_voice_client.disconnect = AsyncMock()
        actor._voice_client = mock_voice_client

        result = await actor._handle_leave()

        assert result.success is True
        assert actor._status == VoiceStatus.DISCONNECTED
        assert actor._guild_id is None
        assert actor._channel_id is None
        mock_voice_client.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_leave_fails_when_disconnected(self) -> None:
        """Leave should fail when already disconnected."""
        from clanker_bot.voice_actor import VoiceActor, VoiceStatus

        bot = MagicMock()
        actor = VoiceActor(bot=bot, stt=FakeSTT())
        assert actor._status == VoiceStatus.DISCONNECTED

        result = await actor._handle_leave()

        assert result.success is False
        assert "not connected" in result.error.lower()


# --- Reconnect Handler Tests ---


class TestReconnectHandler:
    """Test _handle_reconnect implementation."""

    @pytest.mark.asyncio
    async def test_reconnect_succeeds(self) -> None:
        """Reconnect should succeed when channel is available."""
        import discord

        from clanker_bot.voice_actor import VoiceActor, VoiceStatus

        bot = MagicMock()
        mock_channel = MagicMock(spec=discord.VoiceChannel)
        mock_voice_client = MagicMock()
        mock_channel.connect = AsyncMock(return_value=mock_voice_client)
        bot.get_channel.return_value = mock_channel

        actor = VoiceActor(bot=bot, stt=FakeSTT())
        actor._status = VoiceStatus.RECONNECTING
        actor._guild_id = 456
        actor._channel_id = 123

        await actor._handle_reconnect(attempt=1)

        assert actor._status == VoiceStatus.CONNECTED
        assert actor._reconnect_attempt == 0

    @pytest.mark.asyncio
    async def test_reconnect_gives_up_after_max_retries(self) -> None:
        """Reconnect should give up after max retries."""
        from clanker_bot.voice_actor import VoiceActor, VoiceStatus

        bot = MagicMock()
        actor = VoiceActor(bot=bot, stt=FakeSTT(), reconnect_max_retries=3)
        actor._status = VoiceStatus.RECONNECTING
        actor._guild_id = 456
        actor._channel_id = 123

        # Attempt 4 (exceeds max of 3)
        await actor._handle_reconnect(attempt=4)

        assert actor._status == VoiceStatus.DISCONNECTED

    @pytest.mark.asyncio
    async def test_reconnect_posts_next_attempt_on_failure(self) -> None:
        """Reconnect should post next attempt on failure."""
        import discord

        from clanker_bot.voice_actor import ReconnectAttempt, VoiceActor, VoiceStatus

        bot = MagicMock()
        mock_channel = MagicMock(spec=discord.VoiceChannel)
        mock_channel.connect = AsyncMock(side_effect=Exception("Connection failed"))
        bot.get_channel.return_value = mock_channel

        actor = VoiceActor(
            bot=bot,
            stt=FakeSTT(),
            reconnect_delay_seconds=0.01,  # Fast for testing
        )
        actor._status = VoiceStatus.RECONNECTING
        actor._guild_id = 456
        actor._channel_id = 123

        await actor._handle_reconnect(attempt=1)

        # Should have posted next attempt
        msg = await asyncio.wait_for(actor._inbox.get(), timeout=1.0)
        assert isinstance(msg, ReconnectAttempt)
        assert msg.attempt == 2

    @pytest.mark.asyncio
    async def test_reconnect_ignored_when_not_reconnecting(self) -> None:
        """Reconnect should be ignored when state changed."""
        from clanker_bot.voice_actor import VoiceActor, VoiceStatus

        bot = MagicMock()
        actor = VoiceActor(bot=bot, stt=FakeSTT())
        actor._status = VoiceStatus.DISCONNECTED  # State changed

        await actor._handle_reconnect(attempt=1)

        # Should remain disconnected, nothing happened
        assert actor._status == VoiceStatus.DISCONNECTED
        assert actor._inbox.empty()


# --- Disconnect Handler Tests ---


class TestDisconnectHandler:
    """Test _handle_disconnect implementation."""

    @pytest.mark.asyncio
    async def test_unexpected_disconnect_triggers_reconnect(self) -> None:
        """Unexpected disconnect should trigger reconnect."""
        from clanker_bot.voice_actor import (
            ReconnectAttempt,
            VoiceActor,
            VoiceStatus,
        )

        bot = MagicMock()
        actor = VoiceActor(bot=bot, stt=FakeSTT())
        actor._status = VoiceStatus.CONNECTED
        actor._guild_id = 456
        actor._channel_id = 123

        await actor._handle_disconnect(error=Exception("Connection lost"))

        assert actor._status == VoiceStatus.RECONNECTING

        # Should have posted reconnect attempt
        msg = await actor._inbox.get()
        assert isinstance(msg, ReconnectAttempt)
        assert msg.attempt == 1

    @pytest.mark.asyncio
    async def test_disconnect_ignored_when_already_disconnected(self) -> None:
        """Disconnect should be ignored when already disconnected."""
        from clanker_bot.voice_actor import VoiceActor, VoiceStatus

        bot = MagicMock()
        actor = VoiceActor(bot=bot, stt=FakeSTT())
        actor._status = VoiceStatus.DISCONNECTED

        await actor._handle_disconnect(error=None)

        assert actor._status == VoiceStatus.DISCONNECTED
        assert actor._inbox.empty()

    @pytest.mark.asyncio
    async def test_disconnect_ignored_when_already_reconnecting(self) -> None:
        """Disconnect should be ignored when already reconnecting."""
        from clanker_bot.voice_actor import VoiceActor, VoiceStatus

        bot = MagicMock()
        actor = VoiceActor(bot=bot, stt=FakeSTT())
        actor._status = VoiceStatus.RECONNECTING

        await actor._handle_disconnect(error=Exception("Another disconnect"))

        # Should remain reconnecting, no new messages
        assert actor._status == VoiceStatus.RECONNECTING
        assert actor._inbox.empty()


# --- Keepalive Handler Tests ---


class TestKeepaliveHandler:
    """Test _handle_keepalive implementation."""

    def test_keepalive_sends_silence_when_connected(self) -> None:
        """Keepalive should send silence packet when connected."""
        from clanker_bot.voice_actor import OPUS_SILENCE_FRAME, VoiceActor, VoiceStatus

        bot = MagicMock()
        actor = VoiceActor(bot=bot, stt=FakeSTT())
        actor._status = VoiceStatus.CONNECTED

        mock_voice_client = MagicMock()
        mock_voice_client.is_connected.return_value = True
        actor._voice_client = mock_voice_client

        actor._handle_keepalive()

        mock_voice_client.send_audio_packet.assert_called_once_with(
            OPUS_SILENCE_FRAME, encode=False
        )

    def test_keepalive_ignored_when_disconnected(self) -> None:
        """Keepalive should be ignored when disconnected."""
        from clanker_bot.voice_actor import VoiceActor, VoiceStatus

        bot = MagicMock()
        actor = VoiceActor(bot=bot, stt=FakeSTT())
        actor._status = VoiceStatus.DISCONNECTED

        # Should not raise even without voice client
        actor._handle_keepalive()


# --- Timer Task Tests ---


class TestTimerTasks:
    """Test periodic timer tasks."""

    @pytest.mark.asyncio
    async def test_keepalive_timer_posts_messages(self) -> None:
        """Keepalive timer should post SendKeepalive messages."""
        from clanker_bot.voice_actor import SendKeepalive, VoiceActor

        bot = MagicMock()
        actor = VoiceActor(bot=bot, stt=FakeSTT(), keepalive_interval=0.05)

        task = asyncio.create_task(actor._keepalive_timer())

        await asyncio.sleep(0.12)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Should have 2+ messages
        count = 0
        while not actor._inbox.empty():
            msg = await actor._inbox.get()
            if isinstance(msg, SendKeepalive):
                count += 1

        assert count >= 2

    @pytest.mark.asyncio
    async def test_process_timer_posts_messages(self) -> None:
        """Process timer should post ProcessBuffers messages."""
        from clanker_bot.voice_actor import ProcessBuffers, VoiceActor

        bot = MagicMock()
        actor = VoiceActor(bot=bot, stt=FakeSTT(), process_interval=0.05)

        task = asyncio.create_task(actor._process_timer())

        await asyncio.sleep(0.12)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        count = 0
        while not actor._inbox.empty():
            msg = await actor._inbox.get()
            if isinstance(msg, ProcessBuffers):
                count += 1

        assert count >= 2

    @pytest.mark.asyncio
    async def test_health_timer_posts_stale_when_silent(self) -> None:
        """Health timer should post StaleTimeout when audio silent."""
        from clanker_bot.voice_actor import StaleTimeout, VoiceActor, VoiceStatus

        bot = MagicMock()
        actor = VoiceActor(
            bot=bot,
            stt=FakeSTT(),
            health_check_interval=0.05,
            stale_threshold_seconds=0.1,
        )
        actor._status = VoiceStatus.CONNECTED
        actor._last_audio_time = datetime.now() - timedelta(seconds=0.2)

        task = asyncio.create_task(actor._health_timer())

        await asyncio.sleep(0.08)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Should have posted StaleTimeout
        msg = await actor._inbox.get()
        assert isinstance(msg, StaleTimeout)
        assert msg.silence_seconds >= 0.1

    @pytest.mark.asyncio
    async def test_health_timer_only_posts_once_per_stale_period(self) -> None:
        """Health timer should only post StaleTimeout once until audio resumes."""
        from clanker_bot.voice_actor import StaleTimeout, VoiceActor, VoiceStatus

        bot = MagicMock()
        actor = VoiceActor(
            bot=bot,
            stt=FakeSTT(),
            health_check_interval=0.03,
            stale_threshold_seconds=0.05,
        )
        actor._status = VoiceStatus.CONNECTED
        actor._last_audio_time = datetime.now() - timedelta(seconds=0.1)

        task = asyncio.create_task(actor._health_timer())

        # Wait for multiple check intervals
        await asyncio.sleep(0.15)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Should only have one StaleTimeout
        count = 0
        while not actor._inbox.empty():
            msg = await actor._inbox.get()
            if isinstance(msg, StaleTimeout):
                count += 1

        assert count == 1


# --- Sink Tests ---


class TestVoiceActorSink:
    """Test thin sink adapter that posts to actor."""

    def test_sink_wants_pcm_not_opus(self) -> None:
        """Sink should request PCM audio."""
        from clanker_bot.voice_actor import VoiceActor, VoiceActorSink

        bot = MagicMock()
        actor = VoiceActor(bot=bot, stt=FakeSTT())
        sink = VoiceActorSink(actor)

        assert sink.wants_opus() is False

    def test_sink_ignores_invalid_user(self) -> None:
        """Sink should ignore frames without valid user."""
        from clanker_bot.voice_actor import VoiceActor, VoiceActorSink

        bot = MagicMock()
        actor = VoiceActor(bot=bot, stt=FakeSTT())
        sink = VoiceActorSink(actor)

        # No user
        sink.write(None, MagicMock())
        assert actor._inbox.empty()

        # User without id
        sink.write(MagicMock(spec=[]), MagicMock())
        assert actor._inbox.empty()

    def test_sink_ignores_missing_pcm(self) -> None:
        """Sink should ignore frames without PCM data."""
        from clanker_bot.voice_actor import VoiceActor, VoiceActorSink

        bot = MagicMock()
        actor = VoiceActor(bot=bot, stt=FakeSTT())
        sink = VoiceActorSink(actor)

        mock_user = MagicMock()
        mock_user.id = 123
        mock_data = MagicMock(spec=[])  # No pcm attribute

        sink.write(mock_user, mock_data)
        assert actor._inbox.empty()

    def test_sink_cleanup_is_noop(self) -> None:
        """Sink cleanup should be a no-op."""
        from clanker_bot.voice_actor import VoiceActor, VoiceActorSink

        bot = MagicMock()
        actor = VoiceActor(bot=bot, stt=FakeSTT())
        sink = VoiceActorSink(actor)

        # Should not raise
        sink.cleanup()


# --- Should Process Tests ---


class TestShouldProcess:
    """Test _should_process logic."""

    def test_should_process_false_when_no_buffers(self) -> None:
        """should_process should return False when no buffers."""
        from clanker_bot.voice_actor import VoiceActor

        bot = MagicMock()
        actor = VoiceActor(bot=bot, stt=FakeSTT())

        assert actor._should_process() is False

    def test_should_process_true_when_chunk_threshold_reached(self) -> None:
        """should_process should return True when chunk threshold reached."""
        from clanker_bot.voice_actor import AudioBuffer, VoiceActor

        bot = MagicMock()
        actor = VoiceActor(
            bot=bot,
            stt=FakeSTT(),
            chunk_seconds=1.0,
            sample_rate_hz=16000,
        )

        # 2 seconds of audio at 16kHz mono (2 bytes per sample)
        actor._audio_buffers[1] = AudioBuffer(
            pcm_bytes=bytearray(b"\x00\x00" * 32000),  # 2 seconds
            start_time=datetime.now(),
        )

        assert actor._should_process() is True

    def test_should_process_true_when_idle_timeout_reached(self) -> None:
        """should_process should return True when idle timeout reached."""
        from clanker_bot.voice_actor import AudioBuffer, VoiceActor

        bot = MagicMock()
        actor = VoiceActor(
            bot=bot,
            stt=FakeSTT(),
            chunk_seconds=10.0,  # High threshold
            idle_timeout_seconds=1.0,
        )

        # Small buffer
        actor._audio_buffers[1] = AudioBuffer(
            pcm_bytes=bytearray(b"\x00\x00" * 100),
            start_time=datetime.now(),
        )
        # Old last audio time
        actor._last_audio_time = datetime.now() - timedelta(seconds=2.0)

        assert actor._should_process() is True

    def test_should_process_false_when_not_enough_data_or_time(self) -> None:
        """should_process should return False when neither threshold met."""
        from clanker_bot.voice_actor import AudioBuffer, VoiceActor

        bot = MagicMock()
        actor = VoiceActor(
            bot=bot,
            stt=FakeSTT(),
            chunk_seconds=10.0,  # High threshold
            idle_timeout_seconds=10.0,  # High timeout
        )

        # Small buffer
        actor._audio_buffers[1] = AudioBuffer(
            pcm_bytes=bytearray(b"\x00\x00" * 100),
            start_time=datetime.now(),
        )
        # Recent last audio time
        actor._last_audio_time = datetime.now()

        assert actor._should_process() is False


# --- Clear State Tests ---


class TestClearState:
    """Test _clear_state implementation."""

    def test_clear_state_resets_all_fields(self) -> None:
        """_clear_state should reset all connection-related fields."""
        from clanker_bot.voice_actor import AudioBuffer, VoiceActor, VoiceStatus

        bot = MagicMock()
        actor = VoiceActor(bot=bot, stt=FakeSTT())

        # Set up some state
        actor._status = VoiceStatus.CONNECTED
        actor._guild_id = 456
        actor._channel_id = 123
        actor._voice_client = MagicMock()
        actor._audio_buffers[1] = AudioBuffer()
        actor._last_audio_time = datetime.now()
        actor._reconnect_attempt = 2
        actor._stale_posted = True

        actor._clear_state()

        assert actor._status == VoiceStatus.DISCONNECTED
        assert actor._guild_id is None
        assert actor._channel_id is None
        assert actor._voice_client is None
        assert actor._audio_buffers == {}
        assert actor._last_audio_time is None
        assert actor._reconnect_attempt == 0
        assert actor._stale_posted is False
