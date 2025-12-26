# Bug Fix Implementation Plan

**Date**: 2025-12-26
**Scope**: All issues from FUTURE_WORK.md (2025.12.26 section)

---

## Executive Summary

| Priority | Bug | Complexity | Estimated LOC |
|----------|-----|------------|---------------|
| P0 | Voice ingest missing abstract methods | Low | ~10 |
| P0 | Dismiss button "empty message" error | Low | ~5 |
| P1 | Shitpost preview not showing image | Medium | ~15 |
| P1 | Post button only sends text, no image | Low | Already works? |
| P1 | /chat auto-reply in threads | Medium-High | ~80 |
| P2 | Regenerate lacks UX feedback | Low | ~10 |
| P2 | Shitpost ignoring bot messages | Low | ~5 |
| P2 | /speak command disabled | Low | ~10 |
| P3 | Add /transcript command | Medium | ~50 |
| P3 | Voice-text channel shitpost logic | Medium | ~30 |
| P3 | VC join/leave default messages | Low | ~10 |
| P3 | VC monitoring nudge | High | ~100 |

---

## TDD Approach & Testing Philosophy

**Core Principles** (from skills):
1. **Write tests FIRST** - Red-Green-Refactor cycle
2. **Prefer fakes over mocks** - Use `FakeLLM`, `FakeSTT`, etc. from `tests/fakes.py`
3. **One behavior per test** - Name: `test_unit_scenario_result`
4. **Arrange-Act-Assert** structure
5. **Observable behavior, not implementation** - Test what it does, not how

**Anti-patterns to AVOID**:
- Silent failures - raise loud errors instead
- `Dict[str, Any]` - use dataclasses
- Inline imports/functions - all at module level
- Heavy mocking - use fakes aligned with production code
- String assertions - test behavior

**Existing Test Infrastructure**:
- Provider fakes: `FakeLLM`, `FakeSTT`, `FakeTTS`, `FakeImage` in `tests/fakes.py`
- Discord fakes: `FakeInteraction`, `FakeChannel`, `FakeThread`, `FakeHistoryIterator` in `tests/conftest.py`
- Fixtures: `persona`, `context`, `fake_interaction`

---

## Test Specifications (Write These FIRST)

### 1.1 VoiceIngestSink Tests

**New file**: `tests/test_voice_ingest.py`

```python
"""Tests for voice ingest sink."""
import asyncio
import pytest
from clanker_bot.voice_ingest import VoiceIngestSink, VoiceIngestWorker
from tests.fakes import FakeSTT


class TestVoiceIngestSink:
    """Test VoiceIngestSink abstract method implementations."""

    @pytest.fixture
    def worker(self) -> VoiceIngestWorker:
        return VoiceIngestWorker(stt=FakeSTT())

    @pytest.fixture
    def sink(self, worker: VoiceIngestWorker) -> VoiceIngestSink:
        return VoiceIngestSink(worker)

    def test_wants_opus_returns_false(self, sink: VoiceIngestSink) -> None:
        """Sink should request PCM, not Opus-encoded audio."""
        assert sink.wants_opus() is False

    def test_cleanup_cancels_pending_tasks(self, sink: VoiceIngestSink) -> None:
        """Cleanup should cancel all pending processing tasks."""
        # Arrange: add some fake tasks
        task1 = asyncio.create_task(asyncio.sleep(100))
        task2 = asyncio.create_task(asyncio.sleep(100))
        sink._tasks.add(task1)
        sink._tasks.add(task2)

        # Act
        sink.cleanup()

        # Assert
        assert len(sink._tasks) == 0
        assert task1.cancelled()
        assert task2.cancelled()

    def test_cleanup_handles_empty_tasks(self, sink: VoiceIngestSink) -> None:
        """Cleanup should handle case with no pending tasks."""
        sink.cleanup()  # Should not raise
        assert len(sink._tasks) == 0

    def test_sink_can_be_instantiated(self, worker: VoiceIngestWorker) -> None:
        """Sink should be instantiable (not abstract)."""
        sink = VoiceIngestSink(worker)
        assert sink is not None
```

---

### 1.2 Dismiss Button Tests

**Add to**: `tests/test_shitpost_preview.py`

