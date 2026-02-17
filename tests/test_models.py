"""Tests for model serialization."""

import dataclasses

import pytest

from clanker.models import Context


def test_context_round_trip(context: Context) -> None:
    payload = context.to_dict()
    restored = Context.from_dict(payload)
    assert restored == context


def test_context_requires_schema(context: Context) -> None:
    payload = context.to_dict()
    payload["schema_version"] = "v0"
    with pytest.raises(ValueError, match="Unsupported schema version"):
        Context.from_dict(payload)


def test_context_is_immutable(context: Context) -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        context.request_id = "updated"  # type: ignore[misc]
