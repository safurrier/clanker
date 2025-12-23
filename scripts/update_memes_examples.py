#!/usr/bin/env python3
"""Update meme examples using an LLM prompt."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import yaml

from clanker.models import Context, Message, Persona
from clanker.providers.openai import OpenAILLM

PROMPT_PATH = Path("src/clanker/shitposts/prompts/shitpost_meme_examples.yaml")
REGISTRY_PATH = Path("src/clanker/shitposts/meme_instance_args.json")


def load_prompt_template() -> str:
    data = yaml.safe_load(PROMPT_PATH.read_text(encoding="utf-8"))
    return data["template"]


def load_registry() -> dict[str, dict[str, Any]]:
    if not REGISTRY_PATH.exists():
        raise FileNotFoundError(f"Registry not found at {REGISTRY_PATH}")
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def save_registry(registry: dict[str, dict[str, Any]]) -> None:
    REGISTRY_PATH.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


async def generate_examples(
    llm: OpenAILLM, prompt_template: str, template_data: dict[str, Any]
) -> dict[str, Any]:
    prompt = prompt_template.format(
        context=str(template_data),
        additional_prompt_instructions=template_data.get(
            "additional_prompt_instructions", ""
        ),
    )
    context = Context(
        request_id="meme-examples",
        user_id=0,
        guild_id=None,
        channel_id=0,
        persona=Persona(
            id="memes",
            display_name="Memes",
            system_prompt="You are a meme expert.",
        ),
        messages=[Message(role="user", content=prompt)],
        metadata={"source": "script"},
    )
    message = await llm.generate(context, [Message(role="user", content=prompt)])
    payload = json.loads(message.content)
    return payload


async def main() -> None:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is required.")
    prompt_template = load_prompt_template()
    registry = load_registry()
    llm = OpenAILLM(api_key=api_key)

    for template_id, template_data in registry.items():
        if template_data.get("examples_updated", False):
            continue
        payload = await generate_examples(llm, prompt_template, template_data)
        examples = payload.get("examples")
        if not isinstance(examples, list):
            raise ValueError(f"Invalid examples for {template_id}")
        template_data["examples"] = examples
        template_data["examples_updated"] = True
        registry[template_id] = template_data
        save_registry(registry)

    await llm.aclose()


if __name__ == "__main__":
    asyncio.run(main())
