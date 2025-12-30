# Voice Disconnect Investigation

Investigation into silent voice transcription failures during long-running Discord voice sessions.

## Problem Statement

During extended voice channel sessions, voice transcription silently stops working. The bot remains in the voice channel but no longer captures or transcribes audio. Users only discover this when they request `/transcript` and receive empty results, or when `/shitpost` commands fail to include voice context.

## Investigation Timeline

### Session Details
- **Date**: 2025-12-29
- **Session Duration**: ~14 minutes of active transcription
- **Total Transcripts Captured**: 86 events
- **Failure Time**: 23:55:07 UTC

### Event Sequence

| Time | Event | Details |
|------|-------|---------|
| 23:41:18 | Bot started | Voice providers initialized |
| 23:41:23 | Commands synced | 9 slash commands registered |
| 23:41:27 | Joined voice channel | `voice_recv` sink started |
| 23:41:27 - 23:55:01 | Active transcription | 86 transcripts captured successfully |
| 23:55:01 | Last transcript | `total_events=44` in buffer |
| 23:55:07 | **Processing stopped** | `voice_sink.processing_stopped` from `audioreader-stopper-*` thread |
| 23:55:08 | Process loop stopped | Clean shutdown of processing loop |
| 00:05:54 | User ran `/transcript` | `event_count=0` (all events expired from 5-min buffer) |
| 00:30:59 | Nudge session ended | Bot still connected but not listening |

### Key Log Entries

```
23:55:01 | transcript_buffer.add: total_events=44
23:55:07 | voice_sink.processing_stopped  [thread: audioreader-stopper-ffff60bccf20]
23:55:08 | voice_sink.process_loop_stopped
```

The critical indicator is the thread name `audioreader-stopper-*` - this is an internal `discord-ext-voice-recv` cleanup thread, not our code initiating the stop.

## Root Cause Analysis

### Hypotheses Evaluated

| Hypothesis | Evidence | Verdict |
|------------|----------|---------|
| TranscriptBuffer filled up | Buffer was at 44/50, never hit limit | **Ruled out** |
| User ran `/leave` command | No `/leave` in logs | **Ruled out** |
| Auto-leave triggered | No auto-leave events logged | **Ruled out** |
| Callback exception | Would be logged, wouldn't stop audio reader | **Ruled out** |
| Network/Discord disconnect | `audioreader-stopper` thread initiated stop | **Most likely** |

### Conclusion

The voice audio reader (managed by `discord-ext-voice-recv`) detected a connection loss and performed cleanup. This was likely caused by:

1. **Network hiccup** - Momentary connection loss to Discord voice servers
2. **Discord server-side disconnect** - Voice gateway timeout or server migration
3. **Voice gateway timeout** - Keepalive failure

The bot process continued running, but the voice receive pipeline silently stopped. No reconnection was attempted.

## Architecture Context

### Current Voice Pipeline

```
Discord Voice Server
        │
        ▼
discord-ext-voice-recv (VoiceRecvClient)
        │
        ├─► AudioReader thread (receives packets)
        │         │
        │         ▼ [FAILURE POINT - thread stops here]
        │
        ▼
VoiceIngestSink.write()
        │
        ▼
VoiceIngestWorker (VAD + STT)
        │
        ▼
TranscriptBuffer.add()
```

### Missing Components

1. **No disconnect detection** - We don't know when `voice_recv` stops
2. **No reconnection logic** - Once stopped, stays stopped
3. **No health monitoring** - Can't detect stale connections

## Comparison: Sparky's Approach

Sparky (reference implementation) handles this with a `CustomVoiceClient`:

### Key Differences

| Feature | Sparky | Clanker |
|---------|--------|---------|
| Voice library | Custom patched `VoiceClient` | `discord-ext-voice-recv` |
| Retry logic | Up to 3 retries on failure | None |
| Disconnection handling | Waits and retries if `not is_connected()` | Stops immediately |
| Error handling | Catches OSError, CryptoError, broad Exception | Library handles internally |

### Sparky's Retry Pattern

