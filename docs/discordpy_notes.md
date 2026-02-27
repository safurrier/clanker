# discord.py Notes

## Command registration
- Use `discord.app_commands.CommandTree` to register slash commands.
- Sync commands during `on_ready` to ensure they appear in the target guilds.
- Keep slash command handlers thin; they should build `Context` and call SDK functions.

## Permissions + intents
- `discord.Intents.default()` is sufficient for slash commands.
- Message content intent is not required for app commands.
- Voice commands require `GuildVoiceStates` intent (handled by default intents in v2).

## Threads + attachments
- Use `interaction.response.send_message()` for initial responses.
- Use `discord.File` with `io.BytesIO` for in-memory TTS audio.

## dpytest harness
- dpytest targets `discord.ext.commands` (message commands), not `app_commands`.
- Use dpytest for message-command coverage and rely on handler unit tests for slash commands.
- Use fakes for `Interaction` responses when command tree integration is unavailable.
