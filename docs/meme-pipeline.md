# Meme Generation Pipeline

The Clanker9000 bot includes a curated meme generation system that uses LLMs to create contextually appropriate meme text based on a library of 166+ meme templates.

## Overview

The meme pipeline consists of three main components:

1. **Meme Registry** - JSON database of curated meme templates with metadata
2. **Runtime Generation** - LLM-powered text generation for memes
3. **Offline Scripts** - Tools for building and maintaining the registry

## Architecture

```
User: /shitpost n:3 guidance:"AI takeover"
  ↓
Discord Command Handler (handle_shitpost_preview)
  ↓
Build ShitpostContext (channel messages, voice transcripts, or guidance)
  ↓
Generate N meme previews in parallel:
  ├─► Load Templates → Sample Random Template
  ├─► Build LLM Prompt (context + template metadata + examples)
  └─► LLM Generates Text → ["Wait, it's all AI?", "Always has been"]
  ↓
ShitpostPreviewView (ephemeral message, only visible to user)
  ↓
[Post] → Memegen API → Publish to channel
[Regenerate] → Pick new template → Update preview
[Dismiss] → Remove ephemeral message
```

**Note:** The `/shitpost` command now uses:
- `ShitpostContext` model for rich input (explicit guidance, channel messages, or voice transcripts)
- Ephemeral previews so only the command invoker sees drafts
- Interactive buttons (Post/Regenerate/Dismiss) via `ShitpostPreviewView`

## Meme Registry Schema

Each template in `src/clanker/shitposts/meme_instance_args.json` contains:

| Field | Type | Description |
|-------|------|-------------|
| `template_id` | string | Unique identifier matching Memegen API |
| `variant` | string | Human-readable meme name |
| `variant_description` | string | What the meme is and how it's used |
| `examples` | list[list[str]] | 3-6 real examples of the meme format |
| `applicable_context` | string | When/where this meme is appropriate |
| `reference` | string | KnowYourMeme URL for the meme |
| `potentially_nsfw` | boolean | Whether content may be inappropriate |
| `do_not_use` | boolean | Whether template is disabled |
| `disable_reason` | string | (Optional) Why template is disabled |
| `additional_prompt_instructions` | string | (Optional) Extra LLM guidance |
| `examples_updated` | boolean | Whether examples were LLM-regenerated |

### Example Entry

```json
{
  "template_id": "astronaut",
  "variant": "Always Has Been",
  "variant_description": "Two astronauts, one revealing truth while pointing gun...",
  "examples": [
    ["Wait, it's round?", "Always has been"],
    ["Wait, it's all just dog pictures?", "Always has been"]
  ],
  "applicable_context": "Express surprising or previously unknown information...",
  "reference": "https://knowyourmeme.com/memes/wait-its-all-ohio-always-has-been",
  "potentially_nsfw": false,
  "do_not_use": false
}
```

## Runtime Flow

### 1. Template Loading

Templates are loaded from the registry with optional filters:

```python
from clanker.shitposts import load_meme_templates

# Load enabled, SFW templates only (default)
templates = load_meme_templates()

# Load all templates including NSFW
templates = load_meme_templates(include_nsfw=True)

# Load disabled templates too (for admin/debugging)
templates = load_meme_templates(include_disabled=True)
```

**Performance**: Templates are cached using `@lru_cache` to avoid re-parsing JSON on every request.

### 2. Template Selection

```python
from clanker.shitposts import sample_meme_template

# Random selection
template = sample_meme_template(templates)

# Specific template
template = sample_meme_template(templates, template_id="astronaut")
```

### 3. Text Generation

```python
from clanker.shitposts import render_meme_text

lines = await render_meme_text(
    context=context,       # Bot context (user, channel, etc.)
    llm=llm,              # LLM provider
    meme=template,        # Selected template
    topic="AI takeover"   # User's topic
)
# Returns: ["Wait, it's all AI?", "Always has been"]
```

The LLM receives a prompt containing:
- User's topic
- Template description and usage context
- All examples from the registry
- Expected number of text lines (`text_slots`)
- Any additional instructions

### 4. Image Generation

```python
from clanker.providers.memegen import MemegenImage

image = MemegenImage()
image_bytes = await image.generate({
    "template": "astronaut",
    "text": ["Wait, it's all AI?", "Always has been"]
})
```

## Offline Registry Scripts

### Generate New Templates

Fetches templates from Memegen API, filters to KnowYourMeme sources only, and uses LLM to extract metadata:

```bash
export OPENAI_API_KEY=sk-...
uv run python scripts/generate_memes.py
```

**What it does**:
1. Fetches all templates from `https://api.memegen.link/templates`
2. Filters to templates with KnowYourMeme references (quality control)
3. For each new template:
   - Builds prompt with template metadata
   - LLM extracts structured metadata (variant, description, examples, etc.)
   - Validates result matches `MemeTemplate` schema
   - Saves to registry incrementally (crash-safe)

**Idempotent**: Skips templates already in registry.

### Update Examples

