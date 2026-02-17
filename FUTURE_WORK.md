# Future Work - Meme Pipeline & Shitpost System

This document outlines planned improvements and refactoring opportunities for the meme generation and shitpost systems.

## High Priority

### 1. Context-Aware Shitpost Refactoring

**Status**: ✅ Phase 1 & 2 Complete, Phase 3 Pending

**Completed**:
- `ShitpostContext` model implemented in `src/clanker/shitposts/models.py`
- `render_meme_text()` now accepts `ShitpostContext`
- Voice transcript integration via `TranscriptBuffer`
- Channel message context fetching

**Remaining (Phase 3 - New Commands)**:
- `/shitpost-here` - Generate meme based on current thread/channel context
- `/shitpost-vc` - Generate meme based on recent voice conversation
- `/auto-meme` - Auto-generate memes on high engagement (e.g., 5+ reactions)

**Considerations**:
- Privacy: Need user awareness/consent for using conversation history
- Prompt engineering: Different context types need different prompt structures
- Quality: Conversation context is noisier than explicit topics

---

### 2. Prompt Engineering Improvements

**Current State**: Basic prompt in `shitpost_meme_generation.yaml` with minimal guidance.

**Opportunities**:

#### Tone & Style Guidance
```yaml
template: |
  You are an expert memer and shitposter. Your task is to create meme text that:
  1. Matches the format and tone shown in the examples EXACTLY
  2. Incorporates the topic naturally into the meme structure
  3. Is concise (< 50 characters per line for readability)
  4. Would be funny to someone familiar with this meme format
  5. Uses internet culture vernacular appropriately

  Meme: {variant}
  When to use: {applicable_context}

  Topic: {topic}

  Study these examples carefully - match their style:
  {examples}

  {additional_prompt_instructions}

  Generate EXACTLY {text_slots} strings. Return ONLY a JSON list of strings.
```

#### Few-Shot Improvements
- Currently shows examples as JSON dump
- Could format examples more clearly with numbering
- Add "bad example" / "good example" pairs for contrast

#### Template-Specific Instructions
Leverage `additional_prompt_instructions` more:
```json
{
  "astronaut": {
    "additional_prompt_instructions": "The second line MUST be 'Always has been' - this is the core format of the meme."
  }
}
```

---

### 3. Registry Maintenance & Updates

**Needed**:
- Regular runs of `generate_memes.py` to add new templates
- Automated example quality improvement via `update_memes_examples.py`
- CI job to run `validate_registry.py` on PRs
- Periodic review of disabled templates (can some be re-enabled?)

**Implementation**:
```yaml
# .github/workflows/validate-memes.yml
name: Validate Meme Registry
on: [push, pull_request]
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Validate registry
        run: uv run python scripts/validate_registry.py
```

**Scheduled Updates**:
- Monthly: Run `generate_memes.py` to add new templates
- Quarterly: Run `update_memes_examples.py` for quality improvement
- As needed: Review validation errors and fix

---

## Medium Priority

### 4. Smarter Template Selection

**Current**: Random template selection from all enabled templates.

**Opportunity**: Use `applicable_context` field for relevance matching.

**Approaches**:

#### A. Embedding-Based Similarity
```python
async def select_best_template(
    templates: list[MemeTemplate],
    topic: str,
    embedding_model: EmbeddingModel
) -> MemeTemplate:
    """Select template most semantically similar to topic."""
    topic_embedding = await embedding_model.embed(topic)

    scored = []
    for template in templates:
        context_embedding = await embedding_model.embed(template.applicable_context)
        similarity = cosine_similarity(topic_embedding, context_embedding)
        scored.append((template, similarity))

    # Return top match, or random if similarity too low
    top_template, top_score = max(scored, key=lambda x: x[1])
    if top_score > 0.6:
        return top_template
    return random.choice(templates)  # Fallback
```