```python
"""Tests for shitpost preview view."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from clanker_bot.views.shitpost_preview import ShitpostPreviewView, MemePayload


class TestShitpostPreviewDismiss:
    """Test dismiss button behavior."""

    @pytest.fixture
    def payload(self) -> MemePayload:
        return MemePayload(text="Test meme", image_bytes=b"fake_image")

    @pytest.fixture
    def view(self, payload: MemePayload) -> ShitpostPreviewView:
        import discord
        embed = discord.Embed(title="Test")
        return ShitpostPreviewView(
            invoker_id=123,
            payload=payload,
            embed=embed,
        )

    @pytest.fixture
    def mock_interaction(self) -> MagicMock:
        interaction = MagicMock()
        interaction.user.id = 123
        interaction.response.edit_message = AsyncMock()
        return interaction

    @pytest.mark.asyncio
    async def test_dismiss_provides_content(
        self, view: ShitpostPreviewView, mock_interaction: MagicMock
    ) -> None:
        """Dismiss should provide non-empty content to avoid Discord API error."""
        button = MagicMock()

        await view.dismiss_button(mock_interaction, button)

        # Assert edit_message was called with non-None content
        call_kwargs = mock_interaction.response.edit_message.call_args.kwargs
        assert call_kwargs.get("content") is not None
        assert len(call_kwargs["content"]) > 0

    @pytest.mark.asyncio
    async def test_dismiss_clears_embed_and_view(
        self, view: ShitpostPreviewView, mock_interaction: MagicMock
    ) -> None:
        """Dismiss should clear embed, attachments, and view."""
        button = MagicMock()

        await view.dismiss_button(mock_interaction, button)

        call_kwargs = mock_interaction.response.edit_message.call_args.kwargs
        assert call_kwargs.get("embed") is None
        assert call_kwargs.get("attachments") == []
        assert call_kwargs.get("view") is None
```

---

### 3.x Thread Chat Tests

**New file**: `tests/test_thread_chat.py`

```python
"""Tests for thread auto-reply functionality."""
import pytest
from dataclasses import dataclass
from clanker.models import Message
from clanker_bot.command_handlers.common import is_clanker_thread, CLANKER_THREAD_PATTERN


class TestIsClankerThread:
    """Test thread detection helper."""

    def test_matches_valid_clanker_thread_name(self) -> None:
        """Should match clanker-{6 hex chars} pattern."""
        assert CLANKER_THREAD_PATTERN.match("clanker-abc123")
        assert CLANKER_THREAD_PATTERN.match("clanker-000000")
        assert CLANKER_THREAD_PATTERN.match("clanker-ffffff")

    def test_rejects_invalid_thread_names(self) -> None:
        """Should reject non-matching names."""
        assert not CLANKER_THREAD_PATTERN.match("clanker-abc")  # Too short
        assert not CLANKER_THREAD_PATTERN.match("clanker-abc1234")  # Too long
        assert not CLANKER_THREAD_PATTERN.match("clanker-ABCDEF")  # Uppercase
        assert not CLANKER_THREAD_PATTERN.match("other-thread")
        assert not CLANKER_THREAD_PATTERN.match("clanker-ghijkl")  # Not hex

    def test_is_clanker_thread_with_thread_object(self) -> None:
        """Should return True for Thread with matching name."""
        @dataclass
        class FakeThread:
            name: str

        thread = FakeThread(name="clanker-abc123")
        # Note: is_clanker_thread checks isinstance(channel, discord.Thread)
        # For unit test, we test the pattern directly
        assert CLANKER_THREAD_PATTERN.match(thread.name)

    def test_is_clanker_thread_with_non_thread(self) -> None:
        """Should return False for non-Thread objects."""
        assert is_clanker_thread(None) is False
        assert is_clanker_thread("clanker-abc123") is False  # String, not Thread


class TestFetchThreadHistory:
    """Test thread history fetching."""

    @pytest.fixture
    def fake_thread_messages(self) -> list:
        """Create fake message history."""
        from tests.conftest import FakeMessage, FakeAuthor

        return [
            FakeMessage(content="Hello", author=FakeAuthor(display_name="Alice", bot=False)),
            FakeMessage(content="Hi there!", author=FakeAuthor(display_name="Bot", bot=True)),
            FakeMessage(content="How are you?", author=FakeAuthor(display_name="Bob", bot=False)),
        ]

    @pytest.mark.asyncio
    async def test_history_returns_messages_in_chronological_order(
        self, fake_thread_messages: list
    ) -> None:
        """History should return oldest-first."""
        # This will be implemented when we have the real function
        # For now, document the expected behavior
        pass

    @pytest.mark.asyncio
    async def test_history_labels_bot_messages_as_assistant(
        self, fake_thread_messages: list
    ) -> None:
        """Bot's own messages should have role='assistant'."""
        pass

    @pytest.mark.asyncio
    async def test_history_includes_username_for_user_messages(
        self, fake_thread_messages: list
    ) -> None:
        """User messages should include display_name prefix."""
        pass

    @pytest.mark.asyncio
    async def test_history_skips_empty_messages(self) -> None:
        """Empty/whitespace-only messages should be skipped."""
        pass


class TestHandleThreadMessage:
    """Test thread message handler."""

    @pytest.mark.asyncio
    async def test_responds_with_llm_reply(self) -> None:
        """Should call LLM and send response to thread."""
        pass

    @pytest.mark.asyncio
    async def test_includes_full_history_in_context(self) -> None:
        """Context should include all thread messages, not just latest."""
        pass

    @pytest.mark.asyncio
    async def test_shows_typing_indicator(self) -> None:
        """Should show typing indicator while processing."""
        pass

    @pytest.mark.asyncio
    async def test_handles_llm_error_gracefully(self) -> None:
        """Should send error message to thread on failure."""
        pass
```

