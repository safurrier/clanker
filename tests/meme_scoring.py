"""LLM-based meme quality scoring for E2E tests.

Provides a simple rubric-based scoring system for evaluating meme quality
in integration tests. Uses an LLM to assess:
- Relevance: Does the meme relate to the input context?
- Format adherence: Does it match the template structure?
- Coherence: Is it understandable?

This is intended for E2E test validation, not production use.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from clanker.models import Context, Message
from clanker.providers.base import LLM
from clanker.shitposts import MemeTemplate

SCORING_PROMPT = """You are evaluating the quality of a generated meme.

## Meme Template
Name: {template_id}
Description: {template_description}
Expected format: {text_slots} text lines

## Input Context
{input_context}

## Generated Meme Lines
{meme_lines}

## Evaluation Rubric

Rate each criterion from 1-5:

1. **Relevance** (1-5): Does the meme content relate to the input context?
   - 1: Completely unrelated
   - 3: Loosely related
   - 5: Directly relevant and topical

2. **Format Adherence** (1-5): Does it match the meme template structure?
   - 1: Wrong number of lines or nonsensical format
   - 3: Correct structure but awkward
   - 5: Perfect format for this meme type

3. **Coherence** (1-5): Is the meme understandable and makes sense?
   - 1: Incomprehensible
   - 3: Makes sense but confusing
   - 5: Clear and easy to understand

Respond with ONLY a JSON object:
{{"relevance": <1-5>, "format": <1-5>, "coherence": <1-5>, "reasoning": "<brief explanation>"}}
"""


@dataclass(frozen=True)
class MemeScore:
    """Quality score for a generated meme."""

    relevance: int  # 1-5
    format_adherence: int  # 1-5
    coherence: int  # 1-5
    reasoning: str
    raw_response: str

    @property
    def average(self) -> float:
        """Average score across all criteria."""
        return (self.relevance + self.format_adherence + self.coherence) / 3

    @property
    def passes_threshold(self) -> bool:
        """Check if meme passes minimum quality threshold (avg >= 3)."""
        return self.average >= 3.0

    def __str__(self) -> str:
        return (
            f"MemeScore(relevance={self.relevance}, format={self.format_adherence}, "
            f"coherence={self.coherence}, avg={self.average:.2f}, "
            f"passes={self.passes_threshold})"
        )


async def score_meme(
    llm: LLM,
    context: Context,
    template: MemeTemplate,
    input_context: str,
    meme_lines: list[str],
) -> MemeScore:
    """Score a generated meme using LLM-based evaluation.

    Args:
        llm: LLM provider for evaluation
        context: Request context
        template: The meme template used
        input_context: The input that was used to generate the meme
        meme_lines: The generated meme text lines

    Returns:
        MemeScore with ratings and reasoning
    """
    prompt = SCORING_PROMPT.format(
        template_id=template.template_id,
        template_description=template.variant_description or template.variant,
        text_slots=template.text_slots,
        input_context=input_context[:500],  # Truncate long context
        meme_lines=json.dumps(meme_lines),
    )

    message = Message(role="user", content=prompt)
    response = await llm.generate(context, [message])

    try:
        # Parse JSON response
        scores = json.loads(response.content)
        return MemeScore(
            relevance=int(scores.get("relevance", 3)),
            format_adherence=int(scores.get("format", 3)),
            coherence=int(scores.get("coherence", 3)),
            reasoning=str(scores.get("reasoning", "")),
            raw_response=response.content,
        )
    except (json.JSONDecodeError, KeyError, ValueError):
        # If parsing fails, return neutral scores
        return MemeScore(
            relevance=3,
            format_adherence=3,
            coherence=3,
            reasoning=f"Failed to parse LLM response: {response.content[:200]}",
            raw_response=response.content,
        )


def validate_meme_structure(
    meme_lines: list[str],
    template: MemeTemplate,
) -> tuple[bool, str]:
    """Basic structural validation for meme output.

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not meme_lines:
        return False, "No meme lines generated"

    if len(meme_lines) != template.text_slots:
        return False, (
            f"Expected {template.text_slots} lines, got {len(meme_lines)}"
        )

    if not all(isinstance(line, str) for line in meme_lines):
        return False, "All lines must be strings"

    # At least one line should have content
    if not any(line.strip() for line in meme_lines):
        return False, "All meme lines are empty"

    return True, ""
