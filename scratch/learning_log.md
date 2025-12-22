# Learning Log

## discord.py
- Slash commands are registered via `app_commands.CommandTree`.
- `on_ready` should sync commands.

## dpytest
- dpytest focuses on `discord.ext.commands` message commands; slash command coverage is limited.

## Voice ingest
- V1 uses energy-based VAD to avoid heavy torch dependencies.