---

### Shitpost Preview Image Tests

**Add to**: `tests/test_shitpost_preview.py`

```python
class TestShitpostPreviewImage:
    """Test image handling in preview."""

    @pytest.mark.asyncio
    async def test_preview_includes_image_when_available(self) -> None:
        """Preview should attach image file when payload has image_bytes."""
        pass

    @pytest.mark.asyncio
    async def test_preview_shows_text_fallback_when_no_image(self) -> None:
        """Preview should show text in embed when no image available."""
        pass

    @pytest.mark.asyncio
    async def test_post_sends_image_to_channel(self) -> None:
        """Post button should send image file to channel."""
        pass


class TestShitpostRegenerateUX:
    """Test regenerate button UX."""

    @pytest.mark.asyncio
    async def test_regenerate_shows_loading_state(self) -> None:
        """Should show 'Regenerating...' message during generation."""
        pass

    @pytest.mark.asyncio
    async def test_regenerate_disables_buttons_during_generation(self) -> None:
        """Should disable buttons while regenerating."""
        pass

    @pytest.mark.asyncio
    async def test_regenerate_restores_buttons_on_error(self) -> None:
        """Should re-enable buttons if regeneration fails."""
        pass
```

---

## Phase 1: Critical Fixes (Blocking Issues)

### 1.1 VoiceIngestSink Missing Abstract Methods

**File**: `src/clanker_bot/voice_ingest.py`
**Line**: 135

**Root Cause**: `VoiceIngestSink` extends `voice_recv.AudioSink` but doesn't implement required abstract methods `wants_opus()` and `cleanup()`.

**Fix**:
```python
class VoiceIngestSink(voice_recv.AudioSink):
    """voice_recv sink that forwards PCM frames to the worker."""

    # ... existing __init__ ...

    def wants_opus(self) -> bool:
        """Return False: we want decoded PCM, not Opus."""
        return False

    def cleanup(self) -> None:
        """Cancel pending processing tasks."""
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()

    # ... existing write(), _flush() ...
```

**Validation**:
```bash
# Unit test
uv run pytest tests/test_voice_ingest.py -v

# Integration test (requires running bot)
# 1. Start bot
# 2. Join voice channel with /join
# 3. Verify no TypeError in logs
```

---

### 1.2 Dismiss Button "Empty Message" Error

**File**: `src/clanker_bot/views/shitpost_preview.py`
**Line**: 191-196

**Root Cause**: Discord API rejects `edit_message` with all-None content. Need to provide *something*.

**Current Code**:
```python
await interaction.response.edit_message(
    content=None,
    embed=None,
    attachments=[],
    view=None,
)
```

**Fix**:
```python
await interaction.response.edit_message(
    content="*Preview dismissed*",  # Or use zero-width space: "\u200b"
    embed=None,
    attachments=[],
    view=None,
)
```