#### B. LLM-Based Selection
```python
async def select_best_template_llm(
    templates: list[MemeTemplate],
    topic: str,
    llm: LLM
) -> MemeTemplate:
    """Use LLM to pick most appropriate template."""
    options = "\n".join(
        f"- {t.template_id}: {t.applicable_context}"
        for t in templates[:20]  # Limit to avoid token bloat
    )

    prompt = f"""Given the topic "{topic}", which meme is most appropriate?

    Options:
    {options}

    Respond with just the template_id of the best match."""

    response = await llm.generate_simple(prompt)

    # Find template by ID, fallback to random
    for template in templates:
        if template.template_id in response:
            return template

    return random.choice(templates)
```

**Trade-offs**:
- Embedding: Fast, deterministic, requires embedding model
- LLM: Slower, costs tokens, potentially more accurate
- Both: Could use embedding for top-K, then LLM to pick from top-K

---

### 5. Error Handling & Graceful Degradation

**Current Gaps**:
- LLM failures bubble up as exceptions
- Image generation failures crash the command
- No fallbacks for invalid JSON responses

**Improvements**:

```python
# In handle_shitpost()
try:
    lines = await render_meme_text(context, deps.llm, meme_template, topic)
    increment_metric(deps, "meme_generation_success")
except (ValueError, json.JSONDecodeError) as e:
    logger.warning("LLM meme generation failed, using random example", exc_info=True)
    lines = random.choice(meme_template.examples)
    increment_metric(deps, "meme_generation_llm_fallback")
except Exception as e:
    logger.error("Meme generation failed completely", exc_info=True)
    increment_metric(deps, "meme_generation_failure")
    raise

if deps.image:
    try:
        image_payload = await deps.image.generate(...)
        # ... send with image
    except Exception as e:
        logger.warning("Image generation failed, sending text only", exc_info=True)
        increment_metric(deps, "meme_image_fallback")
        await interaction.followup.send(f"🖼️ {caption}\n\n_(image generation failed)_")
```

---

### 6. Example Quality Scoring

**Current**: Binary `examples_updated` flag.

**Opportunity**: Score examples during generation and only keep high-quality ones.

```python
# In update_memes_examples.py

async def score_examples(
    llm: LLM,
    template: MemeTemplate,
    examples: list[list[str]]
) -> dict:
    """Rate example quality 1-10."""
    prompt = f"""Rate these meme examples on a scale of 1-10 based on:
    - Format adherence to the {template.variant} meme
    - Humor quality and effectiveness
    - Representativeness of typical usage

    Template: {template.variant}
    Description: {template.variant_description}

    Examples to rate:
    {json.dumps(examples, indent=2)}

    Return JSON: {{"score": int (1-10), "reasoning": str}}
    """

    response = await llm.generate_simple(prompt)
    return json.loads(response)

# Only save examples with score >= 7
for template_id, template_data in registry.items():
    examples = await generate_examples(llm, template_data)
    score_result = await score_examples(llm, template, examples)

    if score_result["score"] >= 7:
        template_data["examples"] = examples
        template_data["example_quality_score"] = score_result["score"]
        save_registry(registry)
    else:
        logger.info(f"{template_id}: Low quality examples (score={score_result['score']}), retrying...")
```

---

## Lower Priority / Nice to Have

### 7. Template Statistics Dashboard

Visualize template usage and performance:
- Most/least popular templates
- Success/failure rates by template
- Example quality scores over time
- Templates never used (candidates for removal)

**Implementation**: Could be Grafana dashboard, simple web page, or CLI report.

### 8. A/B Testing for Prompts

Test prompt variations to optimize quality:
- Generate same meme with different prompts
- Collect user reactions as implicit feedback
- Automatically select better-performing prompts

### 9. Multi-Template Combos

Allow combining multiple meme formats:
```python
/shitpost-combo topic:"Python vs JavaScript" templates:"drake,change-my-mind"
# Generates both memes about the same topic
```

