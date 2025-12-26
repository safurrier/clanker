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

---

## Voice-to-Meme Integration Tests

### Overview

Use the real audio test infrastructure to validate the full voice → transcript → meme pipeline. This would test that transcribed conversations produce coherent shitposts.

### Proposed Test Flow

```python
@pytest.mark.network()
@pytest.mark.slow()
async def test_voice_transcript_generates_meme():
    """E2E: Real audio → transcript → meme generation."""
    # 1. Load LibriSpeech sample and transcribe
    transcript = await transcribe_sample(librispeech_samples[0])

    # 2. Use transcript as meme topic
    context = ShitpostContext(conversation_transcript=transcript)
    template = random.choice(get_enabled_templates())

    # 3. Generate meme text
    lines = await render_meme_text(context, llm, template, transcript[:100])

    # 4. Validate output
    assert len(lines) == template.text_slots
    assert all(isinstance(line, str) for line in lines)
    assert all(len(line) > 0 for line in lines)
```

### Cost Estimate

Additional to Whisper costs:
- GPT-4o-mini for meme generation: ~$0.001 per meme
- 5 test memes per run: ~$0.005/run

### Benefits

- Validates the full user journey (speak → meme)
- Tests `ShitpostContext` with real conversation data
- Catches integration issues between voice and meme pipelines
- Could generate sample memes for manual review/documentation

### Prerequisites

- Implement `ShitpostContext` refactoring (see "Context-Aware Shitpost Refactoring" above)
- Or use simpler approach: pass transcript directly as topic string


2025.12.26
Bugs
* /chat
    * In chat threads, the bot doesn't respond in thread after the initial command. It only responds to the command
    * It SHOULD read all the messages in the thread and use that as the chat history in the call to the LLM and post the latests response
* /shitpost
    * If not already, shitpost context should ignore anything from the bot itself (e.g. text messages, embeds, etc)
    * The preview and the response are not working properly.
    * The preview does not show the memegen image, just an embed that says "Generated Shitpost"
        * Ideally, it just shows the image
    * Dismiss results in "This interaction failed" with this error:
    2025-12-26 19:42:47 | ERROR    | clanker_bot.views.shitpost_preview:dismiss_button:205 - shitpost.dismiss_failed
Traceback (most recent call last):

  File "<frozen runpy>", line 198, in _run_module_as_main
  File "<frozen runpy>", line 88, in _run_code

  File "/workspace/src/clanker_bot/main.py", line 165, in <module>

  File "/workspace/src/clanker_bot/main.py", line 144, in main
    await bot.start(token)
          │   │     └ 'MTQ1NDE4MDU2NjYwMDY1MDgyMg.GzG6Ob.YMJwcafhx0qHtynZozCwI38WFYkKgY9E1f9tEY'
          │   └ <function Client.start at 0xffffb59023e0>
          └ <clanker_bot.commands.ClankerClient object at 0xffffb48f3cb0>

  File "/usr/local/lib/python3.12/asyncio/runners.py", line 195, in run
    return runner.run(main)
           │      │   └ <coroutine object main.<locals>.runner at 0xffffb46c1700>
           │      └ <function Runner.run at 0xffffb6fc9ee0>
           └ <asyncio.runners.Runner object at 0xffffb46e0140>
  File "/usr/local/lib/python3.12/asyncio/runners.py", line 118, in run
    return self._loop.run_until_complete(task)
           │    │     │                  └ <Task pending name='Task-1' coro=<main.<locals>.runner() running at /workspace/src/clanker_bot/main.py:142> wait_for=<Future ...
           │    │     └ <function BaseEventLoop.run_until_complete at 0xffffb723fb00>
           │    └ <_UnixSelectorEventLoop running=True closed=False debug=False>
           └ <asyncio.runners.Runner object at 0xffffb46e0140>
  File "/usr/local/lib/python3.12/asyncio/base_events.py", line 678, in run_until_complete
    self.run_forever()
    │    └ <function BaseEventLoop.run_forever at 0xffffb723fa60>
    └ <_UnixSelectorEventLoop running=True closed=False debug=False>
  File "/usr/local/lib/python3.12/asyncio/base_events.py", line 645, in run_forever
    self._run_once()
    │    └ <function BaseEventLoop._run_once at 0xffffb6fc98a0>
    └ <_UnixSelectorEventLoop running=True closed=False debug=False>
  File "/usr/local/lib/python3.12/asyncio/base_events.py", line 1999, in _run_once
    handle._run()
    │      └ <function Handle._run at 0xffffb719bce0>
    └ <Handle Task.task_wakeup(<Future finished result=None>)>
  File "/usr/local/lib/python3.12/asyncio/events.py", line 88, in _run
    self._context.run(self._callback, *self._args)
    │    │            │    │           │    └ <member '_args' of 'Handle' objects>
    │    │            │    │           └ <Handle Task.task_wakeup(<Future finished result=None>)>
    │    │            │    └ <member '_callback' of 'Handle' objects>
    │    │            └ <Handle Task.task_wakeup(<Future finished result=None>)>
    │    └ <member '_context' of 'Handle' objects>
    └ <Handle Task.task_wakeup(<Future finished result=None>)>
  File "/usr/local/lib/python3.12/site-packages/discord/ui/view.py", line 555, in _scheduled_task
    await item.callback(interaction)
          │    │        └ <Interaction id=1454197775582367890 type=<InteractionType.component: 3> guild_id=1396212559199211560 user=<Member id=33630329...
          │    └ <discord.ui.view._ViewCallback object at 0xffffb2043b00>
          └ <Button style=<ButtonStyle.danger: 4> url=None disabled=False label='Dismiss' emoji=<PartialEmoji animated=False name='🗑️' id...