**Alternative** (delete instead of edit):
```python
# Ephemeral messages can't be deleted via API, but we can try:
try:
    await interaction.message.delete()
except discord.NotFound:
    # Message already gone
    pass
except discord.HTTPException:
    # Fallback to edit
    await interaction.response.edit_message(
        content="*Dismissed*",
        embed=None,
        attachments=[],
        view=None,
    )
```

**Validation**:
```bash
# Manual test
# 1. Run /shitpost
# 2. Click Dismiss
# 3. Verify no error, message shows "Preview dismissed" or disappears
```

---

## Phase 2: Shitpost Flow Fixes

### 2.1 Preview Not Showing Meme Image

**File**: `src/clanker_bot/command_handlers/chat.py`
**Line**: 217-222

**Root Cause Analysis**: The embed is created with just a title, and the image is set via `embed.set_image(url="attachment://meme.png")` in `_send_preview()`. However, looking at the code, this *should* work...

**Hypothesis**: The `deps.image` provider might not be configured, or is returning `None`.

**Debug Steps**:
```python
# Add logging in _generate_single_meme()
logger.info(
    "meme.image_generation",
    has_image_provider=deps.image is not None,
    image_bytes_len=len(image_bytes) if image_bytes else 0,
    template_id=meme_template.template_id,
)
```

**Possible Fix** (if image provider is missing):
```python
# In _send_preview(), add the caption to embed if no image
if payload.image_bytes:
    file = discord.File(fp=BytesIO(payload.image_bytes), filename="meme.png")
    embed.set_image(url="attachment://meme.png")
    await interaction.followup.send(embed=embed, file=file, view=view, ephemeral=True)
else:
    embed.description = f"**{payload.text}**"  # Show text in embed
    await interaction.followup.send(embed=embed, view=view, ephemeral=True)
```

**Real Fix** (ensure image provider is configured):
Check `BotDependencies` initialization - is `deps.image` being set to a `MemegenImage` instance?

**Validation**:
```bash
# Use test script
uv run python scripts/test_meme_pipeline.py --verbose

# Check logs for image generation
# Look for: "meme.image_generation" log entries
```

---

### 2.2 Post Button Only Sends Text

**File**: `src/clanker_bot/views/shitpost_preview.py`
**Line**: 115-120

**Current Code**:
```python
file = self._build_file()
if file:
    await channel.send(content=self.payload.text, file=file)
else:
    await channel.send(content=self.payload.text)
```

**Analysis**: This code looks correct. The issue is likely upstream - if `payload.image_bytes` is None (from 2.1), then `_build_file()` returns None.

**Fix**: Same as 2.1 - ensure image provider is working.

---

### 2.3 Regenerate UX Feedback

**File**: `src/clanker_bot/views/shitpost_preview.py`
**Line**: 164-168

**Current Code**:
```python
await interaction.response.defer()
# ... regenerate ...
await self._update_preview(interaction, new_payload, new_embed)
```

**Issue**: No visual feedback during regeneration.

**Fix**:
```python
@discord.ui.button(label="Regenerate", style=discord.ButtonStyle.secondary, emoji="🔄")
async def regenerate_button(...) -> None:
    # ... validation checks ...

    # Show "regenerating" state
    await interaction.response.edit_message(
        embed=discord.Embed(
            title="Regenerating...",
            description="Generating a new meme with a different template.",
            color=discord.Color.yellow(),
        ),
        attachments=[],
        view=None,  # Disable buttons during regen
    )

    try:
        new_payload, new_embed = await self.regenerate_callback()
        # Re-enable view and show new meme
        await self._update_preview(interaction, new_payload, new_embed)
        # ... logging ...
    except Exception as e:
        # Show error state
        await interaction.edit_original_response(
            embed=discord.Embed(
                title="Regeneration Failed",
                description=str(e),
                color=discord.Color.red(),
            ),
            view=self,  # Re-enable buttons
        )
```

**Validation**:
```bash
# Manual test
# 1. Run /shitpost
# 2. Click Regenerate
# 3. Verify "Regenerating..." message appears
# 4. Verify new meme replaces the message
```

---

### 2.4 Shitpost Context Should Ignore Bot Messages

**File**: `src/clanker_bot/command_handlers/chat.py`
**Line**: 117-119

**Current Code**:
```python
async for msg in channel.history(limit=limit):
    if msg.author.bot:
        continue  # Already filtering bots!
```

**Analysis**: Bot messages are already filtered. The issue might be with embeds or other content types.

