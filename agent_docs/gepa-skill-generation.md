# GEPA Skill Generation: A Generalized Playbook

How to bootstrap, evolve, and validate reusable AI coding skills for any repository.
Intended for: AI coding harnesses running automated loops **and** humans reviewing or authoring skills.

---

## What Problem This Solves

AI coding agents working on a new codebase make the same category of mistakes repeatedly:

- Wrong import paths or module structure assumptions
- Missed project conventions (naming, async patterns, test fakes)
- Correct logic but failing type checks or lint rules
- Re-discovering how to wire a new component from scratch each time

A **skill** is a short, distilled prompt fragment — written in plain text — that front-loads those hard-won patterns so the agent gets them right on the first attempt instead of the third. GEPA (Generalized Evolutionary Prompt Architecture) is a loop that *generates* and *improves* those skills using real task success/failure as the fitness signal.

The output is a skill document (or set of them) that lives alongside the codebase and is injected into the agent's context at task time.

---

## When to Use This

| Situation | GEPA ROI |
|-----------|----------|
| New codebase, few or no docs | High — skills encode what models discover |
| Well-documented repo with a good CLAUDE.md / AGENTS.md | Low — docs already do the job |
| Repeated failures in a specific subsystem (voice, DB, auth) | High — targeted sub-skill pays off immediately |
| One-off task | None — not worth the overhead |
| CI with automated test oracles | High — clean feedback signal |

Rule of thumb: if `make check` passes reliably on first-attempt implementations, you don't need GEPA yet.

---

## Prerequisites

Before starting the loop you need three things:

1. **An oracle** — a command that returns pass/fail objectively. Usually your test suite (`make test`, `pytest`, `go test ./...`). No oracle = no signal.
2. **A task bank** — a list of representative coding tasks the agent should be able to do. 10–30 tasks is enough to start.
3. **A baseline** — one run of the agent on each task *without* any skill, so you have a before-number.

---

## Step-by-Step

### Step 0 — Audit the repo

Before generating any skill, read the codebase structure and existing docs. The goal is to avoid duplicating what's already written.

**For an AI harness:**
```
Read CLAUDE.md, AGENTS.md (all nested), and any agent_docs/ directory.
List: what conventions are documented? What is NOT documented?
Output: a gap list — conventions that exist in code but not in any doc.
```

**For a human:**
- Walk the directory tree
- Read the most complex existing implementation (not the simplest)
- Note every "oh, I wouldn't have guessed that" moment — those are skill candidates

### Step 1 — Define the task bank

Tasks should be:
- **Representative** of real work (not trivial, not heroic)
- **Independently verifiable** by the oracle
- **Varied** across the codebase surface

Example task bank entry format:
```
TASK_ID: add-anthropic-provider
DESCRIPTION: Add a new LLM provider for Anthropic Claude that implements the LLM protocol.
ORACLE: make check
REFERENCE_IMPL: (path to a reference implementation if one exists, else null)
```

Aim for tasks that exercise different modules. For this repo: one provider task, one CLI command task, one shitpost/persona task, one DB query task, one voice pipeline task.

### Step 2 — Run the baseline

Run the agent on every task with zero skill injection. Record:
- Pass rate (oracle green / total)
- Where failures occur (lint? type check? test assertion? import error?)
- Time-to-pass if you have retries enabled

This is your before number. Keep the raw outputs — you'll mine them for skill content.

### Step 3 — Mine failures for skill content

For each failed run, categorize the error. Common clusters:

| Cluster | Example Error | Skill Content to Write |
|---------|--------------|----------------------|
| Import convention | `ModuleNotFoundError` on wrong path | Correct import paths and module layout |
| Protocol mismatch | Type error on provider method signature | Copy the exact Protocol definition |
| Async mistake | `RuntimeWarning: coroutine never awaited` | "All I/O is async; use `await`" |
| Test pattern | Test fails because no fake used | Show the fake pattern and where fakes live |
| Lint rule | `ruff` error on line length or import order | State the rule explicitly |
| Missing wiring | Feature works but isn't registered | Show the registration step explicitly |

Write one skill section per cluster. Be concrete — show code, not prose.

### Step 4 — Draft the first skill

Structure:

```markdown
# Skill: <name>

## Context
One sentence: what this skill is for and when to apply it.

## Patterns

### <Pattern Name>
<Explanation — 1-3 sentences max>

\`\`\`python
# Concrete minimal example
\`\`\`

### <Pattern Name>
...

## Anti-Patterns
- Don't do X because Y
- Never use Z, use W instead

## Checklist
- [ ] Step 1
- [ ] Step 2
- [ ] Step 3
```

Keep it short. A skill that fits in 100 lines gets read. One that's 400 lines gets skimmed and missed.

### Step 5 — Run the loop (evolutionary phase)