Regenerates examples for existing templates to improve quality:

```bash
export OPENAI_API_KEY=sk-...
uv run python scripts/update_memes_examples.py
```

**What it does**:
1. Loads existing registry
2. For each template without `examples_updated: true`:
   - Builds prompt asking for high-quality examples
   - LLM generates 5-6 examples
   - Saves updated examples
   - Marks `examples_updated: true`

**Use when**: Initial examples from scraping are low quality or insufficient.

### Validate Registry

Checks registry for common errors and quality issues:

```bash
uv run python scripts/validate_registry.py
```

**Checks performed**:
- Required fields present (variant, description, examples, etc.)
- Minimum 3 examples per template
- `text_slots` matches actual example lengths
- Examples aren't all blank
- Disabled templates have `disable_reason`
- Example count consistency (warns if very inconsistent)

**Exit code**: 0 if valid, 1 if errors found (suitable for CI)

## Adding New Memes

### Automated (Recommended)

```bash
# Add all new KnowYourMeme templates
uv run python scripts/generate_memes.py

# Optionally regenerate examples for quality
uv run python scripts/update_memes_examples.py

# Validate before committing
uv run python scripts/validate_registry.py
```

### Manual

1. Open `src/clanker/shitposts/meme_instance_args.json`
2. Add new entry with all required fields:
   ```json
   {
     "my_meme": {
       "template_id": "my_meme",
       "variant": "My Awesome Meme",
       "variant_description": "A meme about...",
       "examples": [
         ["Top text", "Bottom text"],
         ["Another top", "Another bottom"],
         ["Third example", "Third bottom"]
       ],
       "applicable_context": "Use when...",
       "reference": "https://knowyourmeme.com/memes/my-meme",
       "potentially_nsfw": false,
       "do_not_use": false
     }
   }
   ```
3. Validate: `uv run python scripts/validate_registry.py`
4. Test: `/shitpost topic:"test" category:"meme"` in Discord

**Pro tips**:
- Include 5-6 examples (more is better for LLM prompting)
- Make examples diverse to show format variation
- Write clear `applicable_context` (helps LLM understand when to use)
- Use actual meme text from KnowYourMeme examples

## Disabling Templates

To temporarily disable a template:

```json
{
  "problematic_meme": {
    ...
    "do_not_use": true,
    "disable_reason": "NSFW content / offensive theme / low quality examples"
  }
}
```

Disabled templates:
- Won't be selected during runtime
- Are still validated (catch structural errors)
- Can be re-enabled by setting `do_not_use: false`

## Telemetry

The following metrics are tracked:

| Metric | Description |
|--------|-------------|
| `shitpost_requests` | Total shitpost command invocations |
| `meme_template_{template_id}` | Usage count per template |
| `meme_generation_success` | Successful LLM text generations |
| `meme_generation_failure` | Failed LLM generations |

**Analysis ideas**:
- Most popular memes: `sort by meme_template_*`
- Success rate: `success / (success + failure)`
- Templates never used: candidates for removal

## Troubleshooting

### "No meme templates available"
- Check `load_meme_templates()` filters (NSFW/disabled)
- Validate registry: `uv run python scripts/validate_registry.py`
- Verify JSON is valid: `jq . src/clanker/shitposts/meme_instance_args.json`

### "Meme response was not valid JSON"
- LLM didn't return JSON (prompt issue or model failure)
- Check logs for actual LLM response
- Consider adding fallback to random example

### Image generation fails
- Verify Memegen API is accessible: `curl https://api.memegen.link/templates`
- Check template_id exists in Memegen
- Verify text encoding (special characters)

### Poor quality memes
- Add more/better examples to template
- Improve `applicable_context` field
- Update `additional_prompt_instructions` with specific guidance
- Try regenerating examples: `uv run python scripts/update_memes_examples.py`

## Testing

Run tests:
```bash
# All tests
make test

# Meme-specific tests only
uv run pytest tests/test_shitposts.py -k meme

# Test with actual API calls (requires OPENAI_API_KEY)
uv run pytest tests/test_shitposts.py -m network
```

Test specific template:
```python
# In Discord
/shitpost topic:"test" category:"meme"

# Via Python
from clanker.shitposts import load_meme_templates, sample_meme_template
templates = load_meme_templates()
template = sample_meme_template(templates, template_id="astronaut")
print(template)
```

## Best Practices

1. **Always validate before committing**: `uv run python scripts/validate_registry.py`
2. **Use automated scripts when possible** - Manual edits are error-prone
3. **Include diverse examples** - More examples = better LLM output
4. **Test new templates** - Try `/shitpost` with new templates before deploying
5. **Document disable reasons** - Future maintainers will thank you
6. **Keep registry organized** - Templates are sorted alphabetically by ID
7. **Use KnowYourMeme references** - Canonical source for meme history

## Future Improvements

See `FUTURE_WORK.md` (in repo root) for planned enhancements including:
- Context-aware template selection
- Smarter template matching based on topic
- Enhanced prompt engineering
- Example quality scoring
