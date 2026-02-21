"""Task definitions for gskill optimization.

Each task is a dict with:
  id          - unique identifier
  description - the question/task posed to the agent
  oracle_keys - substrings that should appear in a correct agent response
                (score = fraction of keywords present)
"""

from __future__ import annotations

Task = dict[str, object]

# ---------------------------------------------------------------------------
# Training set — GEPA sees these during optimization
# ---------------------------------------------------------------------------

TASK_RUN_TESTS: Task = {
    "id": "run_tests",
    "description": (
        "What is the exact shell command to run clanker's unit tests, "
        "excluding network tests? Be specific about the tool and flags."
    ),
    "oracle_keys": ["pytest", "not network"],
}

TASK_ADD_CLI_COMMAND: Task = {
    "id": "add_cli_command",
    "description": (
        "I want to add a new CLI command called `ping` to clanker. "
        "It should accept an optional prompt argument and call the LLM, "
        "then print 'pong: {response}'. "
        "Show the complete contents of `src/clanker/cli/commands/ping.py` "
        "following the existing patterns exactly."
    ),
    "oracle_keys": [
        "@click.command",
        "click.pass_obj",
        "run_async",
        "CliContext",
        "respond",
        "TransientProviderError",
    ],
}

TASK_WRITE_CLI_TEST: Task = {
    "id": "write_cli_test",
    "description": (
        "Show me how to write a pytest test class for the new `ping` CLI command "
        "in `tests/cli/test_commands.py`. Include: a basic invocation test and a "
        "test for missing-prompt error handling."
    ),
    "oracle_keys": [
        "CliRunner",
        "_patch_factory",
        "FakeLLM",
        "runner.invoke",
        "exit_code",
    ],
}

TRAIN_TASKS: list[Task] = [
    TASK_RUN_TESTS,
    TASK_ADD_CLI_COMMAND,
    TASK_WRITE_CLI_TEST,
]

# ---------------------------------------------------------------------------
# Validation set — GEPA uses these to measure generalization
# ---------------------------------------------------------------------------

TASK_REGISTER_COMMAND: Task = {
    "id": "register_command",
    "description": (
        "After creating `src/clanker/cli/commands/ping.py`, "
        "what exact changes do I make to `src/clanker/cli/main.py` "
        "to register the new command?"
    ),
    "oracle_keys": [
        "cli.add_command",
        "from .commands",
        "noqa",
    ],
}

TASK_ADD_PROVIDER: Task = {
    "id": "add_provider",
    "description": (
        "How do I register a new LLM provider called 'anthropic' "
        "in `src/clanker/providers/factory.py`? "
        "Show the exact lines to add, including where to add the import "
        "and how to register it in the factory registry."
    ),
    "oracle_keys": [
        "_llm_registry",
        "factory.py",
        "_require_env",
        "api_key",
    ],
}

VAL_TASKS: list[Task] = [
    TASK_REGISTER_COMMAND,
    TASK_ADD_PROVIDER,
]

ALL_TASKS: list[Task] = TRAIN_TASKS + VAL_TASKS
