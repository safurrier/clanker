"""Tests for ShitpostPreviewView."""

from __future__ import annotations

from dataclasses import dataclass

import discord
import pytest

from clanker_bot.views.shitpost_preview import (
    MemePayload,
    ShitpostPreviewView,
)


@dataclass
class FakeUser:
    """Fake Discord user for testing."""

    id: int


@dataclass
class FakeChannel:
    """Fake Discord channel for testing."""

    sent_messages: list[tuple[str, bytes | None]]

    async def send(
        self, content: str, *, file: discord.File | None = None, **kwargs: object
    ) -> None:
        image_bytes = None
        if file:
            image_bytes = file.fp.read()
        self.sent_messages.append((content, image_bytes))


class FakeInteractionResponse:
    """Fake interaction response for testing."""

    def __init__(self) -> None:
        self.deferred = False
        self.sent_messages: list[tuple[str, bool]] = []  # (content, ephemeral)
        self.edited_message: dict | None = None

    async def defer(self) -> None:
        self.deferred = True

    async def send_message(self, content: str, *, ephemeral: bool = False) -> None:
        self.sent_messages.append((content, ephemeral))

    async def edit_message(
        self,
        *,
        content: str | None = None,
        embed: discord.Embed | None = None,
        attachments: list | None = None,
        view: discord.ui.View | None = None,
    ) -> None:
        self.edited_message = {
            "content": content,
            "embed": embed,
            "attachments": attachments,
            "view": view,
        }


class FakeInteraction:
    """Fake Discord interaction for testing view callbacks."""

    def __init__(self, user_id: int, channel: FakeChannel | None = None) -> None:
        self.user = FakeUser(id=user_id)
        self.channel = channel
        self.response = FakeInteractionResponse()
        self._followup_messages: list[tuple[str, bool]] = []
        self._edited_original: dict | None = None

    @property
    def followup(self) -> FakeInteraction:
        return self

    async def send(self, content: str, *, ephemeral: bool = False) -> None:
        self._followup_messages.append((content, ephemeral))

    async def edit_original_response(
        self,
        *,
        embed: discord.Embed | None = None,
        attachments: list | None = None,
        view: discord.ui.View | None = None,
    ) -> None:
        self._edited_original = {
            "embed": embed,
            "attachments": attachments,
            "view": view,
        }


def make_embed(title: str = "Test Meme") -> discord.Embed:
    """Create a test embed."""
    return discord.Embed(title=title, description="Test meme content")


def make_payload(
    text: str = "meme caption",
    image_bytes: bytes | None = None,
    template_id: str = "test-template",
) -> MemePayload:
    """Create a test payload."""
    return MemePayload(text=text, image_bytes=image_bytes, template_id=template_id)


class TestShitpostPreviewViewInit:
    """Tests for ShitpostPreviewView initialization."""

    @pytest.mark.asyncio
    async def test_creates_with_required_args(self) -> None:
        payload = make_payload()
        embed = make_embed()
        view = ShitpostPreviewView(
            invoker_id=123,
            payload=payload,
            embed=embed,
        )
        assert view.invoker_id == 123
        assert view.payload == payload
        assert view.embed == embed
        assert view.preview_id is not None
        assert view.timeout == 900.0

    @pytest.mark.asyncio
    async def test_accepts_custom_preview_id(self) -> None:
        view = ShitpostPreviewView(
            invoker_id=123,
            preview_id="custom-id",
            payload=make_payload(),
            embed=make_embed(),
        )
        assert view.preview_id == "custom-id"

    @pytest.mark.asyncio
    async def test_accepts_custom_timeout(self) -> None:
        view = ShitpostPreviewView(
            invoker_id=123,
            payload=make_payload(),
            embed=make_embed(),
            timeout=60.0,
        )
        assert view.timeout == 60.0

    @pytest.mark.asyncio
    async def test_has_three_buttons(self) -> None:
        view = ShitpostPreviewView(
            invoker_id=123,
            payload=make_payload(),
            embed=make_embed(),
        )
        buttons = [child for child in view.children if isinstance(child, discord.ui.Button)]
        assert len(buttons) == 3

        labels = {b.label for b in buttons}
        assert labels == {"Post", "Regenerate", "Dismiss"}


