"""Simple profanity policy."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..models import Context
from ..providers.policy import Policy


@dataclass(frozen=True)
class SimpleProfanityPolicy(Policy):
    """Block contexts containing banned terms."""

    banned_terms: tuple[str, ...] = ("badword", "worseword")

    def validate(self, context: Context) -> None:
        content = " ".join(message.content for message in context.messages)
        for term in self.banned_terms:
            if _contains_term(content, term):
                raise ValueError("Prompt contains blocked content")


def _contains_term(content: str, term: str) -> bool:
    return re.search(rf"\b{re.escape(term)}\b", content, re.IGNORECASE) is not None
