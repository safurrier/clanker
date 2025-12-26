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

from pydantic import BaseModel, Field

from clanker.models import Message
from clanker.providers.base import StructuredLLM
from clanker.shitposts import MemeTemplate


class MemeScoreResponse(BaseModel):
    """Structured output for meme quality scoring."""

    relevance: int = Field(ge=1, le=5, description="Relevance to input context (1-5)")
    format: int = Field(ge=1, le=5, description="Format adherence to template (1-5)")
    coherence: int = Field(ge=1, le=5, description="Clarity and understandability (1-5)")
    reasoning: str = Field(description="Brief explanation of the scores")

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
    llm: StructuredLLM,
    template: MemeTemplate,
    input_context: str,
    meme_lines: list[str],
) -> MemeScore:
    """Score a generated meme using LLM-based evaluation.

    Args:
        llm: LLM provider with structured output support (required)
        template: The meme template used
        input_context: The input that was used to generate the meme
        meme_lines: The generated meme text lines

    Returns:
        MemeScore with ratings and reasoning

    Raises:
        TypeError: If llm does not support structured outputs
    """
    if not isinstance(llm, StructuredLLM):
        raise TypeError(
            f"score_meme requires a StructuredLLM, got {type(llm).__name__}"
        )

    prompt = SCORING_PROMPT.format(
        template_id=template.template_id,
        template_description=template.variant_description or template.variant,
        text_slots=template.text_slots,
        input_context=input_context[:500],  # Truncate long context
        meme_lines=json.dumps(meme_lines),
    )

    message = Message(role="user", content=prompt)
    result = await llm.generate_structured(MemeScoreResponse, [message])

    return MemeScore(
        relevance=result.relevance,
        format_adherence=result.format,
        coherence=result.coherence,
        reasoning=result.reasoning,
        raw_response=result.model_dump_json(),
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
