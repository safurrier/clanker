# Clanker9000 Repository Review

## Overview

This document captures a deeper pass over the Clanker9000 Discord bot repo. It expands the high-level grades from the earlier review into actionable design, implementation, testing, and documentation work streams.

## Design (Current Grade: B-, Target: A)

- **Persona-Aware Provider Routing**  
  Persona config allows per-persona provider overrides, but `build_dependencies` ignores them and always uses global defaults. Refactor dependency wiring so each persona can supply specific LLM/STT/TTS/image providers. Fail the build early when a persona references an unknown provider or missing API key.
- **Explicit Layering Between SDK and Bot**  
  The split between `src/clanker` and `src/clanker_bot` is solid, but the Discord-facing layer still owns core orchestration (e.g., replay logging, policy wiring). Extract an orchestration module inside the SDK so Discord, CLI, or future adapters share the same workflow.
- **Replay / Voice Pipeline Documentation**  
  Formalize the contracts for replay-log records and the voice ingestion pipeline. A diagram that traces chat, TTS, and voice-ingest flows (including config precedence) will help future contributors reason about extensions.

## Implementation (Current Grade: C+, Target: A)

- **Voice Ingest Payload Handling**  
  `VoiceIngestWorker` slices raw PCM and forwards it straight to `STT.transcribe`, but providers like OpenAISTT expect audio containers (e.g., WAV, MP3). Add a helper that wraps each chunk in a WAV header (using Python’s `wave` module or manual struct packing) before upload. Update the STT protocol docstring to clarify expectations.
- **Error Resilience in Slash Commands**  
  `handle_chat` / `handle_speak` / `handle_shitpost` propagate `ValueError` (policy) or `ProviderError` directly, causing Discord to show “interaction failed.” Guard each path, map errors to human-friendly ephemeral responses, and log the exception context (request id, guild id, provider name).
- **Config and Tooling Alignment**  
  The repo syncs against Python 3.12, but `ruff` and `ty` are configured for Python 3.9. Update target versions, ensure CI uses the same interpreter, and document the supported runtime. While here, catch `httpx.RequestError` in providers and convert to `TransientProviderError` so upstream error handling remains consistent.
- **Operational Polishing**  
  Harden replay logging by catching filesystem errors (disk full, permission issues) so a bad write doesn’t drop the whole interaction. Review `VoiceSessionManager.join` to prevent concurrent joins (e.g., two slash commands racing) and ensure state resets cleanly when connections fail.

## Testing (Current Grade: B, Target: A)

- **Provider Failure Cases**  
  Expand coverage around retry logic (e.g., `TransientProviderError` path in LLM/STT, memegen API failures). Use `httpx.MockTransport` to simulate 429/500 + connectivity exceptions.
- **Voice Pipeline Verification**  
  Add deterministic tests for the new WAV wrapping helper. Ensure `detect_speech_segments` plus `chunk_segments` feeding the STT adapter yields round-trippable audio chunks and populates metadata correctly via `build_context_from_event`.
- **Network Smoke Tests as Opt-In**  
  Convert blocking `time.sleep` calls in async helpers to `await asyncio.sleep`. Introduce a dedicated pytest marker and default skip logic so real OpenAI tests only run when explicitly enabled via CLI/CI.
- **Persona Override Tests**  
  Once provider overrides are implemented, add tests that prove persona-specific providers are selected and error when configuration references missing providers.

## Documentation (Current Grade: D, Target: A)

- **Rewrite Front-Matter**  
  Replace the template-focused README and MkDocs landing page with Clanker-specific content: feature overview, command list, architecture summary, configuration instructions, and deployment flow.
- **Configuration and Operations Guides**  
  Document environment variables (`DISCORD_TOKEN`, `CLANKER_CONFIG_PATH`, provider keys), persona/provider override behavior, and voice ingest prerequisites. Include operational guidance: health endpoint usage, metrics snapshot, replay log inspection.
- **Testing & Troubleshooting Section**  
  Add a page outlining standard testing commands, how to run smoke tests, and common failure modes (missing API keys, policy rejections, voice ingest setup).
- **Keep Docs in Sync via CI**  
  Ensure `make docs-check` runs in CI (`docs.yml`) and badges link to active workflows/coverage. Consider auto-publishing docs once content matches the bot.

## Suggested Work Sequencing

1. **Implementation remediation** (voice ingest, error handling, tooling alignment) so new tests/docs can anchor to the updated behavior.
2. **Testing expansion** covering happy- and failure-path scenarios, including persona overrides and provider retries.
3. **Documentation overhaul** once the code paths are stable.
4. **Design formalization**—update architecture docs and diagrams to reflect the refined layering and pipeline behaviors.

Executing these streams will close the gap to A-level scores across all categories while making the project easier to maintain and extend.