**Enhanced Fix**:
```python
async for msg in channel.history(limit=limit):
    if msg.author.bot:
        continue
    if not msg.content.strip():
        continue
    # Also skip messages that are just embeds/attachments
    if msg.content.startswith("/"):  # Skip command invocations
        continue
    messages.append(...)
```

---

## Phase 3: Chat Thread Support (Auto-Reply in Threads)

### 3.1 Overview

**Current State**: Bot only responds to `/chat` slash command. No auto-reply in threads.

**Desired Flow**:
1. User runs `/chat "hello"` in a channel
2. Bot creates thread `clanker-abc123`, responds with LLM reply
3. User types a **regular message** in that thread (no slash command)
4. Bot automatically reads full thread history, calls LLM, responds

**Required Changes**:
1. Enable `message_content` intent
2. Track which threads the bot created (thread naming convention)
3. Add `on_message` event handler for thread auto-reply
4. Fetch thread history and build proper LLM context

---

### 3.2 Enable Message Content Intent

**File**: `src/clanker_bot/main.py`
**Line**: 101-103

**Current**:
```python
intents = discord.Intents.default()
intents.message_content = False
```

**Fix**:
```python
intents = discord.Intents.default()
intents.message_content = True  # Required to read thread messages
```

**Note**: This also requires enabling the "Message Content Intent" in Discord Developer Portal under Bot settings.

---

### 3.3 Thread Detection Strategy

Bot-created threads follow the naming pattern: `clanker-{6-hex-chars}`

**Helper function**:
```python
# In common.py
import re

CLANKER_THREAD_PATTERN = re.compile(r"^clanker-[a-f0-9]{6}$")

def is_clanker_thread(channel: discord.abc.GuildChannel | discord.Thread | None) -> bool:
    """Check if this is a thread created by the bot."""
    if not isinstance(channel, discord.Thread):
        return False
    return bool(CLANKER_THREAD_PATTERN.match(channel.name))
```

---

### 3.4 Add on_message Event Handler

**File**: `src/clanker_bot/main.py` (or new file `src/clanker_bot/listeners.py`)

**Add to build_bot()**:
```python
def build_bot(deps: BotDependencies) -> ClankerClient:
    """Create the Discord client and register commands."""
    intents = discord.Intents.default()
    intents.message_content = True  # Enable for thread reading
    bot = ClankerClient(intents=intents)
    register_commands(bot, deps)

    @bot.event
    async def on_ready() -> None:
        if bot.user:
            logger.info("Bot ready as {}", bot.user.name)
            await bot.tree.sync()
            logger.info("Command tree synced")

    @bot.event
    async def on_message(message: discord.Message) -> None:
        """Auto-reply in clanker threads."""
        # Ignore bot's own messages
        if message.author.bot:
            return

        # Ignore DMs
        if not message.guild:
            return

        # Only respond in clanker threads
        if not is_clanker_thread(message.channel):
            return

        # Ignore empty messages
        if not message.content.strip():
            return

        # Process the message
        await handle_thread_message(message, deps)

    return bot
```

---

### 3.5 Thread Message Handler

**New file**: `src/clanker_bot/command_handlers/thread_chat.py`

```python
"""Handler for automatic thread replies."""
from __future__ import annotations

import uuid

import discord
from loguru import logger

from clanker.models import Context, Message
from clanker.respond import respond

from .common import increment_metric
from .types import BotDependencies


async def _fetch_thread_history(
    thread: discord.Thread,
    limit: int = 20,
) -> list[Message]:
    """Fetch thread history as Message objects.

    Returns messages in chronological order (oldest first).
    Properly labels bot messages as 'assistant' role.
    """
    messages: list[Message] = []
    bot_id = thread.guild.me.id if thread.guild.me else None

    async for msg in thread.history(limit=limit):
        if not msg.content.strip():
            continue

        # Determine role based on author
        if msg.author.bot and msg.author.id == bot_id:
            role = "assistant"
            content = msg.content
        else:
            role = "user"
            # Include username for multi-user context
            content = f"{msg.author.display_name}: {msg.content}"

        messages.append(Message(role=role, content=content))

    messages.reverse()  # Oldest first
    return messages


async def handle_thread_message(
    message: discord.Message,
    deps: BotDependencies,
) -> None:
    """Handle a regular message in a clanker thread."""
    thread = message.channel
    if not isinstance(thread, discord.Thread):
        return

    try:
        # Show typing indicator while processing
        async with thread.typing():
            # Fetch full thread history
            history = await _fetch_thread_history(thread, limit=20)

            # Build context
            context = Context(
                request_id=str(uuid.uuid4()),
                user_id=message.author.id,
                guild_id=message.guild.id if message.guild else None,
                channel_id=thread.id,
                persona=deps.persona,
                messages=history,
                metadata={"source": "discord", "trigger": "thread_message"},
            )

            increment_metric(deps, "thread_chat_requests")

            # Generate response
            reply, _audio = await respond(
                context,
                deps.llm,
                tts=None,
                replay_log_path=deps.replay_log_path,
            )

            # Send reply
            await thread.send(reply.content)

            logger.info(
                "thread_chat.replied",
                thread_id=thread.id,
                user_id=message.author.id,
                message_count=len(history),
            )

    except Exception as e:
        logger.opt(exception=True).error(
            "thread_chat.error",
            thread_id=thread.id,
            error=str(e),
        )
        # Optionally send error message to thread
        await thread.send("Sorry, I encountered an error processing that message.")
```

