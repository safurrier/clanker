"""GEPA evaluator for gskill.

Evaluates a candidate SKILL.md by:
1. Injecting it as the system prompt for an OpenAI agent
2. Posing each task's description as the user message
3. Scoring the response by checking oracle keywords

Evaluator signature matches GEPA's generalization mode:
    evaluate(candidate: str, example: Task) -> float
"""

from __future__ import annotations

import os

import gepa.optimize_anything as oa
from openai import OpenAI

from scripts.gskill.tasks import Task

# Model used for the coding agent being evaluated.
# Cheap and fast — we want to measure skill quality, not raw model power.
AGENT_MODEL = os.getenv("GSKILL_AGENT_MODEL", "gpt-4o-mini")

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. "
                "Export it before running gskill: export OPENAI_API_KEY=sk-..."
            )
        _client = OpenAI(api_key=api_key)
    return _client


def evaluate(skill: str, task: Task) -> tuple[float, dict[str, str]]:
    """Score a candidate skill on a single task.

    Args:
        skill:  The candidate SKILL.md text (optimized by GEPA).
        task:   A task dict with ``id``, ``description``, ``oracle_keys``.

    Returns:
        (score, side_info) where score in [0, 1] and side_info feeds
        GEPA's reflection step with diagnostic context.
    """
    client = _get_client()

    response = client.chat.completions.create(
        model=AGENT_MODEL,
        messages=[
            {"role": "system", "content": skill},
            {"role": "user", "content": task["description"]},
        ],
        temperature=0.0,
        max_tokens=600,
    )
    answer = (response.choices[0].message.content or "").strip()

    oracle_keys: list[str] = task["oracle_keys"]  # type: ignore[assignment]
    hits = [kw for kw in oracle_keys if kw.lower() in answer.lower()]
    misses = [kw for kw in oracle_keys if kw.lower() not in answer.lower()]
    score = len(hits) / len(oracle_keys) if oracle_keys else 1.0

    oa.log(f"Task: {task['id']}")
    oa.log(f"Score: {score:.2f}  hits={hits}  misses={misses}")
    oa.log(f"Agent answer (first 300 chars): {answer[:300]}")

    side_info = {
        "task_id": str(task["id"]),
        "score": f"{score:.2f}",
        "hits": str(hits),
        "misses": str(misses),
        "answer_preview": answer[:400],
    }
    return score, side_info
