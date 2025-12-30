"""Tests for FeedbackStore protocol and FakeFeedbackStore."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from clanker.models import Interaction, Outcome
from clanker.providers.feedback import FeedbackStore

from .fakes import FailingFeedbackStore, FakeFeedbackStore


def make_interaction(
    *,
    id: str | None = None,
    user_id: str = "user-123",
    context_id: str = "guild-456",
    command: str = "shitpost",
    outcome: Outcome = Outcome.ACCEPTED,
    metadata: dict | None = None,
    created_at: datetime | None = None,
) -> Interaction:
    """Create a test interaction with sensible defaults."""
    return Interaction(
        id=id or str(uuid.uuid4()),
        user_id=user_id,
        context_id=context_id,
        command=command,
        outcome=outcome,
        metadata=metadata or {},
        created_at=created_at or datetime.now(timezone.utc),
    )


class TestFakeFeedbackStoreProtocol:
    """Tests that FakeFeedbackStore implements the protocol."""

    def test_fake_feedback_store_is_feedback_store(self) -> None:
        """FakeFeedbackStore satisfies FeedbackStore protocol structurally."""
        fake = FakeFeedbackStore()
        # Check that it has all required methods
        assert hasattr(fake, "record")
        assert hasattr(fake, "get_user_stats")
        assert hasattr(fake, "get_recent_interactions")
        assert hasattr(fake, "get_acceptance_rate")

    def test_fake_feedback_store_type_annotation(self) -> None:
        """FakeFeedbackStore can be assigned to FeedbackStore type."""
        # This is a compile-time check, but we can verify it doesn't raise
        store: FeedbackStore = FakeFeedbackStore()
        assert store is not None


class TestFakeFeedbackStoreRecord:
    """Tests for FakeFeedbackStore.record()."""

    @pytest.mark.asyncio
    async def test_record_stores_interaction(self) -> None:
        """Recording an interaction stores it in the list."""
        fake = FakeFeedbackStore()
        interaction = make_interaction(outcome=Outcome.ACCEPTED)

        await fake.record(interaction)

        assert len(fake.interactions) == 1
        assert fake.interactions[0] == interaction

    @pytest.mark.asyncio
    async def test_record_multiple_interactions(self) -> None:
        """Recording multiple interactions stores all of them."""
        fake = FakeFeedbackStore()

        for i in range(5):
            await fake.record(make_interaction(id=f"interaction-{i}"))

        assert len(fake.interactions) == 5


class TestFakeFeedbackStoreUserStats:
    """Tests for FakeFeedbackStore.get_user_stats()."""

    @pytest.mark.asyncio
    async def test_user_stats_empty(self) -> None:
        """Empty store returns zero counts for all outcomes."""
        fake = FakeFeedbackStore()

        stats = await fake.get_user_stats("user-123")

        assert stats[Outcome.ACCEPTED] == 0
        assert stats[Outcome.REJECTED] == 0
        assert stats[Outcome.REGENERATED] == 0
        assert stats[Outcome.TIMEOUT] == 0

    @pytest.mark.asyncio
    async def test_user_stats_counts_correctly(self) -> None:
        """User stats counts outcomes correctly."""
        fake = FakeFeedbackStore()
        await fake.record(make_interaction(outcome=Outcome.ACCEPTED))
        await fake.record(make_interaction(outcome=Outcome.ACCEPTED))
        await fake.record(make_interaction(outcome=Outcome.REJECTED))

        stats = await fake.get_user_stats("user-123")

        assert stats[Outcome.ACCEPTED] == 2
        assert stats[Outcome.REJECTED] == 1
        assert stats[Outcome.REGENERATED] == 0

    @pytest.mark.asyncio
    async def test_user_stats_filters_by_user(self) -> None:
        """User stats only counts interactions for the specified user."""
        fake = FakeFeedbackStore()
        await fake.record(make_interaction(user_id="user-A", outcome=Outcome.ACCEPTED))
        await fake.record(make_interaction(user_id="user-A", outcome=Outcome.ACCEPTED))
        await fake.record(make_interaction(user_id="user-B", outcome=Outcome.ACCEPTED))

        stats_a = await fake.get_user_stats("user-A")
        stats_b = await fake.get_user_stats("user-B")

        assert stats_a[Outcome.ACCEPTED] == 2
        assert stats_b[Outcome.ACCEPTED] == 1

    @pytest.mark.asyncio
    async def test_user_stats_filters_by_context(self) -> None:
        """User stats can be filtered by context_id."""
        fake = FakeFeedbackStore()
        await fake.record(
            make_interaction(context_id="guild-A", outcome=Outcome.ACCEPTED)
        )
        await fake.record(
            make_interaction(context_id="guild-A", outcome=Outcome.ACCEPTED)
        )
        await fake.record(
            make_interaction(context_id="guild-A", outcome=Outcome.ACCEPTED)
        )
        await fake.record(
            make_interaction(context_id="guild-B", outcome=Outcome.ACCEPTED)
        )
        await fake.record(
            make_interaction(context_id="guild-B", outcome=Outcome.ACCEPTED)
        )

        stats_a = await fake.get_user_stats("user-123", context_id="guild-A")
        stats_b = await fake.get_user_stats("user-123", context_id="guild-B")
        stats_all = await fake.get_user_stats("user-123")

        assert stats_a[Outcome.ACCEPTED] == 3
        assert stats_b[Outcome.ACCEPTED] == 2
        assert stats_all[Outcome.ACCEPTED] == 5

    @pytest.mark.asyncio
    async def test_user_stats_filters_by_command(self) -> None:
        """User stats can be filtered by command."""
        fake = FakeFeedbackStore()
        await fake.record(make_interaction(command="shitpost", outcome=Outcome.ACCEPTED))
        await fake.record(make_interaction(command="shitpost", outcome=Outcome.ACCEPTED))
        await fake.record(make_interaction(command="chat", outcome=Outcome.ACCEPTED))

        stats_shitpost = await fake.get_user_stats("user-123", command="shitpost")
        stats_chat = await fake.get_user_stats("user-123", command="chat")

        assert stats_shitpost[Outcome.ACCEPTED] == 2
        assert stats_chat[Outcome.ACCEPTED] == 1


class TestFakeFeedbackStoreRecentInteractions:
    """Tests for FakeFeedbackStore.get_recent_interactions()."""

    @pytest.mark.asyncio
    async def test_recent_interactions_empty(self) -> None:
        """Empty store returns empty list."""
        fake = FakeFeedbackStore()

        recent = await fake.get_recent_interactions("user-123")

        assert recent == []

    @pytest.mark.asyncio
    async def test_recent_interactions_returns_all(self) -> None:
        """Returns all interactions when under limit."""
        fake = FakeFeedbackStore()
        for i in range(3):
            await fake.record(make_interaction(id=f"interaction-{i}"))

        recent = await fake.get_recent_interactions("user-123")

        assert len(recent) == 3

    @pytest.mark.asyncio
    async def test_recent_interactions_respects_limit(self) -> None:
        """Returns at most limit interactions."""
        fake = FakeFeedbackStore()
        for i in range(10):
            await fake.record(make_interaction(id=f"interaction-{i}"))

        recent = await fake.get_recent_interactions("user-123", limit=5)

        assert len(recent) == 5

    @pytest.mark.asyncio
    async def test_recent_interactions_ordered_by_time(self) -> None:
        """Returns interactions in reverse chronological order."""
        fake = FakeFeedbackStore()
        now = datetime.now(timezone.utc)

        # Record interactions with different timestamps
        for i in range(5):
            await fake.record(
                make_interaction(
                    id=f"interaction-{i}",
                    created_at=now - timedelta(minutes=i),
                )
            )

        recent = await fake.get_recent_interactions("user-123")

        # Most recent (i=0) should be first
        assert recent[0].id == "interaction-0"
        assert recent[4].id == "interaction-4"

    @pytest.mark.asyncio
    async def test_recent_interactions_filters_by_user(self) -> None:
        """Only returns interactions for the specified user."""
        fake = FakeFeedbackStore()
        await fake.record(make_interaction(user_id="user-A", id="A-1"))
        await fake.record(make_interaction(user_id="user-B", id="B-1"))
        await fake.record(make_interaction(user_id="user-A", id="A-2"))

        recent_a = await fake.get_recent_interactions("user-A")
        recent_b = await fake.get_recent_interactions("user-B")

        assert len(recent_a) == 2
        assert len(recent_b) == 1
        assert all(i.user_id == "user-A" for i in recent_a)


class TestFakeFeedbackStoreAcceptanceRate:
    """Tests for FakeFeedbackStore.get_acceptance_rate()."""

    @pytest.mark.asyncio
    async def test_acceptance_rate_no_data(self) -> None:
        """Returns 0.5 when no data exists."""
        fake = FakeFeedbackStore()

        rate = await fake.get_acceptance_rate("user-123", "shitpost")

        assert rate == 0.5

    @pytest.mark.asyncio
    async def test_acceptance_rate_all_accepted(self) -> None:
        """Returns 1.0 when all interactions are accepted."""
        fake = FakeFeedbackStore()
        for _ in range(5):
            await fake.record(make_interaction(outcome=Outcome.ACCEPTED))

        rate = await fake.get_acceptance_rate("user-123", "shitpost")

        assert rate == 1.0

    @pytest.mark.asyncio
    async def test_acceptance_rate_none_accepted(self) -> None:
        """Returns 0.0 when no interactions are accepted."""
        fake = FakeFeedbackStore()
        for _ in range(3):
            await fake.record(make_interaction(outcome=Outcome.REJECTED))

        rate = await fake.get_acceptance_rate("user-123", "shitpost")

        assert rate == 0.0

    @pytest.mark.asyncio
    async def test_acceptance_rate_mixed(self) -> None:
        """Calculates correct rate for mixed outcomes."""
        fake = FakeFeedbackStore()
        # 3 accepted, 1 rejected = 75%
        for _ in range(3):
            await fake.record(make_interaction(outcome=Outcome.ACCEPTED))
        await fake.record(make_interaction(outcome=Outcome.REJECTED))

        rate = await fake.get_acceptance_rate("user-123", "shitpost")

        assert rate == 0.75

    @pytest.mark.asyncio
    async def test_acceptance_rate_excludes_timeout(self) -> None:
        """Timeout outcomes are excluded from rate calculation."""
        fake = FakeFeedbackStore()
        # 2 accepted, 1 rejected, 5 timeout = 2/3 = 66.7%
        await fake.record(make_interaction(outcome=Outcome.ACCEPTED))
        await fake.record(make_interaction(outcome=Outcome.ACCEPTED))
        await fake.record(make_interaction(outcome=Outcome.REJECTED))
        for _ in range(5):
            await fake.record(make_interaction(outcome=Outcome.TIMEOUT))

        rate = await fake.get_acceptance_rate("user-123", "shitpost")

        assert abs(rate - 0.667) < 0.01

    @pytest.mark.asyncio
    async def test_acceptance_rate_includes_regenerated(self) -> None:
        """Regenerated counts as non-acceptance in rate calculation."""
        fake = FakeFeedbackStore()
        # 4 accepted, 1 rejected, 1 regenerated = 4/6 = 66.7%
        for _ in range(4):
            await fake.record(make_interaction(outcome=Outcome.ACCEPTED))
        await fake.record(make_interaction(outcome=Outcome.REJECTED))
        await fake.record(make_interaction(outcome=Outcome.REGENERATED))

        rate = await fake.get_acceptance_rate("user-123", "shitpost")

        assert abs(rate - 0.667) < 0.01


class TestFailingFeedbackStore:
    """Tests for FailingFeedbackStore error handling."""

    @pytest.mark.asyncio
    async def test_record_raises(self) -> None:
        """FailingFeedbackStore.record() always raises."""
        store = FailingFeedbackStore()

        with pytest.raises(RuntimeError, match="Simulated storage failure"):
            await store.record(make_interaction())

    @pytest.mark.asyncio
    async def test_get_user_stats_raises(self) -> None:
        """FailingFeedbackStore.get_user_stats() always raises."""
        store = FailingFeedbackStore()

        with pytest.raises(RuntimeError, match="Simulated storage failure"):
            await store.get_user_stats("user-123")

    @pytest.mark.asyncio
    async def test_get_acceptance_rate_raises(self) -> None:
        """FailingFeedbackStore.get_acceptance_rate() always raises."""
        store = FailingFeedbackStore()

        with pytest.raises(RuntimeError, match="Simulated storage failure"):
            await store.get_acceptance_rate("user-123", "shitpost")