---

### 3.6 Update /chat Handler for Consistency

**File**: `src/clanker_bot/command_handlers/chat.py`

When `/chat` is used in an existing clanker thread, it should also read history:

```python
async def handle_chat(
    interaction: discord.Interaction,
    prompt: str,
    deps: BotDependencies,
) -> None:
    async def action() -> None:
        channel = interaction.channel

        # Build message list
        if is_clanker_thread(channel):
            # In existing thread: read history + add new prompt
            history = await _fetch_thread_history(channel, limit=20)
            # Add the new prompt (not yet in history since interaction hasn't replied)
            history.append(Message(
                role="user",
                content=f"{interaction.user.display_name}: {prompt}"
            ))
            all_messages = history
        else:
            # New conversation: just the prompt
            all_messages = [Message(role="user", content=prompt)]

        context = Context(
            request_id=str(uuid.uuid4()),
            user_id=interaction.user.id,
            guild_id=interaction.guild_id,
            channel_id=interaction.channel_id or 0,
            persona=deps.persona,
            messages=all_messages,
            metadata={"source": "discord"},
        )

        increment_metric(deps, "chat_requests")
        reply, _audio = await respond(context, deps.llm, tts=None, ...)
        await _send_reply(interaction, reply)

    await run_with_provider_handling(...)
```

---

### 3.7 Update _send_reply for Thread Awareness

```python
async def _send_reply(
    interaction: discord.Interaction,
    reply: Message,
    audio: bytes | None = None,
) -> None:
    """Send reply - to existing thread or create new one."""
    channel = interaction.channel

    # If already in a clanker thread, reply there directly
    if is_clanker_thread(channel):
        if audio:
            file = discord.File(fp=BytesIO(audio), filename="speech.mp3")
            await interaction.followup.send(reply.content, file=file)
        else:
            await interaction.followup.send(reply.content)
        return

    # Otherwise, create new thread
    thread = await ensure_thread(interaction)
    if thread:
        if audio:
            file = discord.File(fp=BytesIO(audio), filename="speech.mp3")
            await thread.send(reply.content, file=file)
        else:
            await thread.send(reply.content)
        await interaction.followup.send(f"See thread: {thread.mention}")
    else:
        # Fallback to channel
        if audio:
            file = discord.File(fp=BytesIO(audio), filename="speech.mp3")
            await interaction.followup.send(reply.content, file=file)
        else:
            await interaction.followup.send(reply.content)
```

---

### 3.8 Validation

**Unit Tests**:
```bash
uv run pytest tests/test_commands.py -k "chat" -v
uv run pytest tests/test_thread_chat.py -v  # New test file
```

**Manual Test Checklist**:
- [ ] Run `/chat "hello"` in text channel → creates thread, bot responds
- [ ] Type regular message in that thread → bot reads history, responds
- [ ] Type in a non-clanker thread → bot ignores
- [ ] Multiple users in thread → bot sees all messages with usernames
- [ ] Run `/chat` in existing clanker thread → bot reads history + new prompt

**Edge Cases**:
- [ ] Very long thread (>20 messages) → only recent history used
- [ ] Empty message in thread → ignored
- [ ] Bot's own messages → labeled as "assistant" role, not duplicated

