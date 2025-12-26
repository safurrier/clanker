"""Ephemeral preview view for shitpost generation."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from io import BytesIO

import discord

logger = logging.getLogger(__name__)


@dataclass
class MemePayload:
    """Payload for a generated meme preview."""

    text: str
    image_bytes: bytes | None = None
    template_id: str | None = None


# Type alias for the regenerate callback
RegenerateCallback = Callable[[], Awaitable[tuple[MemePayload, discord.Embed]]]


class ShitpostPreviewView(discord.ui.View):
    """Ephemeral preview view with Post/Regenerate/Dismiss buttons.

    Args:
        invoker_id: Discord user ID of the command invoker (only they can interact)
        preview_id: Unique ID for this preview (for logging/tracking)
        payload: The meme content to post
        embed: The embed to display in the preview
        regenerate_callback: Async function to generate a new meme
        timeout: View timeout in seconds (default 15 minutes)
    """

    def __init__(
        self,
        *,
        invoker_id: int,
        preview_id: str | None = None,
        payload: MemePayload,
        embed: discord.Embed,
        regenerate_callback: RegenerateCallback | None = None,
        timeout: float = 900.0,  # 15 minutes
    ) -> None:
        super().__init__(timeout=timeout)
        self.invoker_id = invoker_id
        self.preview_id = preview_id or str(uuid.uuid4())
        self.payload = payload
        self.embed = embed
        self.regenerate_callback = regenerate_callback
        self._posted = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Only allow the original invoker to interact with this view."""
        if interaction.user.id != self.invoker_id:
            await interaction.response.send_message(
                "Only the person who ran this command can use these buttons.",
                ephemeral=True,
            )
            return False
        return True

    def _build_file(self) -> discord.File | None:
        """Build a discord.File from the payload image bytes."""
        if self.payload.image_bytes:
            return discord.File(
                fp=BytesIO(self.payload.image_bytes),
                filename="meme.png",
            )
        return None

    async def _update_preview(
        self,
        interaction: discord.Interaction,
        new_payload: MemePayload,
        new_embed: discord.Embed,
    ) -> None:
        """Update the preview message with new meme content."""
        self.payload = new_payload
        self.embed = new_embed

        file = self._build_file()
        attachments = [file] if file else []
        await interaction.edit_original_response(
            embed=new_embed,
            attachments=attachments,
            view=self,
        )

    @discord.ui.button(label="Post", style=discord.ButtonStyle.success, emoji="✅")
    async def post_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Publish the meme to the channel and remove the preview."""
        if self._posted:
            await interaction.response.send_message(
                "This meme has already been posted.", ephemeral=True
            )
            return

        self._posted = True

        # Post to the channel where the command was invoked
        channel = interaction.channel
        if channel is None or not hasattr(channel, "send"):
            await interaction.response.send_message(
                "Error: Could not find channel to post to.", ephemeral=True
            )
            return

        try:
            file = self._build_file()
            if file:
                await channel.send(content=self.payload.text, file=file)  # type: ignore[union-attr]
            else:
                await channel.send(content=self.payload.text)  # type: ignore[union-attr]

            # Remove the preview message
            await interaction.response.edit_message(
                content="Posted!",
                embed=None,
                attachments=[],
                view=None,
            )
            logger.info(
                "shitpost.posted",
                extra={
                    "preview_id": self.preview_id,
                    "user_id": self.invoker_id,
                    "template_id": self.payload.template_id,
                },
            )
        except Exception as e:
            logger.error(
                "shitpost.post_failed",
                exc_info=True,
                extra={"preview_id": self.preview_id, "error": str(e)},
            )
            await interaction.response.send_message(
                f"Error posting meme: {e}", ephemeral=True
            )

    @discord.ui.button(
        label="Regenerate", style=discord.ButtonStyle.secondary, emoji="🔄"
    )
    async def regenerate_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Generate a new meme with a different template."""
        if self._posted:
            await interaction.response.send_message(
                "This meme has already been posted.", ephemeral=True
            )
            return

        if self.regenerate_callback is None:
            await interaction.response.send_message(
                "Regeneration not available.", ephemeral=True
            )
            return

        await interaction.response.defer()

        try:
            new_payload, new_embed = await self.regenerate_callback()
            await self._update_preview(interaction, new_payload, new_embed)
            logger.info(
                "shitpost.regenerated",
                extra={
                    "preview_id": self.preview_id,
                    "user_id": self.invoker_id,
                    "new_template_id": new_payload.template_id,
                },
            )
        except Exception as e:
            logger.error(
                "shitpost.regenerate_failed",
                exc_info=True,
                extra={"preview_id": self.preview_id, "error": str(e)},
            )
            await interaction.followup.send(
                f"Error regenerating meme: {e}", ephemeral=True
            )

    @discord.ui.button(label="Dismiss", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def dismiss_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Remove this preview message."""
        try:
            await interaction.response.edit_message(
                content=None,
                embed=None,
                attachments=[],
                view=None,
            )
            # Note: We can't truly delete ephemeral messages, but clearing content
            # and view effectively removes it visually
            logger.info(
                "shitpost.dismissed",
                extra={
                    "preview_id": self.preview_id,
                    "user_id": self.invoker_id,
                },
            )
        except Exception as e:
            logger.error(
                "shitpost.dismiss_failed",
                exc_info=True,
                extra={"preview_id": self.preview_id, "error": str(e)},
            )

    async def on_timeout(self) -> None:
        """Handle view timeout by disabling buttons."""
        logger.info(
            "shitpost.preview_timeout",
            extra={"preview_id": self.preview_id},
        )
        # Views on ephemeral messages can't be edited after timeout
        # without the original interaction, so we just log it