### 10. User-Submitted Templates

Allow users to contribute new templates via Discord command:
```python
/meme-submit template_id:"my_new_meme" variant:"..." description:"..." examples:"..."
# Saves to pending queue for admin review
```

---

## Technical Debt

### Refactoring Opportunities

1. **Type Safety**: Add stricter type hints to meme generation functions
2. **Validation**: Move registry validation logic into reusable validators
3. **Testing**: Add more integration tests for end-to-end meme generation
4. **Logging**: Add structured logging for better debugging
5. **Async Optimization**: Batch template loading if multiple requests concurrent

### Code Quality

- Add docstrings to all public functions in `memes.py`
- Extract magic numbers (e.g., character limits) to constants
- Consider splitting `memes.py` into smaller modules if it grows further

---

## Decision Log

### Why not use a database for templates?
**Decision**: Keep JSON file for now.

**Reasoning**:
- Simple to edit manually
- Easy to version control
- No additional infrastructure
- Fast enough with caching
- Can migrate to DB later if needed

**Reconsider if**: Registry grows beyond 500 templates or we need runtime updates.

### Why cache the entire registry instead of individual templates?
**Decision**: Cache the full list with `@lru_cache(maxsize=4)`.

**Reasoning**:
- 4 cache slots cover all filter combinations (nsfw × disabled)
- Loading is O(n) anyway (parse full JSON)
- Simpler than granular caching
- Memory overhead negligible (166 templates ≈ few MB)

---

## Contributing

When implementing any of these improvements:

1. Start with smallest testable unit
2. Add tests before implementation
3. Update documentation (especially `docs/meme-pipeline.md`)
4. Run validation: `uv run python scripts/validate_registry.py`
5. Check quality: `make check`
6. Get feedback early via draft PR

For questions or discussion, open an issue tagged `enhancement` or `meme-system`.

---

# Audio & Voice Pipeline

## CI Integration for Real Audio Tests

### Overview

The real audio E2E tests (`tests/test_real_audio.py`) are currently marked `@pytest.mark.network` and skipped in CI. Consider enabling them with an API secret for continuous validation of the transcription pipeline.

### Cost Estimate

OpenAI Whisper API: **$0.006 per minute** of audio

| Test Suite | Audio Duration | Cost per Run |
|------------|----------------|--------------|
| LibriSpeech samples | ~15 seconds | ~$0.0015 |
| AMI Corpus samples | ~4 minutes | ~$0.024 |
| **Total** | ~4.5 minutes | **~$0.03** |

At 100 CI runs/month = **~$3/month**

### Implementation Plan

1. **Add GitHub secret**: `OPENAI_API_KEY` for test runs

2. **Create dedicated test marker**:
   ```python
   @pytest.mark.whisper  # Tests requiring Whisper API
   @pytest.mark.network
   async def test_librispeech_transcription_accuracy(...):
   ```

3. **Update CI workflow**:
   ```yaml
   - name: Run Whisper API tests
     if: github.event_name == 'push' && github.ref == 'refs/heads/main'
     env:
       OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
     run: uv run pytest -m whisper --timeout=120
   ```

4. **Consider cost controls**:
   - Run only on main branch merges (not every PR)
   - Weekly scheduled runs instead of per-commit
   - Cache LibriSpeech downloads in CI artifacts

### Current State

- Real audio tests: `tests/test_real_audio.py` (skipped in CI)
- Synthetic tests: `tests/test_audio_e2e.py` (always run)
- Download script: `scripts/download_test_audio.py`
- Pipeline debugger: `scripts/test_audio_pipeline.py`
- Test data docs: `tests/data/README.md`

---

## Voice-to-Meme Integration Tests

**Status**: ✅ Implemented

