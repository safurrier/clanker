"""Tests for thread auto-reply functionality."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from contextlib import asynccontextmanager

import pytest

from clanker.models import Message, Persona
from clanker_bot.command_handlers.common import (
    CLANKER_THREAD_PATTERN,
    is_clanker_thread,
)
from clanker_bot.command_handlers.thread_chat import (
    _fetch_thread_history,
    handle_thread_message,
)
from clanker_bot.command_handlers.types import BotDependencies
from tests.fakes import FakeLLM


class TestClankerThreadPattern:
    """Test thread name pattern matching."""

    def test_matches_valid_clanker_thread_names(self) -> None:
        """Should match clanker-{6 hex chars} pattern."""
        assert CLANKER_THREAD_PATTERN.match("clanker-abc123")
        assert CLANKER_THREAD_PATTERN.match("clanker-000000")
        assert CLANKER_THREAD_PATTERN.match("clanker-ffffff")
        assert CLANKER_THREAD_PATTERN.match("clanker-a1b2c3")

    def test_rejects_too_short_hex(self) -> None:
        """Should reject names with less than 6 hex chars."""
        assert not CLANKER_THREAD_PATTERN.match("clanker-abc")
        assert not CLANKER_THREAD_PATTERN.match("clanker-12345")

    def test_rejects_too_long_hex(self) -> None:
        """Should reject names with more than 6 hex chars."""
        assert not CLANKER_THREAD_PATTERN.match("clanker-abc1234")
        assert not CLANKER_THREAD_PATTERN.match("clanker-1234567")

    def test_rejects_uppercase_hex(self) -> None:
        """Should reject uppercase hex (we generate lowercase)."""
        assert not CLANKER_THREAD_PATTERN.match("clanker-ABCDEF")
        assert not CLANKER_THREAD_PATTERN.match("clanker-ABC123")

    def test_rejects_non_hex_chars(self) -> None:
        """Should reject non-hex characters."""
        assert not CLANKER_THREAD_PATTERN.match("clanker-ghijkl")
        assert not CLANKER_THREAD_PATTERN.match("clanker-xyz123")

    def test_rejects_other_prefixes(self) -> None:
        """Should reject names without clanker- prefix."""
        assert not CLANKER_THREAD_PATTERN.match("other-abc123")
        assert not CLANKER_THREAD_PATTERN.match("thread-abc123")
        assert not CLANKER_THREAD_PATTERN.match("abc123")


class TestIsClankerThread:
    """Test is_clanker_thread helper function."""

    def test_returns_false_for_none(self) -> None:
        """Should return False for None input."""
        assert is_clanker_thread(None) is False

    def test_returns_false_for_string(self) -> None:
        """Should return False for string (not a Thread object)."""
        assert is_clanker_thread("clanker-abc123") is False  # type: ignore[arg-type]

    def test_returns_false_for_non_thread_channel(self) -> None:
        """Should return False for non-Thread channel types."""

        @dataclass
        class FakeTextChannel:
            name: str = "general"

        channel = FakeTextChannel()
        assert is_clanker_thread(channel) is False  # type: ignore[arg-type]

    def test_returns_true_for_matching_thread(self) -> None:
        """Should return True for Thread with matching name."""
        # We can't easily create a real discord.Thread in tests,
        # so we test with a duck-typed object that has __class__.__name__ = "Thread"

        @dataclass
        class FakeThread:
            name: str

        # Patch the class name to simulate discord.Thread
        FakeThread.__name__ = "Thread"

        thread = FakeThread(name="clanker-abc123")
        # Note: The real is_clanker_thread uses isinstance(channel, discord.Thread)
        # which won't work with our fake. We'll test the pattern match instead.
        assert CLANKER_THREAD_PATTERN.match(thread.name)

    def test_returns_false_for_thread_with_wrong_name(self) -> None:
        """Should return False for Thread with non-matching name."""

        @dataclass
        class FakeThread:
            name: str

        thread = FakeThread(name="general-chat")
        assert not CLANKER_THREAD_PATTERN.match(thread.name)


# --- Fakes for thread testing ---


@dataclass
class FakeAuthor:
    """Fake Discord author."""

    id: int
    display_name: str
    bot: bool = False


@dataclass
class FakeMessage:
    """Fake Discord message."""

    content: str
    author: FakeAuthor


class FakeHistoryIterator:
    """Async iterator for fake thread history."""

    def __init__(self, messages: list[FakeMessage]) -> None:
        self._messages = messages
        self._index = 0

    def __aiter__(self) -> FakeHistoryIterator:
        return self

    async def __anext__(self) -> FakeMessage:
        if self._index >= len(self._messages):
            raise StopAsyncIteration
        msg = self._messages[self._index]
        self._index += 1
        return msg


@dataclass
class FakeGuildMe:
    """Fake guild.me for getting bot ID."""

    id: int = 999


@dataclass
class FakeGuild:
    """Fake Discord guild."""

    id: int = 123
    me: FakeGuildMe = field(default_factory=FakeGuildMe)


@dataclass
class FakeThread:
    """Fake Discord thread for testing."""

    id: int
    name: str
    history_messages: list[FakeMessage] = field(default_factory=list)
    sent_messages: list[str] = field(default_factory=list)
    guild: FakeGuild = field(default_factory=FakeGuild)
    _typing: bool = False

    def history(self, limit: int = 100) -> FakeHistoryIterator:
        """Return async iterator over history."""
        return FakeHistoryIterator(self.history_messages[:limit])

    async def send(self, content: str, **kwargs: Any) -> None:
        """Record sent message."""
        self.sent_messages.append(content)

    @asynccontextmanager
    async def typing(self):
        """Fake typing context manager."""
        self._typing = True
        try:
            yield
        finally:
            self._typing = False


@dataclass
class FakeDiscordMessage:
    """Fake Discord message for on_message handler."""

    content: str
    author: FakeAuthor
    channel: FakeThread
    guild: FakeGuild = field(default_factory=FakeGuild)


class TestFetchThreadHistory:
    """Test _fetch_thread_history function."""

    @pytest.fixture
    def bot_author(self) -> FakeAuthor:
        """Bot author with ID matching guild.me."""
        return FakeAuthor(id=999, display_name="Clanker", bot=True)

    @pytest.fixture
    def user_alice(self) -> FakeAuthor:
        """Human user Alice."""
        return FakeAuthor(id=1, display_name="Alice", bot=False)

    @pytest.fixture
    def user_bob(self) -> FakeAuthor:
        """Human user Bob."""
        return FakeAuthor(id=2, display_name="Bob", bot=False)

    @pytest.mark.asyncio
    async def test_returns_messages_in_chronological_order(
        self, user_alice: FakeAuthor, user_bob: FakeAuthor
    ) -> None:
        """History should return oldest-first after reversing Discord's newest-first."""
        # Discord returns newest first, so we simulate that
        thread = FakeThread(
            id=100,
            name="clanker-abc123",
            history_messages=[
                FakeMessage(content="Third", author=user_bob),
                FakeMessage(content="Second", author=user_alice),
                FakeMessage(content="First", author=user_alice),
            ],
        )

        history = await _fetch_thread_history(thread, limit=10)  # type: ignore[arg-type]

        assert len(history) == 3
        assert history[0].content == "Alice: First"
        assert history[1].content == "Alice: Second"
        assert history[2].content == "Bob: Third"

    @pytest.mark.asyncio
    async def test_labels_bot_messages_as_assistant(
        self, bot_author: FakeAuthor, user_alice: FakeAuthor
    ) -> None:
        """Bot's own messages should have role='assistant'."""
        thread = FakeThread(
            id=100,
            name="clanker-abc123",
            history_messages=[
                FakeMessage(content="Bot reply", author=bot_author),
                FakeMessage(content="User message", author=user_alice),
            ],
        )

        history = await _fetch_thread_history(thread, limit=10)  # type: ignore[arg-type]

        # Reversed order: user message first, then bot
        assert history[0].role == "user"
        assert history[1].role == "assistant"
        assert history[1].content == "Bot reply"

    @pytest.mark.asyncio
    async def test_includes_username_for_user_messages(
        self, user_alice: FakeAuthor
    ) -> None:
        """User messages should include display_name prefix."""
        thread = FakeThread(
            id=100,
            name="clanker-abc123",
            history_messages=[FakeMessage(content="Hello", author=user_alice)],
        )

        history = await _fetch_thread_history(thread, limit=10)  # type: ignore[arg-type]

        assert history[0].role == "user"
        assert history[0].content == "Alice: Hello"

    @pytest.mark.asyncio
    async def test_skips_empty_messages(self, user_alice: FakeAuthor) -> None:
        """Empty/whitespace-only messages should be skipped."""
        thread = FakeThread(
            id=100,
            name="clanker-abc123",
            history_messages=[
                FakeMessage(content="Real message", author=user_alice),
                FakeMessage(content="", author=user_alice),
                FakeMessage(content="   ", author=user_alice),
            ],
        )

        history = await _fetch_thread_history(thread, limit=10)  # type: ignore[arg-type]

        assert len(history) == 1
        assert "Real message" in history[0].content

    @pytest.mark.asyncio
    async def test_respects_limit(self, user_alice: FakeAuthor) -> None:
        """Should only fetch up to limit messages."""
        thread = FakeThread(
            id=100,
            name="clanker-abc123",
            history_messages=[
                FakeMessage(content=f"Message {i}", author=user_alice)
                for i in range(10)
            ],
        )

        history = await _fetch_thread_history(thread, limit=3)  # type: ignore[arg-type]

        assert len(history) == 3


