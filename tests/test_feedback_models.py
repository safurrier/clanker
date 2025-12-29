"""Tests for feedback models."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from clanker.models import Interaction, Outcome, UserPreferences


class TestOutcome:
    """Tests for the Outcome enum."""

    def test_outcome_enum_values(self) -> None:
        """Outcome enum has expected string values."""
        assert Outcome.ACCEPTED.value == "accepted"
        assert Outcome.REJECTED.value == "rejected"
        assert Outcome.REGENERATED.value == "regenerated"
        assert Outcome.TIMEOUT.value == "timeout"

    def test_outcome_is_string_enum(self) -> None:
        """Outcome enum values can be used as strings."""
        assert str(Outcome.ACCEPTED) == "Outcome.ACCEPTED"
        assert Outcome.ACCEPTED == "accepted"

    def test_outcome_from_string(self) -> None:
        """Outcome can be created from string value."""
        assert Outcome("accepted") == Outcome.ACCEPTED
        assert Outcome("rejected") == Outcome.REJECTED

    def test_outcome_invalid_value_raises(self) -> None:
        """Invalid outcome value raises ValueError."""
        with pytest.raises(ValueError):
            Outcome("invalid")


class TestInteraction:
    """Tests for the Interaction dataclass."""

    def test_interaction_creation(self) -> None:
        """Interaction can be created with all required fields."""
        now = datetime.now(timezone.utc)
        interaction = Interaction(
            id="test-123",
            user_id="user-456",
            context_id="guild-789",
            command="shitpost",
            outcome=Outcome.ACCEPTED,
            metadata={"template": "drake"},
            created_at=now,
        )

        assert interaction.id == "test-123"
        assert interaction.user_id == "user-456"
        assert interaction.context_id == "guild-789"
        assert interaction.command == "shitpost"
        assert interaction.outcome == Outcome.ACCEPTED
        assert interaction.metadata == {"template": "drake"}
        assert interaction.created_at == now

    def test_interaction_frozen(self) -> None:
        """Interaction dataclass is immutable."""
        interaction = Interaction(
            id="test-123",
            user_id="user-456",
            context_id="guild-789",
            command="shitpost",
            outcome=Outcome.ACCEPTED,
            metadata={"template": "drake"},
            created_at=datetime.now(timezone.utc),
        )

        with pytest.raises(FrozenInstanceError):
            interaction.outcome = Outcome.REJECTED  # type: ignore[misc]

    def test_interaction_empty_metadata(self) -> None:
        """Interaction works with empty metadata."""
        interaction = Interaction(
            id="test-123",
            user_id="user-456",
            context_id="guild-789",
            command="chat",
            outcome=Outcome.ACCEPTED,
            metadata={},
            created_at=datetime.now(timezone.utc),
        )

        assert interaction.metadata == {}

    def test_interaction_complex_metadata(self) -> None:
        """Interaction supports complex metadata structures."""
        metadata = {
            "template": "drake",
            "length": 42,
            "tags": ["funny", "meme"],
            "nested": {"key": "value"},
        }
        interaction = Interaction(
            id="test-123",
            user_id="user-456",
            context_id="guild-789",
            command="shitpost",
            outcome=Outcome.ACCEPTED,
            metadata=metadata,
            created_at=datetime.now(timezone.utc),
        )

        assert interaction.metadata["template"] == "drake"
        assert interaction.metadata["length"] == 42
        assert interaction.metadata["tags"] == ["funny", "meme"]

    def test_interaction_equality(self) -> None:
        """Two interactions with same values are equal."""
        now = datetime.now(timezone.utc)
        interaction1 = Interaction(
            id="test-123",
            user_id="user-456",
            context_id="guild-789",
            command="shitpost",
            outcome=Outcome.ACCEPTED,
            metadata={},
            created_at=now,
        )
        interaction2 = Interaction(
            id="test-123",
            user_id="user-456",
            context_id="guild-789",
            command="shitpost",
            outcome=Outcome.ACCEPTED,
            metadata={},
            created_at=now,
        )

        assert interaction1 == interaction2


class TestUserPreferences:
    """Tests for the UserPreferences dataclass."""

    def test_user_preferences_creation(self) -> None:
        """UserPreferences can be created with all required fields."""
        now = datetime.now(timezone.utc)
        prefs = UserPreferences(
            user_id="user-123",
            context_id="guild-456",
            preferences={"preferred_style": "edgy"},
            updated_at=now,
        )

        assert prefs.user_id == "user-123"
        assert prefs.context_id == "guild-456"
        assert prefs.preferences == {"preferred_style": "edgy"}
        assert prefs.updated_at == now

    def test_user_preferences_frozen(self) -> None:
        """UserPreferences dataclass is immutable."""
        prefs = UserPreferences(
            user_id="user-123",
            context_id="guild-456",
            preferences={"preferred_style": "edgy"},
            updated_at=datetime.now(timezone.utc),
        )

        with pytest.raises(FrozenInstanceError):
            prefs.preferences = {}  # type: ignore[misc]

    def test_user_preferences_empty(self) -> None:
        """UserPreferences works with empty preferences."""
        prefs = UserPreferences(
            user_id="user-123",
            context_id="guild-456",
            preferences={},
            updated_at=datetime.now(timezone.utc),
        )

        assert prefs.preferences == {}

    def test_user_preferences_complex(self) -> None:
        """UserPreferences supports complex preference structures."""
        preferences = {
            "preferred_style": "edgy",
            "favorite_templates": ["drake", "distracted"],
            "settings": {"auto_post": False, "nsfw": True},
        }
        prefs = UserPreferences(
            user_id="user-123",
            context_id="guild-456",
            preferences=preferences,
            updated_at=datetime.now(timezone.utc),
        )

        assert prefs.preferences["preferred_style"] == "edgy"
        assert prefs.preferences["favorite_templates"] == ["drake", "distracted"]