This is the core GEPA loop. Each iteration:

```
1. Inject current skill into agent context
2. Run agent on full task bank
3. Collect oracle results
4. Diff pass rate vs previous iteration
5. If improved: keep changes, note what helped
6. If no improvement: revert or branch
7. Mine new failures for additional skill content
8. Goto 1
```

For an AI harness, steps 1–4 are automated. Steps 5–7 can be automated with a simple comparator. Step 8 requires either a human or a second LLM pass analyzing the failure diffs.

**Stopping criteria** (pick one or combine):
- Pass rate plateaus for 3+ iterations
- Pass rate exceeds 90%
- Diminishing returns: last 3 iterations each improved by <2%

### Step 6 — Validate generalization

The skill might be overfit to your task bank. Before shipping:

1. Hold out 20% of tasks from the start (don't use them in training)
2. After the loop converges, run on the held-out set
3. If held-out pass rate is within 5% of training pass rate: skill generalizes
4. If held-out is much worse: the skill is too task-specific — generalize the language

### Step 7 — Write the final skill

After the loop, the skill document has accumulated edits. Clean it up:
- Remove anything that didn't move the pass rate
- Consolidate redundant sections
- Add a one-line summary at the top for fast scanning
- Verify all code examples still match the current codebase

### Step 8 — Integrate

**Option A: Standalone skill file**
Drop it in `agent_docs/` or alongside the relevant module's `AGENTS.md`. Reference it from the root `CLAUDE.md`.

**Option B: Inline into existing docs**
If the skill is small (< 30 lines), merge it into the existing relevant doc. Avoid doc sprawl.

**Option C: Harness injection**
If your CI/CD harness injects context at runtime, register the skill there so it's available to all future agent runs automatically.

### Step 9 — Maintain

Skills rot. When the codebase changes:
- Run a quick oracle pass after any major refactor
- If pass rate drops, treat it as a bug in the skill and re-run a short loop (2–3 iterations)
- Version-control the skill alongside the code — PRs that change patterns should update the skill

---

## Special Case: Targeted Sub-Skills

If one subsystem has a disproportionate failure rate, write a focused sub-skill just for that area instead of bloating the root skill.

Example triggers:
- Voice pipeline tasks fail 60% of the time but everything else passes
- DB query tasks always fail because of sqlc-specific patterns

Sub-skill files live next to the module (`src/clanker/voice/AGENTS.md`, etc.) and are only injected when the task touches that module. This keeps context lean.

---

## What Makes a Good Oracle

The oracle is the most important part. Bad oracles produce bad skills.

| Oracle Quality | Example | Problem |
|---------------|---------|---------|
| **Excellent** | `pytest tests/` with no mocks | Tests real behavior |
| **Good** | `make check` (lint + types + tests) | Catches style issues too |
| **Marginal** | "Does the file exist and have the right function name?" | Misses logic errors |
| **Bad** | LLM-as-judge on output text | High variance, not deterministic |

If your only oracle is an LLM judge, run it 3x per task and take majority vote to reduce noise.

---

## Prompt Template for the Harness

When injecting the skill into the agent at task time:

```
<skill name="<skill-name>">
<contents of skill file>
</skill>

<task>
<task description>
</task>

Implement the task. Follow all patterns in the skill above.
After implementing, verify against the oracle: <oracle command>.
```

If the oracle fails, the harness can optionally re-run with the failure output appended:
```
<oracle-failure>
<stdout/stderr of failed oracle run>
</oracle-failure>

Fix the implementation so the oracle passes.
```

Do not retry more than 2–3 times without human review — repeated failures on the same task signal a gap in the skill, not a transient error.

---

## Quick Reference Checklist

**Setup:**
- [ ] Identify the oracle command
- [ ] Build a 10–30 task bank
- [ ] Run baseline (no skill)
- [ ] Record baseline pass rate

**Loop:**
- [ ] Mine failure clusters from baseline
- [ ] Draft skill (< 100 lines)
- [ ] Run loop until plateau or >90% pass rate
- [ ] Validate on held-out tasks

**Ship:**
- [ ] Clean up skill document
- [ ] Remove anything that didn't help
- [ ] Integrate into agent_docs/ or AGENTS.md
- [ ] Set up maintenance trigger (re-run on major refactors)

---

## This Repo Specifically

For **Clanker9000**, the highest-value skill targets are:

1. **Adding a new provider** — the Protocol + factory + registration pattern is non-obvious and not fully shown end-to-end in any doc
2. **Voice pipeline changes** — VAD thresholds, async chunker, resampling — the existing `voice-pipeline.md` is good but partial
3. **DB query flow** — sqlc generation + placeholder fix script is a multi-step process agents reliably botch

For everything else (adding CLI commands, new personas, shitpost templates), `CLAUDE.md` is already sufficient and a skill would be redundant.