class TestInteractionCheck:
    """Tests for interaction_check access control."""

    @pytest.mark.asyncio
    async def test_allows_invoker(self) -> None:
        view = ShitpostPreviewView(
            invoker_id=123,
            payload=make_payload(),
            embed=make_embed(),
        )
        interaction = FakeInteraction(user_id=123)
        result = await view.interaction_check(interaction)  # type: ignore[arg-type]
        assert result is True

    @pytest.mark.asyncio
    async def test_blocks_other_users(self) -> None:
        view = ShitpostPreviewView(
            invoker_id=123,
            payload=make_payload(),
            embed=make_embed(),
        )
        interaction = FakeInteraction(user_id=456)
        result = await view.interaction_check(interaction)  # type: ignore[arg-type]
        assert result is False
        assert len(interaction.response.sent_messages) == 1
        assert "Only the person who ran this command" in interaction.response.sent_messages[0][0]


class TestPostButton:
    """Tests for the Post button."""

    @pytest.mark.asyncio
    async def test_posts_text_to_channel(self) -> None:
        channel = FakeChannel(sent_messages=[])
        payload = make_payload(text="my meme caption")
        view = ShitpostPreviewView(
            invoker_id=123,
            payload=payload,
            embed=make_embed(),
        )
        interaction = FakeInteraction(user_id=123, channel=channel)

        await view.post_button.callback(interaction)  # type: ignore[arg-type]

        assert len(channel.sent_messages) == 1
        assert channel.sent_messages[0][0] == "my meme caption"
        assert channel.sent_messages[0][1] is None  # no image

    @pytest.mark.asyncio
    async def test_posts_text_and_image_to_channel(self) -> None:
        channel = FakeChannel(sent_messages=[])
        payload = make_payload(text="caption", image_bytes=b"fake-png-data")
        view = ShitpostPreviewView(
            invoker_id=123,
            payload=payload,
            embed=make_embed(),
        )
        interaction = FakeInteraction(user_id=123, channel=channel)

        await view.post_button.callback(interaction)  # type: ignore[arg-type]

        assert len(channel.sent_messages) == 1
        assert channel.sent_messages[0][0] == "caption"
        assert channel.sent_messages[0][1] == b"fake-png-data"

    @pytest.mark.asyncio
    async def test_removes_preview_after_posting(self) -> None:
        channel = FakeChannel(sent_messages=[])
        view = ShitpostPreviewView(
            invoker_id=123,
            payload=make_payload(),
            embed=make_embed(),
        )
        interaction = FakeInteraction(user_id=123, channel=channel)

        await view.post_button.callback(interaction)  # type: ignore[arg-type]

        assert interaction.response.edited_message is not None
        assert interaction.response.edited_message["content"] == "Posted!"
        assert interaction.response.edited_message["embed"] is None
        assert interaction.response.edited_message["view"] is None

    @pytest.mark.asyncio
    async def test_prevents_double_posting(self) -> None:
        channel = FakeChannel(sent_messages=[])
        view = ShitpostPreviewView(
            invoker_id=123,
            payload=make_payload(),
            embed=make_embed(),
        )
        interaction = FakeInteraction(user_id=123, channel=channel)

        # First post
        await view.post_button.callback(interaction)  # type: ignore[arg-type]
        assert len(channel.sent_messages) == 1

        # Second attempt
        interaction2 = FakeInteraction(user_id=123, channel=channel)
        await view.post_button.callback(interaction2)  # type: ignore[arg-type]

        # Should not post again
        assert len(channel.sent_messages) == 1
        assert "already been posted" in interaction2.response.sent_messages[0][0]

    @pytest.mark.asyncio
    async def test_handles_missing_channel(self) -> None:
        view = ShitpostPreviewView(
            invoker_id=123,
            payload=make_payload(),
            embed=make_embed(),
        )
        interaction = FakeInteraction(user_id=123, channel=None)

        await view.post_button.callback(interaction)  # type: ignore[arg-type]

        assert "Could not find channel" in interaction.response.sent_messages[0][0]


