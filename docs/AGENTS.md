# docs/ Agent Routing Index

Documentation files in this directory, classified by type and audience.

## How-To Guides (task-oriented)

| File | Description |
|------|-------------|
| `QUICKSTART.md` | Install, configure, and run the bot |
| `CONTRIBUTING.md` | Development setup, code standards, PR workflow |
| `container-setup.md` | Docker/Podman development environment |
| `voice-debugging.md` | Debug voice pipeline issues with capture system |

## Explanation (understanding-oriented)

| File | Description |
|------|-------------|
| `ARCHITECTURE.md` | System design, components, data flows, design decisions |
| `audio-capture.md` | Voice pipeline: VAD, utterance grouping, transcription |
| `meme-pipeline.md` | Meme registry, LLM generation, Memegen integration |
| `voice_ingest_pipeline.md` | V1 voice ingest design notes |
| `transcript-examples.md` | Real-world conversation output scenarios |

## Reference

| File | Description |
|------|-------------|
| `config_schema.md` | Configuration YAML schema |
| `discordpy_notes.md` | discord.py patterns and gotchas |
| `reference/api.md` | Auto-generated API docs (mkdocstrings) |
| `FUTURE_WORK.md` | Planned improvements (symlink to root) |

## Agent-Facing Documentation

Detailed agent docs live in `agent_docs/` (separate from human-facing docs):
- `agent_docs/architecture.md` - Deep architecture reference
- `agent_docs/testing.md` - Testing strategy and fixtures
- `agent_docs/voice-pipeline.md` - Voice pipeline internals
- `agent_docs/providers.md` - Provider system details