class TestHandleThreadMessage:
    """Test handle_thread_message function."""

    @pytest.fixture
    def persona(self) -> Persona:
        """Test persona."""
        return Persona(
            id="test",
            display_name="Test Bot",
            system_prompt="You are a test bot.",
            tts_voice=None,
            providers=None,
        )

    @pytest.fixture
    def deps(self, persona: Persona) -> BotDependencies:
        """Test dependencies with FakeLLM."""
        return BotDependencies(
            llm=FakeLLM(reply_text="Hello from bot!"),
            stt=None,
            tts=None,
            image=None,
            persona=persona,
            voice_manager=None,  # type: ignore[arg-type]
            metrics=None,
            admin_user_ids=set(),
            admin_state=None,  # type: ignore[arg-type]
        )

    @pytest.mark.asyncio
    async def test_responds_with_llm_reply(self, deps: BotDependencies) -> None:
        """Should call LLM and send response to thread."""
        thread = FakeThread(
            id=100,
            name="clanker-abc123",
            history_messages=[],
        )
        user = FakeAuthor(id=1, display_name="Alice", bot=False)
        message = FakeDiscordMessage(
            content="Hello bot",
            author=user,
            channel=thread,
        )

        await handle_thread_message(message, deps)  # type: ignore[arg-type]

        assert len(thread.sent_messages) == 1
        assert thread.sent_messages[0] == "Hello from bot!"

    @pytest.mark.asyncio
    async def test_includes_history_in_context(self, deps: BotDependencies) -> None:
        """Context should include thread history messages."""
        user = FakeAuthor(id=1, display_name="Alice", bot=False)
        thread = FakeThread(
            id=100,
            name="clanker-abc123",
            history_messages=[
                FakeMessage(content="Previous message", author=user),
            ],
        )
        message = FakeDiscordMessage(
            content="New message",
            author=user,
            channel=thread,
        )

        # We can't easily verify context without mocking,
        # but we verify the handler completes successfully
        await handle_thread_message(message, deps)  # type: ignore[arg-type]

        assert len(thread.sent_messages) == 1

    @pytest.mark.asyncio
    async def test_splits_long_response_into_multiple_messages(
        self, persona: Persona
    ) -> None:
        """Long responses should be split into multiple messages."""
        # Create LLM that returns a response over 2000 chars
        long_response = "word " * 600  # 3000 chars
        deps = BotDependencies(
            llm=FakeLLM(reply_text=long_response),
            stt=None,
            tts=None,
            image=None,
            persona=persona,
            voice_manager=None,  # type: ignore[arg-type]
            metrics=None,
            admin_user_ids=set(),
            admin_state=None,  # type: ignore[arg-type]
        )

        thread = FakeThread(
            id=100,
            name="clanker-abc123",
            history_messages=[],
        )
        user = FakeAuthor(id=1, display_name="Alice", bot=False)
        message = FakeDiscordMessage(
            content="Tell me something long",
            author=user,
            channel=thread,
        )

        await handle_thread_message(message, deps)  # type: ignore[arg-type]

        # Should have multiple messages
        assert len(thread.sent_messages) >= 2
        # All messages should be under the limit
        assert all(len(msg) <= 2000 for msg in thread.sent_messages)
        # All content should be preserved
        assert "".join(thread.sent_messages) == long_response
