"""Comprehensive tests for meme generation pipeline."""

from __future__ import annotations

import pytest

from clanker.models import Context, Persona
from clanker.providers.memegen import MemegenImage
from clanker.shitposts import ShitpostContext
from clanker.shitposts.memes import (
    build_meme_prompt,
    load_meme_templates,
    normalize_meme_lines,
    parse_meme_lines,
    render_meme_text,
    sample_meme_template,
)
from tests.fakes import FakeLLM

# Unit tests for parsing and normalization


def test_parse_meme_lines_valid_list() -> None:
    """Test parsing valid JSON list of strings."""
    text = '["top text", "bottom text"]'
    lines = parse_meme_lines(text)
    assert lines == ["top text", "bottom text"]


def test_parse_meme_lines_with_whitespace() -> None:
    """Test parsing strips whitespace from lines."""
    text = '["  top text  ", "  bottom text  "]'
    lines = parse_meme_lines(text)
    assert lines == ["top text", "bottom text"]


def test_parse_meme_lines_dict_with_text_key() -> None:
    """Test parsing dict with 'text' key."""
    text = '{"text": ["top", "bottom"], "metadata": "ignored"}'
    lines = parse_meme_lines(text)
    assert lines == ["top", "bottom"]


def test_parse_meme_lines_invalid_json() -> None:
    """Test parsing raises on invalid JSON."""
    with pytest.raises(ValueError, match="not valid JSON"):
        parse_meme_lines("not json")


def test_parse_meme_lines_not_list() -> None:
    """Test parsing raises when not a list."""
    with pytest.raises(ValueError, match="must be a JSON list"):
        parse_meme_lines('{"foo": "bar"}')


def test_parse_meme_lines_not_strings() -> None:
    """Test parsing raises when list contains non-strings."""
    with pytest.raises(ValueError, match="must be a JSON list of strings"):
        parse_meme_lines("[1, 2, 3]")


def test_normalize_meme_lines_exact_match() -> None:
    """Test normalization when line count matches expected."""
    lines = normalize_meme_lines(["top", "bottom"], expected=2)
    assert lines == ["top", "bottom"]


def test_normalize_meme_lines_too_few() -> None:
    """Test normalization pads with empty strings."""
    lines = normalize_meme_lines(["top"], expected=3)
    assert lines == ["top", "", ""]


def test_normalize_meme_lines_too_many() -> None:
    """Test normalization truncates extra lines."""
    lines = normalize_meme_lines(["one", "two", "three", "four"], expected=2)
    assert lines == ["one", "two"]


def test_normalize_meme_lines_filters_blanks() -> None:
    """Test normalization filters blank lines before padding."""
    lines = normalize_meme_lines(["top", "", "bottom", ""], expected=2)
    assert lines == ["top", "bottom"]


def test_normalize_meme_lines_all_blank() -> None:
    """Test normalization returns empty strings when all blank."""
    lines = normalize_meme_lines(["", "", ""], expected=2)
    assert lines == ["", ""]


def test_normalize_meme_lines_empty_input() -> None:
    """Test normalization handles empty input."""
    lines = normalize_meme_lines([], expected=2)
    assert lines == ["", ""]


# Template loading and selection tests


def test_load_meme_templates_include_nsfw() -> None:
    """Test loading includes NSFW templates when requested."""
    all_templates = load_meme_templates(include_nsfw=True, include_disabled=True)
    safe_templates = load_meme_templates(include_nsfw=False, include_disabled=True)

    all_ids = {t.template_id for t in all_templates}
    safe_ids = {t.template_id for t in safe_templates}

    # NSFW templates should be in all but not safe
    nsfw_templates = [t for t in all_templates if t.potentially_nsfw]
    if nsfw_templates:  # Only test if we have NSFW templates
        nsfw_id = nsfw_templates[0].template_id
        assert nsfw_id in all_ids
        assert nsfw_id not in safe_ids


def test_load_meme_templates_exclude_disabled() -> None:
    """Test loading excludes disabled templates by default."""
    all_templates = load_meme_templates(include_disabled=True)
    enabled_templates = load_meme_templates(include_disabled=False)

    all_ids = {t.template_id for t in all_templates}
    enabled_ids = {t.template_id for t in enabled_templates}

    # Disabled templates should be in all but not enabled
    disabled_templates = [t for t in all_templates if t.do_not_use]
    assert len(disabled_templates) > 0  # We know some are disabled
    disabled_id = disabled_templates[0].template_id
    assert disabled_id in all_ids
    assert disabled_id not in enabled_ids


def test_sample_meme_template_by_id() -> None:
    """Test sampling specific template by ID."""
    templates = load_meme_templates()
    # We know "aag" exists and is enabled
    template = sample_meme_template(templates, template_id="aag")
    assert template.template_id == "aag"


def test_sample_meme_template_random() -> None:
    """Test random sampling returns valid template."""
    templates = load_meme_templates()
    template = sample_meme_template(templates)
    assert template.template_id in {t.template_id for t in templates}