Tests implemented in `tests/test_voice_to_meme.py`:
- E2E tests transcribing real audio then generating memes
- LLM-based meme quality scoring (`tests/meme_scoring.py`)
- `MemeScoreResponse` structured output model
- Validates `TranscriptEvent` compatibility with `ShitpostContext`


---

## 2025.12.26 - Bugs & Improvements

### /chat
* In chat threads, the bot doesn't respond in thread after the initial command. It only responds to the command
* It SHOULD read all the messages in the thread and use that as the chat history in the call to the LLM and post the latest response
* Thread name should be improved - currently "clanker-uuid", should be something like "Chat: <topic>" or derive from first message

### /shitpost
* If not already, shitpost context should ignore anything from the bot itself (e.g. text messages, embeds, etc)
* The preview does not show the memegen image, just an embed that says "Generated Shitpost"
  * Ideally, it just shows the image
* Dismiss results in "This interaction failed" - HTTPException: Cannot send an empty message
* There's no UX on regenerate, it just edits the image in place. Instead show "Regenerating..." then a NEW ephemeral post
* The Post only displays the text, not a generated meme (just the LLM meme lines, not the memegen image)

### /transcript
* Remove the display of timestamps (cleaner output)
* If empty, says to use /join - but should only show that message if the bot isn't already in a voice channel

### /speak
* Doesn't do anything - comment it out for now

### /join & Voice
* Join message on VC should have some default messages for join/leave, briefly mention /shitpost
* The shitpost if it's a Text in Chat channel (i.e. the chat channel associated with a voice channel), it should ONLY use the transcriptions for shitposts. If no recent transcripts (within 5 mins), respond ephemerally with message about running /join first

### Silero VAD
* Model should be predownloaded via Docker and loaded on bot startup (avoid torch hub warning)

### VC Features (Future)
* **VC monitoring nudge**: Add a Cog to listen to VC channels in guild. When 2+ people present, send a View to start listening/join. Auto-dismiss after 5 minutes
* **Auto leave**: When no users present, leave/end the voice call

---

## Voice Connection Refactoring: Actor Model

**Status**: ✅ Implemented (behind feature flag `USE_VOICE_ACTOR=1`)

**Implementation Details**:
- `src/clanker_bot/voice_actor.py` (~660 LOC) - Full actor implementation with message types, VoiceStatus enum, VoiceActorSink adapter
- `tests/test_voice_actor.py` (~580 LOC, 56 tests) - Comprehensive test coverage
- Integrated with command handlers (`handle_join`, `handle_leave`)
- Feature flag for gradual rollout: `USE_VOICE_ACTOR=1`

**Remaining Work**:
- Testing in production environment
- Monitor for edge cases and race conditions
- Once stable, deprecate old `voice_ingest.py`/`voice_resilience.py` code

### Problem

The current voice management code is spread across 4 files (~790 LOC) with complex callback chains:

- `voice_ingest.py` - `VoiceIngestWorker`, `VoiceIngestSink`, `VoiceIngestSession`
- `voice_resilience.py` - `VoiceKeepalive`, `VoiceReconnector`, `create_reconnect_handler`
- `discord_adapter.py` - `VoiceSessionManager`, `VoiceSessionState`
- `command_handlers/voice.py` - `_setup_transcription`, disconnect/stale handlers

State is scattered across multiple objects, making it hard to answer "what state are we in?" The callback chain for reconnection loops through 6+ functions across files.

### Proposed Solution: Actor Model

Refactor to a single `VoiceActor` class that:

1. **Owns all state** in one place (status, guild_id, channel_id, buffers, etc.)
2. **Processes messages sequentially** via `asyncio.Queue` (no race conditions)
3. **Eliminates callbacks** — everything is a message (`JoinRequest`, `AudioReceived`, `StaleTimeout`, etc.)
4. **Handles thread boundary naturally** — `Queue.put_nowait()` is thread-safe for `voice_recv.write()`

### Why Actor Model over State Machine

Both patterns were considered. Actor model wins for this use case because:

