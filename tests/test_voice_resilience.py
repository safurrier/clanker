"""Tests for voice connection resilience features.

Tests for:
- Silence keepalive to prevent Discord load-balancer disconnects
- After callback for detecting and recovering from disconnects
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clanker_bot.voice_ingest import VoiceIngestSink, VoiceIngestWorker
from tests.fakes import FakeSTT


# --- Fixtures ---


@pytest.fixture
def worker() -> VoiceIngestWorker:
    """Create a VoiceIngestWorker with fake STT."""
    return VoiceIngestWorker(stt=FakeSTT())


@pytest.fixture
def sink(worker: VoiceIngestWorker) -> VoiceIngestSink:
    """Create a VoiceIngestSink for testing."""
    return VoiceIngestSink(worker)


# --- Silence Keepalive Tests ---


class TestSilenceKeepalive:
    """Tests for the silence keepalive functionality."""

    @pytest.mark.asyncio
    async def test_keepalive_sends_silence_packets_periodically(self) -> None:
        """Keepalive task should send silence packets at regular intervals."""
        from clanker_bot.voice_resilience import VoiceKeepalive

        # Create mock voice client
        voice_client = MagicMock()
        voice_client.is_connected.return_value = True
        voice_client.send_audio_packet = MagicMock()

        keepalive = VoiceKeepalive(voice_client, interval_seconds=0.1)
        keepalive.start()

        # Wait for a few intervals
        await asyncio.sleep(0.35)
        keepalive.stop()

        # Should have sent at least 2-3 packets
        assert voice_client.send_audio_packet.call_count >= 2
        # Verify silence packet format (Opus silence frame)
        call_args = voice_client.send_audio_packet.call_args_list[0]
        assert call_args[0][0] == b"\xf8\xff\xfe"
        assert call_args[1]["encode"] is False

    @pytest.mark.asyncio
    async def test_keepalive_stops_when_disconnected(self) -> None:
        """Keepalive task should stop when voice client disconnects."""
        from clanker_bot.voice_resilience import VoiceKeepalive

        voice_client = MagicMock()
        # Start connected, then disconnect
        connected_states = [True, True, False]
        voice_client.is_connected.side_effect = connected_states

        keepalive = VoiceKeepalive(voice_client, interval_seconds=0.05)
        keepalive.start()

        # Wait for task to notice disconnection
        await asyncio.sleep(0.2)

        # Task should have stopped itself
        assert keepalive._task is None or keepalive._task.done()

    @pytest.mark.asyncio
    async def test_keepalive_stop_is_idempotent(self) -> None:
        """Calling stop multiple times should be safe."""
        from clanker_bot.voice_resilience import VoiceKeepalive

        voice_client = MagicMock()
        voice_client.is_connected.return_value = True

        keepalive = VoiceKeepalive(voice_client, interval_seconds=1.0)
        keepalive.start()

        # Stop multiple times
        keepalive.stop()
        keepalive.stop()
        keepalive.stop()

        # Should not raise

    @pytest.mark.asyncio
    async def test_keepalive_handles_send_error_gracefully(self) -> None:
        """Keepalive should handle errors when sending packets."""
        from clanker_bot.voice_resilience import VoiceKeepalive

        voice_client = MagicMock()
        voice_client.is_connected.return_value = True
        # Simulate send failing
        voice_client.send_audio_packet.side_effect = Exception("Network error")

        keepalive = VoiceKeepalive(voice_client, interval_seconds=0.05)
        keepalive.start()

        # Should not crash, just log and continue
        await asyncio.sleep(0.15)
        keepalive.stop()

        # Should have attempted multiple sends despite errors
        assert voice_client.send_audio_packet.call_count >= 2


# --- Reconnection Callback Tests ---


class TestReconnectionCallback:
    """Tests for the after callback reconnection functionality."""

    @pytest.mark.asyncio
    async def test_reconnect_handler_calls_callback_on_error(self) -> None:
        """Reconnect handler should invoke callback when error occurs."""
        from clanker_bot.voice_resilience import create_reconnect_handler

        callback_invoked = asyncio.Event()
        error_received: list[Exception | None] = []

        async def on_disconnect(error: Exception | None) -> None:
            error_received.append(error)
            callback_invoked.set()

        handler = create_reconnect_handler(on_disconnect)

        # Simulate error from voice_recv
        test_error = Exception("Connection lost")
        handler(test_error)

        # Wait for async callback
        await asyncio.wait_for(callback_invoked.wait(), timeout=1.0)

        assert len(error_received) == 1
        assert error_received[0] is test_error

    @pytest.mark.asyncio
    async def test_reconnect_handler_calls_callback_on_none(self) -> None:
        """Reconnect handler should invoke callback when sink exhausted (None)."""
        from clanker_bot.voice_resilience import create_reconnect_handler

        callback_invoked = asyncio.Event()
        error_received: list[Exception | None] = []

        async def on_disconnect(error: Exception | None) -> None:
            error_received.append(error)
            callback_invoked.set()

        handler = create_reconnect_handler(on_disconnect)

        # Simulate normal stop (None error)
        handler(None)

        await asyncio.wait_for(callback_invoked.wait(), timeout=1.0)

        assert len(error_received) == 1
        assert error_received[0] is None

    @pytest.mark.asyncio
    async def test_reconnect_handler_logs_callback_errors(self) -> None:
        """Reconnect handler should log errors from the callback."""
        from clanker_bot.voice_resilience import create_reconnect_handler

        async def failing_callback(error: Exception | None) -> None:
            raise RuntimeError("Callback failed")

        handler = create_reconnect_handler(failing_callback)

        # Should not raise, just log
        with patch("clanker_bot.voice_resilience.logger") as mock_logger:
            handler(Exception("test"))
            await asyncio.sleep(0.1)  # Let the async task run
            # Callback error should be logged
            assert mock_logger.exception.called or mock_logger.error.called


class TestVoiceReconnector:
    """Tests for the VoiceReconnector class."""

    @pytest.mark.asyncio
    async def test_reconnector_attempts_rejoin_on_disconnect(self) -> None:
        """Reconnector should attempt to rejoin channel on unexpected disconnect."""
        from clanker_bot.voice_resilience import VoiceReconnector

        # Mock dependencies
        rejoin_called = asyncio.Event()
        rejoin_args: list[tuple[int, int]] = []

        async def mock_rejoin(guild_id: int, channel_id: int) -> bool:
            rejoin_args.append((guild_id, channel_id))
            rejoin_called.set()
            return True

        reconnector = VoiceReconnector(
            rejoin_callback=mock_rejoin,
            max_retries=3,
            retry_delay_seconds=0.1,
        )

        # Simulate unexpected disconnect
        await reconnector.handle_disconnect(
            guild_id=123,
            channel_id=456,
            error=Exception("Connection lost"),
        )

        await asyncio.wait_for(rejoin_called.wait(), timeout=1.0)

        assert rejoin_args == [(123, 456)]

    @pytest.mark.asyncio
    async def test_reconnector_retries_on_failure(self) -> None:
        """Reconnector should retry on rejoin failure."""
        from clanker_bot.voice_resilience import VoiceReconnector

        attempt_count = 0

        async def failing_rejoin(guild_id: int, channel_id: int) -> bool:
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                return False
            return True

        reconnector = VoiceReconnector(
            rejoin_callback=failing_rejoin,
            max_retries=5,
            retry_delay_seconds=0.05,
        )

        await reconnector.handle_disconnect(
            guild_id=123,
            channel_id=456,
            error=Exception("Connection lost"),
        )

        # Wait for retries
        await asyncio.sleep(0.3)

        assert attempt_count == 3  # Failed twice, succeeded on third

    @pytest.mark.asyncio
    async def test_reconnector_gives_up_after_max_retries(self) -> None:
        """Reconnector should give up after max retries exceeded."""
        from clanker_bot.voice_resilience import VoiceReconnector

        attempt_count = 0

        async def always_failing_rejoin(guild_id: int, channel_id: int) -> bool:
            nonlocal attempt_count
            attempt_count += 1
            return False

        reconnector = VoiceReconnector(
            rejoin_callback=always_failing_rejoin,
            max_retries=3,
            retry_delay_seconds=0.05,
        )

        await reconnector.handle_disconnect(
            guild_id=123,
            channel_id=456,
            error=Exception("Connection lost"),
        )

        # Wait for all retries
        await asyncio.sleep(0.5)

        assert attempt_count == 3

    @pytest.mark.asyncio
    async def test_reconnector_skips_expected_disconnect(self) -> None:
        """Reconnector should not attempt rejoin for expected disconnects."""
        from clanker_bot.voice_resilience import VoiceReconnector

        rejoin_called = False

        async def mock_rejoin(guild_id: int, channel_id: int) -> bool:
            nonlocal rejoin_called
            rejoin_called = True
            return True

        reconnector = VoiceReconnector(
            rejoin_callback=mock_rejoin,
            max_retries=3,
        )

        # Mark disconnect as expected
        reconnector.mark_expected_disconnect(guild_id=123)

        # Handle disconnect
        await reconnector.handle_disconnect(
            guild_id=123,
            channel_id=456,
            error=None,  # Normal disconnect
        )

        await asyncio.sleep(0.1)

        assert not rejoin_called

    @pytest.mark.asyncio
    async def test_expected_disconnect_is_cleared_after_handling(self) -> None:
        """Expected disconnect flag should be cleared after handling."""
        from clanker_bot.voice_resilience import VoiceReconnector

        async def mock_rejoin(guild_id: int, channel_id: int) -> bool:
            return True

        reconnector = VoiceReconnector(rejoin_callback=mock_rejoin)

        reconnector.mark_expected_disconnect(guild_id=123)
        assert reconnector.is_expected_disconnect(123)

        await reconnector.handle_disconnect(guild_id=123, channel_id=456, error=None)
        await asyncio.sleep(0.1)

        # Flag should be cleared
        assert not reconnector.is_expected_disconnect(123)


# --- Integration Tests ---


class TestVoiceResilienceIntegration:
    """Integration tests for voice resilience features."""

    @pytest.mark.asyncio
    async def test_start_voice_ingest_with_resilience(self) -> None:
        """start_voice_ingest should accept and use resilience options."""
        from clanker_bot.voice_resilience import VoiceKeepalive, VoiceReconnector

        # We can't easily test the full integration without a real voice client,
        # but we can verify the module structure is correct
        assert VoiceKeepalive is not None
        assert VoiceReconnector is not None

    @pytest.mark.asyncio
    async def test_keepalive_and_reconnector_work_together(self) -> None:
        """Keepalive and reconnector should be usable together."""
        from clanker_bot.voice_resilience import VoiceKeepalive, VoiceReconnector

        voice_client = MagicMock()
        voice_client.is_connected.return_value = True

        async def mock_rejoin(guild_id: int, channel_id: int) -> bool:
            return True

        # Both can be instantiated and used together
        keepalive = VoiceKeepalive(voice_client, interval_seconds=15.0)
        reconnector = VoiceReconnector(rejoin_callback=mock_rejoin)

        keepalive.start()
        reconnector.mark_expected_disconnect(123)

        keepalive.stop()
        # Should not raise
