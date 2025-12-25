# Future Work - Meme Pipeline & Shitpost System

This document outlines planned improvements and refactoring opportunities for the meme generation and shitpost systems.

## High Priority

### 1. Context-Aware Shitpost Refactoring

**Current State**: The shitpost command only accepts `topic: str` as input, which limits it to explicit user-provided topics.

**Problem**: The bot has access to much richer contextual information that could make shitposts more relevant:
- Voice channel transcripts
- Thread conversation history
- Recent channel messages
- User reactions/engagement patterns

**Proposed Solution**: Refactor to use a generic "input context" model instead of just topic string.

#### Implementation Plan

**Phase 1: Create Context Model**
```python
@dataclass(frozen=True)
class ShitpostContext:
    """Context for generating contextual shitposts."""

    # Primary input (one of these should be set)
    explicit_topic: str | None = None
    conversation_transcript: str | None = None
    thread_messages: list[Message] | None = None

    # Metadata
    channel_type: str | None = None  # "voice", "text", "thread"
    user_id: int | None = None
    recent_reactions: list[str] | None = None

    def get_input_prompt(self) -> str:
        """Build input prompt from available context."""
        if self.explicit_topic:
            return self.explicit_topic

        if self.conversation_transcript:
            return f"Recent conversation:\n{self.conversation_transcript[-500:]}"

        if self.thread_messages:
            summary = "\n".join(msg.content for msg in self.thread_messages[-5:])
            return f"Recent messages:\n{summary}"

        return "random internet humor"
```

**Phase 2: Update Signatures**
- Change `render_meme_text(topic: str, ...)` to `render_meme_text(context: ShitpostContext, ...)`
- Change `render_shitpost(topic: str, ...)` to `render_shitpost(context: ShitpostContext, ...)`
- Update command handlers to construct appropriate `ShitpostContext`

**Phase 3: New Commands**
- `/shitpost-here` - Generate meme based on current thread/channel context
- `/shitpost-vc` - Generate meme based on recent voice conversation (requires transcript storage)
- `/auto-meme` - Auto-generate memes on high engagement (e.g., 5+ reactions)

**Benefits**:
- Separation of concerns (context gathering vs. generation)
- More relevant and contextual shitposts
- Extensible to new context sources
- Backward compatible (explicit topic still works)

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
