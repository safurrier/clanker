# gskill — automatically learn a SKILL.md for clanker

A lightweight replication of the [GEPA gskill pipeline][blog] applied to this
Discord bot codebase. It uses [GEPA's `optimize_anything` API][gepa] to
iteratively improve a markdown skill document that helps AI coding agents work
effectively in this repo.

[blog]: https://gepa-ai.github.io/gepa/blog/2026/02/18/automatically-learning-skills-for-coding-agents/
[gepa]: https://gepa-ai.github.io/gepa/guides/quickstart/

## What it does

```
seed_skill.md  ──►  GEPA optimize_anything  ──►  .claude/skills/clanker/SKILL.md
                         ▲             │
                         │   reflect   │
                         └─────────────┘
                    (agent answers tasks;
                     score = oracle keyword hits)
```

1. **Seed skill** (`seed_skill.md`) — a human-authored starting point covering
   how to run tests, add CLI commands, write CLI tests, and add providers.

2. **Tasks** (`tasks.py`) — 5 verifiable questions split into train (3) and
   validation (2) sets. Each task has oracle keywords that should appear in a
   correct agent answer.

3. **Evaluator** (`evaluator.py`) — calls OpenAI with the candidate skill as
   the system prompt and each task description as the user message; returns the
   fraction of oracle keywords found in the response.

4. **Optimizer** (`optimize.py`) — runs GEPA's evolutionary search, using a
   more capable reflector LLM to propose improvements to the skill based on
   pass/fail patterns across tasks.

## Setup

```bash
pip install gepa
export OPENAI_API_KEY=sk-...
```

## Usage

```bash
# Dry-run: score the seed skill without optimization
python -m scripts.gskill.optimize --dry-run

# Run full optimization (20 evaluator calls by default)
python -m scripts.gskill.optimize

# More calls for better results
python -m scripts.gskill.optimize --max-calls 50

# Use a different agent model
python -m scripts.gskill.optimize --agent-model gpt-4o --reflection-model openai/gpt-4o
```

The best skill is saved to `.claude/skills/clanker/SKILL.md`.

## Tasks

| ID | Type | Oracle keywords |
|----|------|----------------|
| `run_tests` | Knowledge | `pytest`, `not network` |
| `add_cli_command` | Code gen | `@click.command`, `click.pass_obj`, `run_async`, `CliContext`, `respond`, `TransientProviderError` |
| `write_cli_test` | Code gen | `CliRunner`, `_patch_factory`, `FakeLLM`, `runner.invoke`, `exit_code` |
| `register_command` | Knowledge | `cli.add_command`, `from .commands`, `noqa` |
| `add_provider` | Knowledge | `_llm_registry`, `factory.py`, `_require_env`, `api_key` |

## Relation to gskill / SWE-smith

The original gskill uses [SWE-smith][swesmith] to generate ~300 Docker-backed
tasks with executable test oracles. This implementation uses 5 hand-crafted
tasks with keyword oracles instead — sufficient to demonstrate the GEPA
optimization loop without requiring Docker or external CI infrastructure.

[swesmith]: https://github.com/SWE-bench/SWE-smith

## Files

```
scripts/gskill/
  __init__.py        package marker
  seed_skill.md      initial human-authored skill
  tasks.py           train/val task definitions
  evaluator.py       GEPA evaluator (OpenAI agent + oracle scoring)
  optimize.py        main optimization script
  README.md          this file

.claude/skills/clanker/
  SKILL.md           output: best skill found by GEPA
```
