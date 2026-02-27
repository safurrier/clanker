"""Shitpost generation API."""

from __future__ import annotations

import secrets
from collections.abc import Iterable
from pathlib import Path

import yaml

from ..models import Context, Message
from ..providers.base import LLM
from .models import ShitpostContext, ShitpostRequest, ShitpostTemplate

TEMPLATES_PATH = Path(__file__).with_name("templates.yaml")


def load_templates() -> list[ShitpostTemplate]:
    """Load templates from YAML."""
    data = yaml.safe_load(TEMPLATES_PATH.read_text(encoding="utf-8"))
    return [
        ShitpostTemplate(
            name=item["name"],
            category=item["category"],
            prompt=item["prompt"],
            tags=tuple(item.get("tags", [])),
        )
        for item in data
    ]


def sample_template(
    templates: Iterable[ShitpostTemplate],
    category: str | None = None,
    name: str | None = None,
) -> ShitpostTemplate:
    """Select a template by category or name."""
    choices = list(templates)
    if name:
        for template in choices:
            if template.name == name:
                return template
        raise ValueError("Unknown shitpost template name")
    if category:
        filtered = [template for template in choices if template.category == category]
        if not filtered:
            raise ValueError("Unknown shitpost category")
        choices = filtered
    return secrets.choice(choices)


def build_request(
    template: ShitpostTemplate, shitpost_context: ShitpostContext
) -> ShitpostRequest:
    """Build a shitpost request from a template and context.

    Args:
        template: The shitpost template to use
        shitpost_context: Context containing user input and/or conversation history
    """
    topic = shitpost_context.get_prompt_input()
    variables = {"topic": topic}
    return ShitpostRequest(template=template, variables=variables)


async def render_shitpost(
    context: Context,
    llm: LLM,
    request: ShitpostRequest,
) -> Message:
    """Render a shitpost using the LLM."""
    prompt = request.template.prompt.format(**request.variables)
    message = Message(role="user", content=prompt)
    return await llm.generate(context, [message])