```python
class CustomVoiceClient(VoiceClient):
    _retry_attempts: int = 0

    def recv_audio(self, sink, callback, *args):
        exited_on_failure = False

        while self.recording:
            if not self.is_connected():
                time.sleep(0.1)
                continue  # Wait for reconnection

            try:
                data = self.socket.recv(4096)
                self.unpack_audio(data)
            except OSError as oe:
                if self.recording:
                    exited_on_failure = True
                    self.stop_recording()
            except CryptoError:
                continue  # Ignore crypto errors

        # Retry on unexpected exit
        if exited_on_failure:
            self._retry_attempts += 1
            if self._retry_attempts < 3:
                self.start_recording(sink, callback, *args)
                return
```

## Potential Solutions

### Option 1: Enhanced Logging (Low effort, diagnostic)

Add logging to understand failure modes better before implementing fixes.

**Changes:**
- Log when `stop_processing()` is called with context (expected vs unexpected)
- Add periodic health logging for voice connection state
- Log voice client `is_connected()` status in process loop

**Pros:**
- Quick to implement
- Helps diagnose root cause patterns
- No behavior change risk

**Cons:**
- Doesn't fix the problem
- Users still experience failures

### Option 2: Voice State Monitoring + Reconnection (Medium effort)

Monitor voice state changes and attempt to reconnect when unexpected disconnects occur.

**Changes:**
- Track "expected" disconnects (user ran `/leave`) vs unexpected
- In `on_voice_state_update`, detect when bot loses voice connection unexpectedly
- Attempt to rejoin the same channel and restart listening
- Add configurable retry limit (e.g., 3 attempts)

**Implementation sketch:**
```python
class VoiceSessionManager:
    expected_disconnects: set[int] = set()  # guild_ids expecting disconnect

    def mark_leaving(self, guild_id: int) -> None:
        """Mark that we're intentionally leaving."""
        self.expected_disconnects.add(guild_id)

    async def handle_unexpected_disconnect(
        self, guild_id: int, channel_id: int
    ) -> None:
        """Attempt to rejoin after unexpected disconnect."""
        if guild_id in self.expected_disconnects:
            self.expected_disconnects.discard(guild_id)
            return

        # Unexpected disconnect - attempt rejoin
        logger.warning("voice.unexpected_disconnect", guild=guild_id)
        # ... rejoin logic with retry
```

**Pros:**
- Handles the most common failure case
- Works with existing `discord-ext-voice-recv` library
- Non-invasive to current architecture

**Cons:**
- Doesn't handle all edge cases (e.g., network still down on retry)
- May cause brief audio gaps during reconnection

### Option 3: Custom Voice Client (High effort, robust)

Fork or patch `discord-ext-voice-recv` to add Sparky-style retry logic.

**Changes:**
- Create `CustomVoiceRecvClient` extending `VoiceRecvClient`
- Override audio receive loop with error handling and retry logic
- Add connection health checks within the receive loop

**Pros:**
- Most robust solution
- Handles errors at the source
- Can implement sophisticated retry strategies

**Cons:**
- Significant development effort
- Must maintain fork/patch
- Risk of breaking with library updates

### Option 4: Periodic Health Check + Proactive Reconnection (Medium effort)

Add a background task that periodically verifies voice connection health.

**Changes:**
- Background task runs every 30-60 seconds
- Checks if bot should be in voice (has active session) but isn't receiving audio
- Proactively reconnects before users notice

**Implementation sketch:**
```python
async def voice_health_monitor(self):
    while True:
        await asyncio.sleep(60)
        for guild_id, session in self.active_sessions.items():
            if session.should_be_listening and not session.receiving_audio:
                logger.warning("voice.stale_connection_detected", guild=guild_id)
                await self.reconnect(guild_id)
```

**Pros:**
- Catches failures even when no audio is expected
- Can detect "zombie" connections
- Proactive rather than reactive

**Cons:**
- Adds background task complexity
- May reconnect unnecessarily in quiet channels
- Requires tracking "should be listening" state

## Recommended Approach

**Phase 1: Logging (Immediate)**
- Add diagnostic logging to understand failure patterns
- Track how often this happens and under what conditions