---

## Phase 4: Voice Improvements

### 4.1 Disable /speak Command

**File**: `src/clanker_bot/commands.py`
**Line**: 47-57

**Fix**: Comment out or remove the /speak command registration:
```python
# TODO: Re-enable when TTS pipeline is ready
# @app_commands.describe(prompt="Prompt for Clanker")
# async def speak(interaction: discord.Interaction, prompt: str) -> None:
#     await handle_speak(interaction, prompt, deps)
#
# tree.add_command(
#     app_commands.Command(
#         name="speak",
#         description="Chat with TTS response",
#         callback=speak,
#     )
# )
```

---

### 4.2 Add /transcript Debug Command

**New File**: `src/clanker_bot/command_handlers/transcript.py`

```python
"""Transcript debug command handler."""
from __future__ import annotations

import discord
from loguru import logger

from .common import increment_metric
from .types import BotDependencies


async def handle_transcript(
    interaction: discord.Interaction,
    deps: BotDependencies,
) -> None:
    """Show recent voice transcripts for debugging."""
    await interaction.response.defer(ephemeral=True)

    guild_id = interaction.guild_id
    if not guild_id:
        await interaction.followup.send("Not in a guild.", ephemeral=True)
        return

    if not deps.transcript_buffer:
        await interaction.followup.send("Transcript buffer not available.", ephemeral=True)
        return

    events = deps.transcript_buffer.get(guild_id)
    if not events:
        await interaction.followup.send(
            "No recent transcripts. Use `/join` first to start voice capture.",
            ephemeral=True
        )
        return

    increment_metric(deps, "transcript_requests")

    # Format transcripts
    lines = []
    for event in events[-10:]:  # Last 10
        timestamp = event.start_time.strftime("%H:%M:%S")
        speaker = f"<@{event.speaker_id}>" if event.speaker_id else "Unknown"
        lines.append(f"`{timestamp}` {speaker}: {event.text}")

    embed = discord.Embed(
        title="Recent Voice Transcripts",
        description="\n".join(lines) or "No transcripts",
        color=discord.Color.blue(),
    )
    embed.set_footer(text=f"{len(events)} total events in buffer")

    await interaction.followup.send(embed=embed, ephemeral=True)
    logger.info("transcript.displayed", guild_id=guild_id, event_count=len(events))
```

**Register in commands.py**:
```python
from .command_handlers import handle_transcript

async def transcript(interaction: discord.Interaction) -> None:
    await handle_transcript(interaction, deps)

tree.add_command(
    app_commands.Command(
        name="transcript",
        description="Show recent voice transcripts (debug)",
        callback=transcript,
    )
)
```

---

### 4.3 Voice-Associated Text Channel Logic

**File**: `src/clanker_bot/command_handlers/chat.py`

**Requirement**: If shitpost is run in a voice channel's text chat but no recent transcripts, prompt user to /join first.

**Fix in _build_shitpost_context()**:
```python
async def _build_shitpost_context(
    interaction: discord.Interaction,
    guidance: str | None,
    deps: BotDependencies,
) -> ShitpostContext | None:  # Return None if voice channel requires /join
    """Build ShitpostContext from voice transcript or channel history."""
    transcript_utterances, channel_type = _get_voice_context(interaction.guild_id, deps)

    # Check if this is a voice channel's text chat
    channel = interaction.channel
    is_voice_text_channel = (
        hasattr(channel, "category") and
        channel.category and
        any(vc.name == channel.name for vc in channel.category.voice_channels if hasattr(channel.category, "voice_channels"))
    )

    # If voice text channel but no transcripts, require /join
    if is_voice_text_channel and not transcript_utterances:
        return None  # Signal that /join is required

    # ... rest of existing logic ...
```

**Update handle_shitpost_preview()**:
```python
shitpost_context = await _build_shitpost_context(interaction, guidance, deps)
if shitpost_context is None:
    await interaction.followup.send(
        "This appears to be a voice channel's text chat. "
        "Use `/join` first to start voice capture, then try `/shitpost` again.",
        ephemeral=True
    )
    return
```

---

### 4.4 Default Join/Leave Messages

**File**: `src/clanker_bot/command_handlers/voice.py`

