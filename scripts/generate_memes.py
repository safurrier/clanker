#!/usr/bin/env python3
"""Generate meme template metadata from Memegen + LLM."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import yaml

from clanker.models import Context, Message, Persona
from clanker.providers.openai import OpenAILLM
from clanker.shitposts.memes import MemeTemplate

PROMPT_PATH = Path("src/clanker/shitposts/prompts/shitpost_meme_json_extraction.yaml")
REGISTRY_PATH = Path("src/clanker/shitposts/meme_instance_args.json")
MEMEGEN_TEMPLATES_URL = "https://api.memegen.link/templates"


@dataclass
class MemegenTemplate:
    """Representation of the Memegen template payload."""

    id: str
    name: str
    example: dict[str, Any]
    source: str | None = None
    keywords: list[str] | None = None

    @property
    def prompt_context(self) -> str:
        return "\n".join(
            [
                f"ID: {self.id}",
                f"Name: {self.name}",
                f"Example Text Inputs: {self.example.get('text', [])}",
                f"Keywords: {self.keywords or []}",
                f"Reference: {self.source or ''}",
            ]
        )


def load_prompt_template() -> str:
    data = yaml.safe_load(PROMPT_PATH.read_text(encoding="utf-8"))
    return data["template"]


async def fetch_memegen_templates(client: httpx.AsyncClient) -> list[MemegenTemplate]:
    response = await client.get(MEMEGEN_TEMPLATES_URL)
    response.raise_for_status()
    templates = []
    for payload in response.json():
        templates.append(
            MemegenTemplate(
                id=payload["id"],
                name=payload["name"],
                example=payload.get("example", {}),
                source=payload.get("source"),
                keywords=payload.get("keywords"),
            )
        )
    return templates


def load_registry() -> dict[str, dict[str, Any]]:
    if not REGISTRY_PATH.exists():
        return {}
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def save_registry(registry: dict[str, dict[str, Any]]) -> None:
    REGISTRY_PATH.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


async def generate_metadata(
    llm: OpenAILLM, prompt_template: str, template: MemegenTemplate
) -> dict[str, Any]:
    prompt = prompt_template.format(context=template.prompt_context)
    context = Context(
        request_id="meme-registry",
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
    MemeTemplate(**payload)
    return payload


async def main() -> None:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is required.")
    prompt_template = load_prompt_template()
    registry = load_registry()
    async with httpx.AsyncClient(timeout=30.0) as client:
        templates = await fetch_memegen_templates(client)
        filtered = [
            template
            for template in templates
            if template.source and "knowyourmeme" in template.source
        ]
        llm = OpenAILLM(api_key=api_key)
        for template in filtered:
            if template.id in registry:
                continue
            payload = await generate_metadata(llm, prompt_template, template)
            registry[template.id] = payload
            save_registry(registry)
        await llm.aclose()


if __name__ == "__main__":
    asyncio.run(main())