class TestRegenerateButton:
    """Tests for the Regenerate button."""

    @pytest.mark.asyncio
    async def test_calls_regenerate_callback(self) -> None:
        new_payload = make_payload(text="new caption", template_id="new-template")
        new_embed = make_embed(title="New Meme")

        async def regenerate() -> tuple[MemePayload, discord.Embed]:
            return new_payload, new_embed

        view = ShitpostPreviewView(
            invoker_id=123,
            payload=make_payload(),
            embed=make_embed(),
            regenerate_callback=regenerate,
        )
        interaction = FakeInteraction(user_id=123)

        await view.regenerate_button.callback(interaction)  # type: ignore[arg-type]

        assert view.payload == new_payload
        assert view.embed == new_embed
        assert interaction.response.deferred is True
        assert interaction._edited_original is not None
        assert interaction._edited_original["embed"] == new_embed

    @pytest.mark.asyncio
    async def test_updates_view_with_new_image(self) -> None:
        new_payload = make_payload(
            text="new caption",
            image_bytes=b"new-image-data",
        )
        new_embed = make_embed(title="New Meme")

        async def regenerate() -> tuple[MemePayload, discord.Embed]:
            return new_payload, new_embed

        view = ShitpostPreviewView(
            invoker_id=123,
            payload=make_payload(),
            embed=make_embed(),
            regenerate_callback=regenerate,
        )
        interaction = FakeInteraction(user_id=123)

        await view.regenerate_button.callback(interaction)  # type: ignore[arg-type]

        assert interaction._edited_original is not None
        # Attachments should contain the new file
        assert len(interaction._edited_original["attachments"]) == 1

    @pytest.mark.asyncio
    async def test_handles_no_callback(self) -> None:
        view = ShitpostPreviewView(
            invoker_id=123,
            payload=make_payload(),
            embed=make_embed(),
            regenerate_callback=None,
        )
        interaction = FakeInteraction(user_id=123)

        await view.regenerate_button.callback(interaction)  # type: ignore[arg-type]

        assert "not available" in interaction.response.sent_messages[0][0]

    @pytest.mark.asyncio
    async def test_blocks_regenerate_after_posted(self) -> None:
        async def regenerate() -> tuple[MemePayload, discord.Embed]:
            return make_payload(), make_embed()

        channel = FakeChannel(sent_messages=[])
        view = ShitpostPreviewView(
            invoker_id=123,
            payload=make_payload(),
            embed=make_embed(),
            regenerate_callback=regenerate,
        )

        # Post first
        post_interaction = FakeInteraction(user_id=123, channel=channel)
        await view.post_button.callback(post_interaction)  # type: ignore[arg-type]

        # Try to regenerate
        regen_interaction = FakeInteraction(user_id=123)
        await view.regenerate_button.callback(regen_interaction)  # type: ignore[arg-type]

        assert "already been posted" in regen_interaction.response.sent_messages[0][0]


class TestDismissButton:
    """Tests for the Dismiss button."""

    @pytest.mark.asyncio
    async def test_clears_message(self) -> None:
        view = ShitpostPreviewView(
            invoker_id=123,
            payload=make_payload(),
            embed=make_embed(),
        )
        interaction = FakeInteraction(user_id=123)

        await view.dismiss_button.callback(interaction)  # type: ignore[arg-type]

        assert interaction.response.edited_message is not None
        assert interaction.response.edited_message["content"] is None
        assert interaction.response.edited_message["embed"] is None
        assert interaction.response.edited_message["view"] is None
        assert interaction.response.edited_message["attachments"] == []


class TestMemePayload:
    """Tests for MemePayload dataclass."""

    def test_text_only(self) -> None:
        payload = MemePayload(text="hello")
        assert payload.text == "hello"
        assert payload.image_bytes is None
        assert payload.template_id is None

    def test_with_image(self) -> None:
        payload = MemePayload(
            text="hello",
            image_bytes=b"image-data",
            template_id="drake",
        )
        assert payload.text == "hello"
        assert payload.image_bytes == b"image-data"
        assert payload.template_id == "drake"
