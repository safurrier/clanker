"""Tests for profanity policy."""

import pytest

from clanker.models import Context, Message, Persona
from clanker.policies import SimpleProfanityPolicy


def test_policy_blocks_banned_term() -> None:
    policy = SimpleProfanityPolicy(banned_terms=("blocked",))
    context = Context(
        request_id="req",
        user_id=1,
        guild_id=None,
        channel_id=2,
        persona=Persona(id="p", display_name="p", system_prompt="sys"),
        messages=[Message(role="user", content="this is blocked")],
        metadata={},
    )
    with pytest.raises(ValueError, match="blocked content"):
        policy.validate(context)


def test_policy_allows_clean_text() -> None:
    policy = SimpleProfanityPolicy(banned_terms=("blocked",))
    context = Context(
        request_id="req",
        user_id=1,
        guild_id=None,
        channel_id=2,
        persona=Persona(id="p", display_name="p", system_prompt="sys"),
        messages=[Message(role="user", content="clean")],
        metadata={},
    )
    policy.validate(context)