> File "/workspace/src/clanker_bot/views/shitpost_preview.py", line 191, in dismiss_button
    await interaction.response.edit_message(
          │           └ <discord.utils.CachedSlotProperty object at 0xffffb5a23f20>
          └ <Interaction id=1454197775582367890 type=<InteractionType.component: 3> guild_id=1396212559199211560 user=<Member id=33630329...

  File "/usr/local/lib/python3.12/site-packages/discord/interactions.py", line 1207, in edit_message
    response = await adapter.create_interaction_response(
                     │       └ <function AsyncWebhookAdapter.create_interaction_response at 0xffffb5a60ea0>
                     └ <discord.webhook.async_.AsyncWebhookAdapter object at 0xffffb5a55ca0>
  File "/usr/local/lib/python3.12/site-packages/discord/webhook/async_.py", line 226, in request
    raise HTTPException(response, data)
          │             │         └ {'message': 'Cannot send an empty message', 'code': 50006}
          │             └ <ClientResponse(https://discord.com/api/v10/interactions/1454197775582367890/aW50ZXJhY3Rpb246MTQ1NDE5Nzc3NTU4MjM2Nzg5MDpsTmNs...
          └ <class 'discord.errors.HTTPException'>

discord.errors.HTTPException: 400 Bad Request (error code: 50006): Cannot send an empty message
    * There's no UX on regenerate, it just edits the image in place. Instead I think it would make sense if the flow was basically an edit immediately that says like regenerating or soemthing and then a NEW ephemeral post? If the ephemeral is not possible on a new message we can edit in place maybe)
    * The Post only displays the text, not a generated meme. I.e. I think it's just the meme lines generated from LLM and not the memegen image
* We should add a /transcript command or something that displays/prints the recent transcript with the same defaults used for the meme shitpost? For debugging purposes
* This is the join message on VC join using /join from the bot. Let's have some default messages for join / leave. Since it really only does /shitpost maybe let's have that briefly mentioned?
* The shitpost if it's a Text in Chat channel (i.e. the chat channel associated with a voice channel), it should ONLY use the transcritptions for shitposts. I.e. if shitpost is run in that channel we but don't have any recent transcripts from that channel (idk maybe within the last 5 mins or so), then respond ephemerally with a message about how user needs to run /join first or whatever?
* The voice ingest is not working properly. We likely need to do like a pair programming where I manually attempt to have the VC capture audio and transcribe and Claude watches the logs, propsoes fixes etc. In the meantime, this is the initial error trace:
2025-12-26 19:56:39 | ERROR    | clanker_bot.command_handlers.voice:_setup_transcription:63 - Failed to start voice ingest.
Traceback (most recent call last):

  File "<frozen runpy>", line 198, in _run_module_as_main
  File "<frozen runpy>", line 88, in _run_code

  File "/workspace/src/clanker_bot/main.py", line 165, in <module>
    main()
    └ <function main at 0xffff825036a0>

  File "/workspace/src/clanker_bot/main.py", line 144, in main
    asyncio.run(runner())
    │       │   └ <function main.<locals>.runner at 0xffff8245fce0>
    │       └ <function run at 0xffff85cbade0>
    └ <module 'asyncio' from '/usr/local/lib/python3.12/asyncio/__init__.py'>

  File "/usr/local/lib/python3.12/asyncio/runners.py", line 195, in run
    return runner.run(main)
           │      │   └ <coroutine object main.<locals>.runner at 0xffff82465700>
           │      └ <function Runner.run at 0xffff84d69da0>
           └ <asyncio.runners.Runner object at 0xffff82480110>
  File "/usr/local/lib/python3.12/asyncio/runners.py", line 118, in run
    return self._loop.run_until_complete(task)
           │    │     │                  └ <Task pending name='Task-1' coro=<main.<locals>.runner() running at /workspace/src/clanker_bot/main.py:142> wait_for=<Future ...
           │    │     └ <function BaseEventLoop.run_until_complete at 0xffff84fdf9c0>
           │    └ <_UnixSelectorEventLoop running=True closed=False debug=False>
           └ <asyncio.runners.Runner object at 0xffff82480110>
  File "/usr/local/lib/python3.12/asyncio/base_events.py", line 678, in run_until_complete
    self.run_forever()
    │    └ <function BaseEventLoop.run_forever at 0xffff84fdf920>
    └ <_UnixSelectorEventLoop running=True closed=False debug=False>
  File "/usr/local/lib/python3.12/asyncio/base_events.py", line 645, in run_forever
    self._run_once()
    │    └ <function BaseEventLoop._run_once at 0xffff84d69760>
    └ <_UnixSelectorEventLoop running=True closed=False debug=False>
  File "/usr/local/lib/python3.12/asyncio/base_events.py", line 1999, in _run_once
    handle._run()
    │      └ <function Handle._run at 0xffff84f3bba0>
    └ <Handle Task.task_wakeup(<Task finishe...> result=None>)>
  File "/usr/local/lib/python3.12/asyncio/events.py", line 88, in _run
    self._context.run(self._callback, *self._args)
    │    │            │    │           │    └ <member '_args' of 'Handle' objects>
    │    │            │    │           └ <Handle Task.task_wakeup(<Task finishe...> result=None>)>
    │    │            │    └ <member '_callback' of 'Handle' objects>
    │    │            └ <Handle Task.task_wakeup(<Task finishe...> result=None>)>
    │    └ <member '_context' of 'Handle' objects>
    └ <Handle Task.task_wakeup(<Task finishe...> result=None>)>
  File "/usr/local/lib/python3.12/site-packages/discord/app_commands/tree.py", line 1138, in wrapper
    await self._call(interaction)
          │    │     └ <Interaction id=1454201239838392461 type=<InteractionType.application_command: 2> guild_id=1396212559199211560 user=<Member i...
          │    └ <function CommandTree._call at 0xffff837de5c0>
          └ <discord.app_commands.tree.CommandTree object at 0xffff823ee720>
  File "/usr/local/lib/python3.12/site-packages/discord/app_commands/tree.py", line 1297, in _call
    await command._invoke_with_namespace(interaction, namespace)
          │       │                      │            └ <Namespace >
          │       │                      └ <Interaction id=1454201239838392461 type=<InteractionType.application_command: 2> guild_id=1396212559199211560 user=<Member i...
          │       └ <function Command._invoke_with_namespace at 0xffff837c4ea0>
          └ <discord.app_commands.commands.Command object at 0xffff8244fd10>
  File "/usr/local/lib/python3.12/site-packages/discord/app_commands/commands.py", line 884, in _invoke_with_namespace
    return await self._do_call(interaction, transformed_values)
                 │    │        │            └ {}
                 │    │        └ <Interaction id=1454201239838392461 type=<InteractionType.application_command: 2> guild_id=1396212559199211560 user=<Member i...
                 │    └ <function Command._do_call at 0xffff837c4e00>
                 └ <discord.app_commands.commands.Command object at 0xffff8244fd10>
  File "/usr/local/lib/python3.12/site-packages/discord/app_commands/commands.py", line 859, in _do_call
    return await self._callback(interaction, **params)  # type: ignore
                 │    │         │              └ {}
                 │    │         └ <Interaction id=1454201239838392461 type=<InteractionType.application_command: 2> guild_id=1396212559199211560 user=<Member i...
                 │    └ <function register_commands.<locals>.join at 0xffff82503c40>
                 └ <discord.app_commands.commands.Command object at 0xffff8244fd10>

  File "/workspace/src/clanker_bot/commands.py", line 80, in join
    await handle_join(interaction, deps)
          │           │            └ BotDependencies(llm=OpenAILLM(api_key='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', model='gpt-4o-mini', base_url='h...
          │           └ <Interaction id=1454201239838392461 type=<InteractionType.application_command: 2> guild_id=1396212559199211560 user=<Member i...
          └ <function handle_join at 0xffff825032e0>

  File "/workspace/src/clanker_bot/command_handlers/voice.py", line 96, in handle_join
    message = await _setup_transcription(deps, voice_client_cls)
                    │                    │     └ <class 'discord.ext.voice_recv.voice_client.VoiceRecvClient'>
                    │                    └ BotDependencies(llm=OpenAILLM(api_key='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', model='gpt-4o-mini', base_url='h...
                    └ <function _setup_transcription at 0xffff82503240>

> File "/workspace/src/clanker_bot/command_handlers/voice.py", line 58, in _setup_transcription
    await start_voice_ingest(recv_client, deps.stt)
          │                  │            │    └ OpenAISTT(api_key='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', model='whisper-1', base_url='https://api.openai.com/...
          │                  │            └ BotDependencies(llm=OpenAILLM(api_key='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', model='gpt-4o-mini', base_url='h...
          │                  └ <discord.ext.voice_recv.voice_client.VoiceRecvClient object at 0xffff82b24ef0>
          └ <function start_voice_ingest at 0xffff82502ac0>

  File "/workspace/src/clanker_bot/voice_ingest.py", line 200, in start_voice_ingest
    sink = VoiceIngestSink(worker, on_transcript=on_transcript)
           │               │                     └ None
           │               └ VoiceIngestWorker(stt=OpenAISTT(api_key='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', model='whisper-1', base_url='h...
           └ <class 'clanker_bot.voice_ingest.VoiceIngestSink'>

TypeError: Can't instantiate abstract class VoiceIngestSink without an implementation for abstract methods 'cleanup', 'wants_opus'


* the /speak command doesn't do anything, we should comment it out for now and add a FutureWork section on actually getting that to work properly
* The /join command seems to do something related to checking/downloading Silero VAD and results in this message. Shouldn't we just have that like model predownloaded via docker and loaded on bot startup?
/usr/local/lib/python3.12/site-packages/torch/hub.py:335: UserWarning: You are about to download and run code from an untrusted repository. In a future release, this won't be allowed. To add the repository to your trusted list, change the command to {calling_fn}(..., trust_repo=False) and a command prompt will appear asking for an explicit confirmation of trust, or load(..., trust_repo=True), which will assume that the prompt is to be answered with 'yes'. You can also use load(..., trust_repo='check') which will only prompt for confirmation if the repo is not already trusted. This will eventually be the default behaviour
  warnings.warn(


* VC monitoring nudge.
  * We could add a Cog to listen to VC channels in guild and when at least 2 people are present send a View to start lisenting/join. If not selected within 5 minutes, dissapear
* Auto leave meeting. When no users present, leave/end the voice call.
