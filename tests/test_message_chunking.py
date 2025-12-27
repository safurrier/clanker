"""Tests for Discord message chunking (multi-message send for long responses)."""

from __future__ import annotations

import pytest

from clanker_bot.command_handlers.common import (
    DISCORD_MESSAGE_LIMIT,
    chunk_message,
)


class TestDiscordMessageLimit:
    """Verify the Discord message limit constant."""

    def test_discord_limit_is_2000(self) -> None:
        """Discord's message limit should be 2000 characters."""
        assert DISCORD_MESSAGE_LIMIT == 2000


class TestChunkMessage:
    """Test chunk_message helper function."""

    def test_short_message_returns_single_chunk(self) -> None:
        """Messages under the limit should return as a single chunk."""
        text = "Hello, world!"
        chunks = chunk_message(text)

        assert len(chunks) == 1
        assert chunks[0] == text

    def test_empty_message_returns_empty_list(self) -> None:
        """Empty messages should return an empty list."""
        chunks = chunk_message("")

        assert chunks == []

    def test_whitespace_only_returns_empty_list(self) -> None:
        """Whitespace-only messages should return an empty list."""
        chunks = chunk_message("   \n\t  ")

        assert chunks == []

    def test_exactly_at_limit_returns_single_chunk(self) -> None:
        """Message exactly at limit should return as single chunk."""
        text = "x" * 2000
        chunks = chunk_message(text)

        assert len(chunks) == 1
        assert chunks[0] == text

    def test_over_limit_splits_into_multiple_chunks(self) -> None:
        """Messages over limit should be split into multiple chunks."""
        text = "x" * 3500
        chunks = chunk_message(text)

        assert len(chunks) == 2
        assert all(len(c) <= 2000 for c in chunks)
        assert "".join(chunks) == text

    def test_preserves_all_content(self) -> None:
        """All content should be preserved when chunking."""
        text = "Hello " * 500  # 3000 chars
        chunks = chunk_message(text)

        assert "".join(chunks) == text

    def test_splits_on_newlines_when_possible(self) -> None:
        """Should prefer splitting at newline boundaries."""
        # Create text with a newline near the middle
        part1 = "a" * 1500
        part2 = "b" * 1500
        text = f"{part1}\n{part2}"

        chunks = chunk_message(text)

        # Should split at the newline, keeping newline with first chunk
        assert len(chunks) == 2
        assert chunks[0] == f"{part1}\n"
        assert chunks[1] == part2
        # Verify content is preserved
        assert "".join(chunks) == text

    def test_splits_on_spaces_when_no_newlines(self) -> None:
        """Should prefer splitting at space boundaries when no newlines."""
        # Create text with spaces
        words = ["word"] * 600  # Each "word " is 5 chars = 3000 total
        text = " ".join(words)

        chunks = chunk_message(text)

        # Each chunk should end at a word boundary (no partial words)
        assert len(chunks) >= 2
        for chunk in chunks:
            # Chunk shouldn't end mid-word
            assert not chunk.endswith("wor")
            assert not chunk.endswith("wo")
            assert not chunk.endswith("w")

    def test_hard_split_when_no_boundaries(self) -> None:
        """Should hard split when no natural boundaries exist."""
        text = "x" * 5000  # No spaces or newlines
        chunks = chunk_message(text)

        assert len(chunks) == 3
        assert chunks[0] == "x" * 2000
        assert chunks[1] == "x" * 2000
        assert chunks[2] == "x" * 1000

    def test_multiple_chunks_all_under_limit(self) -> None:
        """All chunks should be under the limit."""
        text = "y" * 10000
        chunks = chunk_message(text)

        assert all(len(c) <= 2000 for c in chunks)

    def test_custom_limit_parameter(self) -> None:
        """Should respect custom max_length parameter."""
        text = "Hello world! " * 10  # 130 chars
        chunks = chunk_message(text, max_length=50)

        assert all(len(c) <= 50 for c in chunks)
        assert "".join(chunks) == text

    def test_very_long_word_is_split(self) -> None:
        """Very long words without spaces should be hard split."""
        long_word = "a" * 2500
        text = f"Hello {long_word} world"
        chunks = chunk_message(text)

        # Content should be preserved
        assert "".join(chunks) == text
        assert all(len(c) <= 2000 for c in chunks)

    def test_preserves_multiple_newlines(self) -> None:
        """Should preserve formatting with multiple newlines."""
        text = "Line 1\n\nLine 2\n\n\nLine 3"
        chunks = chunk_message(text)

        assert "".join(chunks) == text

    def test_trailing_newline_preserved(self) -> None:
        """Trailing newlines should be preserved."""
        text = "Hello world\n"
        chunks = chunk_message(text)

        assert chunks == ["Hello world\n"]

    def test_leading_newline_preserved(self) -> None:
        """Leading newlines should be preserved."""
        text = "\nHello world"
        chunks = chunk_message(text)

        assert chunks == ["\nHello world"]

    def test_code_block_not_split_when_fits(self) -> None:
        """Code blocks that fit should stay together."""
        code = "```python\nprint('hello')\n```"
        text = f"Here's some code:\n{code}"
        chunks = chunk_message(text)

        assert len(chunks) == 1
        assert "```python" in chunks[0]
        assert "```" in chunks[0]

    def test_unicode_characters_handled(self) -> None:
        """Unicode characters should be handled correctly."""
        text = "🎉" * 1500  # Emojis
        chunks = chunk_message(text)

        assert "".join(chunks) == text
        assert all(len(c) <= 2000 for c in chunks)