| Aspect | State Machine | Actor Model |
|--------|--------------|-------------|
| Thread safety | Need locks or `run_coroutine_threadsafe` | `Queue.put_nowait` just works |
| Testing | Call private methods or mock timers | Post messages directly to inbox |
| Debugging | Correlate logs across methods | Message *is* the log |
| Conceptual fit | Better for UI/game loops | Better for event-driven I/O (Discord) |

### Message Types

```python
@dataclass(frozen=True)
class JoinRequest:
    channel_id: int
    guild_id: int
    response_queue: asyncio.Queue[JoinResult]

@dataclass(frozen=True)
class LeaveRequest:
    response_queue: asyncio.Queue[LeaveResult]

@dataclass(frozen=True)
class AudioReceived:
    user_id: int
    pcm_bytes: bytes
    timestamp: datetime

@dataclass(frozen=True)
class StaleTimeout:
    silence_seconds: float

@dataclass(frozen=True)
class DisconnectDetected:
    error: Exception | None

@dataclass(frozen=True)
class ReconnectAttempt:
    attempt: int

@dataclass(frozen=True)
class SendKeepalive:
    pass

@dataclass(frozen=True)
class ProcessBuffers:
    pass
```

### Actor Structure

```python
class VoiceActor:
    def __init__(self, bot: discord.Client, stt: STT) -> None:
        self._inbox: asyncio.Queue[VoiceMessage] = asyncio.Queue()
        # All state in one place
        self._status: VoiceStatus = VoiceStatus.Disconnected
        self._guild_id: int | None = None
        self._channel_id: int | None = None
        self._voice_client: discord.VoiceClient | None = None
        self._audio_buffers: dict[int, bytearray] = {}
        self._last_audio_time: datetime | None = None
        self._reconnect_attempt: int = 0

    async def join(self, channel_id: int, guild_id: int) -> JoinResult:
        """Public API — posts message, waits for response."""
        response_queue: asyncio.Queue[JoinResult] = asyncio.Queue()
        await self._inbox.put(JoinRequest(channel_id, guild_id, response_queue))
        return await response_queue.get()

    def post_audio(self, user_id: int, pcm: bytes) -> None:
        """Called from voice_recv thread — thread-safe."""
        self._inbox.put_nowait(AudioReceived(user_id, pcm, datetime.now()))

    async def run(self) -> None:
        """Main loop — processes one message at a time."""
        async for msg in self._iter_inbox():
            await self._handle(msg)

    async def _handle(self, msg: VoiceMessage) -> None:
        logger.info("voice.msg: status={}, msg={}", self._status, type(msg).__name__)
        match msg:
            case JoinRequest(): ...
            case LeaveRequest(): ...
            case AudioReceived(): ...
            case StaleTimeout(): ...
            case DisconnectDetected(): ...
            case ReconnectAttempt(): ...
            case SendKeepalive(): ...
            case ProcessBuffers(): ...
```

### Benefits

1. **Single log point captures everything** — message queue is the audit log
2. **Testing is straightforward** — post messages, assert state
3. **Reconnect flow is explicit** — each attempt is a `ReconnectAttempt` message
4. **Message history for debugging** — can keep last N messages for post-mortem
5. **Natural fit for Discord** — already event-driven, this aligns with that model

### File Structure After Refactor

```
voice_actor.py (~400 LOC)     - VoiceActor, VoiceStatus, message types
voice_sink.py (~100 LOC)      - Thin adapter that posts to actor's queue
transcript_buffer.py (~80 LOC) - TranscriptBuffer (unchanged)
command_handlers/voice.py (~80 LOC) - Simplified: just calls actor.join()/leave()
```

### Implementation Notes

- Start with a parallel implementation alongside existing code
- Add feature flag to switch between old/new implementations
- Migrate one path at a time (join → leave → reconnect → stale detection)
- Remove old code once new implementation is stable
