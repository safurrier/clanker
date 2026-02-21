"""gskill: automatically learn a SKILL.md for the clanker codebase.

Implements the gskill pipeline from the GEPA paper:
  https://gepa-ai.github.io/gepa/blog/2026/02/18/automatically-learning-skills-for-coding-agents/

Pipeline
--------
1. Load a seed SKILL.md (human-written starting point)
2. Use GEPA's optimize_anything in "generalization" mode:
   - dataset  = training tasks (3 tasks)
   - valset   = validation tasks (2 tasks)
   - evaluator = call an OpenAI agent with skill as system prompt,
                 score response against oracle keywords
3. Save the best SKILL.md to .claude/skills/clanker/SKILL.md

Usage
-----
    export OPENAI_API_KEY=sk-...
    python -m scripts.gskill.optimize [--max-calls N] [--agent-model MODEL]

    # Verify pipeline structure without any API calls:
    python -m scripts.gskill.optimize --dry-run --mock

    # Score seed skill via real LLM agent (requires valid OPENAI_API_KEY):
    python -m scripts.gskill.optimize --dry-run

Options
-------
    --max-calls N       Maximum GEPA evaluator calls (default: 20)
    --agent-model MODEL OpenAI model for the coding agent (default: gpt-4o-mini)
    --reflection-model  LiteLLM model string for GEPA's reflector (default: openai/gpt-4o-mini)
    --dry-run           Score seed skill without full optimization; print results and exit
    --mock              With --dry-run: check oracle keywords in seed text directly (no API)
    --output PATH       Where to save the best skill (default: .claude/skills/clanker/SKILL.md)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Make sure the repo root is on sys.path when run as a script
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from gepa.optimize_anything import GEPAConfig, EngineConfig, optimize_anything, ReflectionConfig

from scripts.gskill.evaluator import evaluate
from scripts.gskill.tasks import TRAIN_TASKS, VAL_TASKS

_SEED_SKILL_PATH = Path(__file__).parent / "seed_skill.md"
_DEFAULT_OUTPUT = _REPO_ROOT / ".claude" / "skills" / "clanker" / "SKILL.md"

OBJECTIVE = (
    "Optimize a SKILL.md document that helps AI coding agents answer questions "
    "and complete implementation tasks in the Clanker9000 Discord bot SDK codebase. "
    "The skill should provide accurate, actionable guidance on: running tests, "
    "adding CLI commands, writing tests for CLI commands, registering commands, "
    "and adding providers. Agents using this skill should be able to produce "
    "correct commands, code skeletons, and file references on the first attempt."
)


def _score_seed_mock(seed: str) -> None:
    """Check oracle keywords in the seed skill text itself without any API calls.

    This verifies the seed_skill.md has good coverage before spending API budget.
    """
    print("(mock mode: checking oracle keywords in seed_skill.md directly)\n")
    for task in TRAIN_TASKS + VAL_TASKS:
        oracle_keys: list[str] = task["oracle_keys"]  # type: ignore[assignment]
        hits = [kw for kw in oracle_keys if kw.lower() in seed.lower()]
        misses = [kw for kw in oracle_keys if kw.lower() not in seed.lower()]
        score = len(hits) / len(oracle_keys) if oracle_keys else 1.0
        status = "PASS" if score == 1.0 else "PARTIAL" if score > 0 else "FAIL"
        print(
            f"[{task['id']}] {status}  score={score:.2f}  "
            f"hits={hits}  misses={misses}"
        )
    print(
        "\nMock seed check complete. "
        "Run without --mock (valid OPENAI_API_KEY required) "
        "to score via an LLM agent."
    )


def _score_seed(seed: str) -> None:
    """Dry-run: score the seed skill via LLM agent against all tasks."""
    print("=== Dry-run: scoring seed skill via LLM agent ===\n")
    for task in TRAIN_TASKS + VAL_TASKS:
        score, info = evaluate(seed, task)
        print(
            f"[{task['id']}] score={score:.2f}  "
            f"hits={info['hits']}  misses={info['misses']}"
        )
    print("\nSeed scored. Run without --dry-run to start GEPA optimization.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="gskill: learn a SKILL.md with GEPA")
    parser.add_argument(
        "--max-calls",
        type=int,
        default=20,
        help="Maximum evaluator calls for GEPA optimization (default: 20)",
    )
    parser.add_argument(
        "--agent-model",
        default="gpt-4o-mini",
        help="OpenAI model for the coding agent (default: gpt-4o-mini)",
    )
    parser.add_argument(
        "--reflection-model",
        default="openai/gpt-4o-mini",
        help="LiteLLM model string for GEPA's reflector (default: openai/gpt-4o-mini)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Score seed skill without full optimization and exit",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="With --dry-run: check oracle keywords in seed text directly (no API calls)",
    )
    parser.add_argument(
        "--output",
        default=str(_DEFAULT_OUTPUT),
        help=f"Output path for best skill (default: {_DEFAULT_OUTPUT})",
    )
    args = parser.parse_args(argv)

    # Set agent model via env var (picked up by evaluator.py)
    os.environ.setdefault("GSKILL_AGENT_MODEL", args.agent_model)

    seed = _SEED_SKILL_PATH.read_text()

    if args.dry_run:
        if args.mock:
            _score_seed_mock(seed)
        else:
            _score_seed(seed)
        return

    if not os.environ.get("OPENAI_API_KEY"):
        print(
            "ERROR: OPENAI_API_KEY is not set.\n"
            "Set it to run optimization, or use --dry-run to skip API calls.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Starting gskill optimization on clanker")
    print(f"  Train tasks : {[t['id'] for t in TRAIN_TASKS]}")
    print(f"  Val tasks   : {[t['id'] for t in VAL_TASKS]}")
    print(f"  Agent model : {args.agent_model}")
    print(f"  Reflector   : {args.reflection_model}")
    print(f"  Max calls   : {args.max_calls}")
    print()

    result = optimize_anything(
        seed_candidate=seed,
        evaluator=evaluate,
        dataset=TRAIN_TASKS,
        valset=VAL_TASKS,
        objective=OBJECTIVE,
        config=GEPAConfig(
            engine=EngineConfig(
                max_metric_calls=args.max_calls,
                display_progress_bar=True,
                # Keep it deterministic across runs
                seed=42,
            ),
            reflection=ReflectionConfig(
                reflection_lm=args.reflection_model,
            ),
        ),
    )

    # Save best skill
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    best_skill: str = result.best_candidate  # type: ignore[assignment]
    output_path.write_text(best_skill)

    print(f"\n=== Optimization complete ===")
    print(f"Best validation score : {result.best_score:.3f}")
    print(f"Skill saved to        : {output_path}")
    print()
    print("To use the skill with Claude Code, point it at the skill file:")
    print(f"  cat {output_path}")


if __name__ == "__main__":
    main()