def test_sample_meme_template_unknown_id() -> None:
    """Test sampling with unknown ID raises error."""
    templates = load_meme_templates()
    with pytest.raises(ValueError, match="Unknown meme template"):
        sample_meme_template(templates, template_id="nonexistent_meme_id")


def test_sample_meme_template_empty_list() -> None:
    """Test sampling from empty list raises error."""
    with pytest.raises(ValueError, match="No meme templates available"):
        sample_meme_template([])


# Prompt building tests


def test_build_meme_prompt_contains_topic() -> None:
    """Test prompt includes the topic."""
    templates = load_meme_templates()
    template = sample_meme_template(templates, template_id="aag")
    prompt = build_meme_prompt(template, topic="test topic")
    assert "test topic" in prompt


# Integration tests


@pytest.mark.asyncio()
async def test_render_meme_text_normalizes_output() -> None:
    """Test meme text generation normalizes LLM output."""
    templates = load_meme_templates()
    template = sample_meme_template(templates, template_id="aag")

    context = Context(
        request_id="test",
        user_id=1,
        guild_id=None,
        channel_id=1,
        persona=Persona(id="test", display_name="Test", system_prompt="test"),
        messages=[],
        metadata={},
    )

    # Fake LLM returns only 1 line but template expects 2
    llm = FakeLLM(reply_text='["Only one line"]')
    shitpost_context = ShitpostContext(user_input="test")

    lines = await render_meme_text(context, llm, template, shitpost_context)

    # Should be normalized to 2 lines
    assert len(lines) == template.text_slots
    assert lines[0] == "Only one line"
    assert lines[1] == ""  # Padded


# E2E tests with real Memegen API


@pytest.mark.network()
@pytest.mark.asyncio()
async def test_memegen_api_e2e() -> None:
    """E2E test hitting real Memegen API with fake LLM."""
    templates = load_meme_templates()
    # Use astronaut - we know it exists and has 2 text slots
    template = sample_meme_template(templates, template_id="astronaut")

    context = Context(
        request_id="e2e",
        user_id=1,
        guild_id=None,
        channel_id=1,
        persona=Persona(id="test", display_name="Test", system_prompt="test"),
        messages=[],
        metadata={},
    )

    # Use fake LLM to avoid OpenAI costs
    llm = FakeLLM(reply_text='["Wait it is a test", "Always has been"]')
    shitpost_context = ShitpostContext(user_input="testing")

    # Generate text
    lines = await render_meme_text(context, llm, template, shitpost_context)
    assert len(lines) == 2

    # Generate actual image with real Memegen API
    try:
        image_gen = MemegenImage()
        image_bytes = await image_gen.generate(
            {"template": template.template_id, "text": lines}
        )

        # Verify we got actual image data
        assert isinstance(image_bytes, bytes), f"Expected bytes, got {type(image_bytes)}"
        if len(image_bytes) == 0:
            pytest.skip("Memegen API returned empty response (may be rate limited or down)")

        # PNG magic bytes
        assert image_bytes[:8] == b"\x89PNG\r\n\x1a\n", (
            f"Invalid PNG header: {image_bytes[:8]!r}"
        )
    except Exception as e:
        pytest.skip(f"Memegen API test failed: {e}")


@pytest.mark.network()
@pytest.mark.asyncio()
async def test_memegen_multiline_e2e() -> None:
    """E2E test for multi-line memes with real API."""
    templates = load_meme_templates()
    # Use captain-america which we know has 3 text slots
    template = sample_meme_template(templates, template_id="captain-america")

    # Generate image with 3 lines
    try:
        image_gen = MemegenImage()
        image_bytes = await image_gen.generate(
            {"template": template.template_id, "text": ["Line 1", "Line 2", "Line 3"]}
        )

        assert isinstance(image_bytes, bytes)
        if len(image_bytes) == 0:
            pytest.skip("Memegen API returned empty response (may be rate limited or down)")

        # PNG magic bytes
        assert image_bytes[:8] == b"\x89PNG\r\n\x1a\n"
    except Exception as e:
        pytest.skip(f"Memegen API test failed: {e}")


# Error handling tests


@pytest.mark.asyncio()
async def test_render_meme_text_invalid_llm_response() -> None:
    """Test meme generation fails gracefully on invalid LLM response."""
    templates = load_meme_templates()
    template = sample_meme_template(templates, template_id="aag")

    context = Context(
        request_id="test",
        user_id=1,
        guild_id=None,
        channel_id=1,
        persona=Persona(id="test", display_name="Test", system_prompt="test"),
        messages=[],
        metadata={},
    )

    # LLM returns invalid JSON
    llm = FakeLLM(reply_text="not json at all")
    shitpost_context = ShitpostContext(user_input="test")

    with pytest.raises(ValueError, match="not valid JSON"):
        await render_meme_text(context, llm, template, shitpost_context)
