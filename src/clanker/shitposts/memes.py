"""Meme template handling for shitposts."""

from __future__ import annotations

import json
import secrets
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from ..models import Context, Message
from ..providers.base import LLM, StructuredLLM
from .models import MemeLines, ShitpostContext

MEME_INSTANCE_ARGS_PATH = Path(__file__).with_name("meme_instance_args.json")
MEME_PROMPT_PATH = Path(__file__).with_name("prompts") / "shitpost_meme_generation.yaml"

# Track file modification time for cache invalidation
_last_registry_mtime: float | None = None


@dataclass(frozen=True)
class MemeTemplate:
    """Curated meme template metadata."""

    template_id: str
    variant: str
    variant_description: str
    examples: list[list[str]]
    reference: str
    applicable_context: str
    potentially_nsfw: bool
    do_not_use: bool
    additional_prompt_instructions: str = ""
    examples_updated: bool = False
    disable_reason: str = ""  # Optional: explains why do_not_use is True

    @property
    def text_slots(self) -> int:
        if not self.examples:
            return 2
        return max(len(example) for example in self.examples)


@dataclass(frozen=True)
class MemeGeneration:
    """Rendered meme output."""

    template: MemeTemplate
    lines: list[str]


@lru_cache(maxsize=4)
def _load_meme_templates_cached(
    include_nsfw: bool = False,
    include_disabled: bool = False,
    _cache_key: float = 0.0,  # mtime used as cache key
) -> tuple[MemeTemplate, ...]:
    """Load meme templates from JSON with caching.

    Internal function - use load_meme_templates() instead.
    """
    raw = json.loads(MEME_INSTANCE_ARGS_PATH.read_text(encoding="utf-8"))
    templates: list[MemeTemplate] = []
    for template_id, payload in raw.items():
        template = _build_template(template_id, payload)
        if not include_nsfw and template.potentially_nsfw:
            continue
        if not include_disabled and template.do_not_use:
            continue
        templates.append(template)
    return tuple(templates)


def load_meme_templates(
    include_nsfw: bool = False, include_disabled: bool = False
) -> tuple[MemeTemplate, ...]:
    """Load meme templates from the curated JSON registry.

    Results are cached to avoid repeated JSON parsing. Cache is automatically
    invalidated when the registry file is modified (hot-reload support).

    Args:
        include_nsfw: Include potentially NSFW templates
        include_disabled: Include templates marked do_not_use=True

    Returns:
        Tuple of MemeTemplate objects matching the filters

    Note: Returns tuple instead of list to support caching (tuples are hashable).
    """
    global _last_registry_mtime

    # Check if file was modified since last load
    current_mtime = MEME_INSTANCE_ARGS_PATH.stat().st_mtime

    if _last_registry_mtime != current_mtime:
        # File changed - clear cache
        _load_meme_templates_cached.cache_clear()
        _last_registry_mtime = current_mtime

    # Use mtime as cache key to ensure fresh data after file changes
    return _load_meme_templates_cached(include_nsfw, include_disabled, current_mtime)


def sample_meme_template(
    templates: Iterable[MemeTemplate], template_id: str | None = None
) -> MemeTemplate:
    """Select a meme template by ID or at random."""
    choices = list(templates)
    if template_id:
        for template in choices:
            if template.template_id == template_id:
                return template
        raise ValueError("Unknown meme template")
    if not choices:
        raise ValueError("No meme templates available")
    return secrets.choice(choices)


async def render_meme_text(
    context: Context,
    llm: LLM | StructuredLLM,
    meme: MemeTemplate,
    shitpost_context: ShitpostContext,
) -> list[str]:
    """Generate meme text lines for a template.

    Args:
        context: LLM request context (user, channel, persona, etc.)
        llm: LLM provider for text generation (supports structured outputs if available)
        meme: Meme template to generate text for
        shitpost_context: Context containing user input and/or conversation history

    If the LLM supports structured outputs (has generate_structured method),
    it will be used for guaranteed schema compliance. Otherwise falls back to
    unstructured generation with JSON parsing.
    """
    topic = shitpost_context.get_prompt_input()
    prompt = build_meme_prompt(meme, topic)
    message = Message(role="user", content=prompt)

    # Use structured output if available (guarantees valid response)
    if isinstance(llm, StructuredLLM):
        result = await llm.generate_structured(MemeLines, [message])
        lines = result.lines
    else:
        # Fallback to unstructured generation with JSON parsing
        response = await llm.generate(context, [message])
        lines = parse_meme_lines(response.content)

    return normalize_meme_lines(lines, meme.text_slots)


def build_meme_prompt(meme: MemeTemplate, topic: str) -> str:
    """Build the LLM prompt for meme generation."""
    data = yaml.safe_load(MEME_PROMPT_PATH.read_text(encoding="utf-8"))
    template = data["template"]
    return template.format(
        topic=topic,
        template_id=meme.template_id,
        variant=meme.variant,
        variant_description=meme.variant_description,
        applicable_context=meme.applicable_context,
        reference=meme.reference,
        examples=json.dumps(meme.examples, ensure_ascii=False),
        text_slots=meme.text_slots,
        additional_prompt_instructions=meme.additional_prompt_instructions,
    )


def parse_meme_lines(text: str) -> list[str]:
    """Parse meme text lines from the LLM response."""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("Meme response was not valid JSON.") from exc
    if isinstance(payload, dict):
        payload = payload.get("text")
    if not isinstance(payload, list) or not all(
        isinstance(item, str) for item in payload
    ):
        raise ValueError("Meme response must be a JSON list of strings.")
    return [item.strip() for item in payload]


def normalize_meme_lines(lines: list[str], expected: int) -> list[str]:
    """Normalize meme lines to the expected length."""
    trimmed = [line for line in lines if line]
    if not trimmed:
        return [""] * expected
    if len(trimmed) < expected:
        trimmed.extend([""] * (expected - len(trimmed)))
        return trimmed
    return trimmed[:expected]


def _build_template(template_id: str, payload: dict) -> MemeTemplate:
    return MemeTemplate(
        template_id=str(payload.get("template_id") or template_id),
        variant=str(payload.get("variant") or ""),
        variant_description=str(payload.get("variant_description") or ""),
        examples=[list(example) for example in payload.get("examples") or []],
        reference=str(payload.get("reference") or ""),
        applicable_context=str(payload.get("applicable_context") or ""),
        potentially_nsfw=bool(payload.get("potentially_nsfw", False)),
        do_not_use=bool(payload.get("do_not_use", False)),
        additional_prompt_instructions=str(
            payload.get("additional_prompt_instructions", "")
        ),
        examples_updated=bool(payload.get("examples_updated", False)),
        disable_reason=str(payload.get("disable_reason", "")),
    )