**Add constants**:
```python
JOIN_MESSAGES = [
    "I'm here and ready to generate some quality shitposts! Use `/shitpost` after some conversation.",
    "Joined! Talk amongst yourselves - I'll be listening for meme material.",
    "Ready to capture the chaos. Use `/shitpost` when the moment is right.",
]

LEAVE_MESSAGES = [
    "Peace out! Your transcripts have been preserved for future shitposting.",
    "Leaving, but the memes will live on.",
    "Gone but not forgotten. `/shitpost` still works with recent transcripts!",
]
```

**Use in handlers**:
```python
import random

async def handle_join(...):
    # ... existing join logic ...
    message = random.choice(JOIN_MESSAGES)
    await interaction.followup.send(message)

async def handle_leave(...):
    # ... existing leave logic ...
    message = random.choice(LEAVE_MESSAGES)
    await interaction.followup.send(message)
```

---

## Phase 5: Validation Strategy

### Unit Tests

```bash
# Run all tests
make test

# Specific test files
uv run pytest tests/test_voice_ingest.py -v       # Voice sink fixes
uv run pytest tests/test_commands.py -v           # Command handlers
uv run pytest tests/test_meme_pipeline.py -v      # Meme generation
```

### Integration Tests (Manual)

Create a test checklist:

```markdown
## Manual Test Checklist

### Voice Pipeline
- [ ] /join works without TypeError
- [ ] Voice transcripts appear in logs
- [ ] /leave works and shows message
- [ ] /transcript shows recent transcripts

### Shitpost Flow
- [ ] /shitpost shows image preview (not just embed)
- [ ] Dismiss button clears preview (no error)
- [ ] Regenerate shows "Regenerating..." feedback
- [ ] Post sends image to channel
- [ ] Bot messages excluded from context

### Chat Flow
- [ ] /chat in channel creates new thread
- [ ] /chat in thread replies in same thread
- [ ] Thread history included in LLM context
```

### E2E Test Script

```bash
# Test meme pipeline end-to-end
uv run python scripts/test_meme_pipeline.py --verbose

# Test audio pipeline (VAD, STT)
uv run python scripts/test_audio_pipeline.py --stt
```

---

## Dependency Graph

```
Phase 1 (Critical)
├── 1.1 VoiceIngestSink abstract methods ─────┐
│                                              │
└── 1.2 Dismiss button fix                    │
                                              │
Phase 2 (Shitpost)                            │
├── 2.1 Preview image ◄──────────────────────┤
│       ↓                                     │
├── 2.2 Post button (depends on 2.1)         │
├── 2.3 Regenerate UX                        │
└── 2.4 Bot message filter                   │
                                              │
Phase 3 (Chat - Auto-Reply in Threads)        │
├── 3.2 Enable message_content intent         │
├── 3.3 Thread detection helper               │
├── 3.4 on_message event handler              │
├── 3.5 Thread message handler (new file)     │
├── 3.6 Update /chat for history              │
└── 3.7 Update _send_reply                    │
                                              │
Phase 4 (Voice)                               │
├── 4.1 Disable /speak                        │
├── 4.2 /transcript (depends on 1.1) ◄────────┘
├── 4.3 Voice text channel logic (depends on 4.2)
└── 4.4 Join/leave messages
```

---

## Recommended Execution Order

1. **1.1** - VoiceIngestSink (unblocks all voice features)
2. **1.2** - Dismiss button (quick fix, improves UX immediately)
3. **2.1** - Preview image (debug & fix)
4. **4.1** - Disable /speak (prevents user confusion)
5. **3.1** - Chat thread history (core feature)
6. **2.3** - Regenerate UX
7. **4.2** - /transcript command
8. **4.4** - Join/leave messages
9. **2.4** - Bot message filter
10. **4.3** - Voice text channel logic (requires testing with real Discord)

---

## Notes

### Docker Silero VAD Pre-download

The warning about untrusted repositories during /join should be addressed by pre-downloading the model in Docker. Check `docker/Dockerfile` for the model caching step. If missing:

```dockerfile
# Pre-download Silero VAD model
RUN python -c "import torch; torch.hub.load('snakers4/silero-vad', 'silero_vad', trust_repo=True)"
```

### VC Monitoring Nudge (Deferred)

The feature to automatically prompt users when 2+ people join VC is a larger undertaking requiring:
- A Discord Cog listening to voice state updates
- View with timeout logic
- State management across sessions

Recommend deferring to a future sprint.