**Phase 2: Voice State Reconnection (Short-term)**
- Implement Option 2 (voice state monitoring + reconnection)
- Covers the most common failure case with moderate effort

**Phase 3: Health Monitoring (If needed)**
- If Phase 2 doesn't catch all cases, add periodic health checks
- Only implement if logging shows failures not caught by voice state changes

---

## Implementation (2025-12-29)

Based on external research of discord.py best practices and the `discord-ext-voice-recv` library, a revised approach was implemented combining two strategies:

### Strategy A: Silence Keepalive (Preventive)

Discord's load balancer disconnects idle voice clients every 15 minutes to 2 hours. Sending Opus silence frames (`b'\xf8\xff\xfe'`) every 15 seconds prevents this.

**Implementation**: `VoiceKeepalive` class in `voice_resilience.py`
- Runs as background task after joining voice
- Automatically stops when voice client disconnects
- Handles send errors gracefully

### Strategy B: After Callback Reconnection (Reactive)

The `discord-ext-voice-recv` library's `listen()` method accepts an `after` callback that fires when the audio sink stops (due to error or exhaustion). This is the hook for reconnection logic.

**Implementation**: `VoiceReconnector` class in `voice_resilience.py`
- Tracks expected vs unexpected disconnects
- On unexpected disconnect, attempts to rejoin with configurable retries
- Uses `create_reconnect_handler()` to bridge sync callback to async reconnection logic

### Key Changes

| File | Changes |
|------|---------|
| `src/clanker_bot/voice_resilience.py` | **New file**: `VoiceKeepalive`, `VoiceReconnector`, `create_reconnect_handler()` |
| `src/clanker_bot/voice_ingest.py` | Added `VoiceIngestSession` dataclass, updated `start_voice_ingest()` to enable keepalive and accept `on_disconnect` callback |
| `src/clanker_bot/discord_adapter.py` | Enhanced `VoiceSessionManager` with reconnector support and `clear_state()` method |
| `src/clanker_bot/command_handlers/voice.py` | Wired up disconnect handler in `_setup_transcription()` |
| `src/clanker_bot/main.py` | Set up `VoiceReconnector` with rejoin callback in `build_bot()` |
| `tests/test_voice_resilience.py` | **New file**: 14 tests for resilience features |

### Usage Flow

1. Bot joins voice channel via `/join` command
2. `start_voice_ingest()` starts listening with:
   - `VoiceKeepalive` sending silence packets every 15s
   - `after` callback connected to `VoiceReconnector`
3. If connection drops unexpectedly:
   - `after` callback fires
   - `VoiceReconnector.handle_disconnect()` attempts rejoin with 3 retries
4. If `/leave` command runs:
   - `VoiceSessionManager.leave()` marks disconnect as expected
   - `VoiceReconnector` skips reconnection attempt

### External References

Research sources that informed this implementation:
- [discord.py Discussion #9722](https://github.com/Rapptz/discord.py/discussions/9722) - Random disconnects are normal (load balancing), keepalive packets help
- [discord.py Issue #9511](https://github.com/Rapptz/discord.py/issues/9511) - Voice connection code improvements
- [discord-ext-voice-recv](https://github.com/imayhaveborkedit/discord-ext-voice-recv) - `after` callback in `listen()` method

---

## Related Files

| File | Purpose |
|------|---------|
| `src/clanker_bot/voice_ingest.py` | Voice receive sink and processing |
| `src/clanker_bot/voice_resilience.py` | Keepalive and reconnection utilities |
| `src/clanker_bot/command_handlers/voice.py` | `/join`, `/leave` handlers |
| `src/clanker_bot/discord_adapter.py` | VoiceSessionManager |
| `src/clanker_bot/cogs/vc_monitor.py` | Voice state monitoring (auto-leave, nudge) |

## References

- [discord-ext-voice-recv documentation](https://github.com/imayhaveborkedit/discord-ext-voice-recv)
- Sparky codebase: `sparky/patched/voice_client.py` (CustomVoiceClient with retry logic)
