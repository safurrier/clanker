# Discord Bot Module — Agent Instructions

Discord.py integration layer. Depends on the Clanker SDK (`src/clanker/`) for all business logic.

## File Structure

```
clanker_bot/
├── main.py                 # Entry point, dependency injection, health server
├── commands.py             # Slash command registration (register_commands())
├── discord_adapter.py      # Discord-specific adapters, voice session management
├── voice_ingest.py         # Discord audio capture → SDK pipeline
├── voice_resilience.py     # Voice connection keepalive and reconnection
├── voice_actor.py          # Actor-based voice management (USE_VOICE_ACTOR flag)
├── logging_config.py       # Loguru structured logging with file rotation
├── health.py               # Health check HTTP endpoint (/status)
├── metrics.py              # Observability counters/gauges
├── admin.py                # Admin utilities
│
├── command_handlers/       # Slash command implementations
│   ├── __init__.py         # Exports all handlers
│   ├── types.py            # Handler type definitions
│   ├── common.py           # Shared handler utilities
│   ├── admin.py            # Admin command handlers
│   ├── chat.py             # /chat and /speak handlers
│   ├── messages.py         # Message command handlers
│   ├── thread_chat.py      # Thread auto-reply handler
│   ├── transcript.py       # /transcript handler
│   └── voice.py            # /join and /leave handlers
│
├── views/                  # Discord UI views
│   └── shitpost_preview.py # Shitpost preview with approve/reject buttons
│
├── cogs/                   # Discord cogs
│   └── vc_monitor.py       # Voice channel monitoring, auto-leave
│
└── persistence/            # Database layer
    ├── connection.py       # SQLAlchemy async engine (module-level global)
    ├── sql_feedback.py     # FeedbackStore implementation
    ├── db/
    │   ├── schema.sql      # Database schema
    │   └── queries/        # sqlc query definitions
    └── generated/          # sqlc-generated Python (DO NOT EDIT)
```

## Slash Commands

| Command | Handler | Description |
|---------|---------|-------------|
| `/chat` | `command_handlers/chat.py` | Chat with LLM |
| `/speak` | `command_handlers/chat.py` | Chat with TTS audio response |
| `/shitpost` | `command_handlers/chat.py` | Generate shitpost with preview |
| `/join` | `command_handlers/voice.py` | Join voice channel |
| `/leave` | `command_handlers/voice.py` | Leave voice channel |
| `/transcript` | `command_handlers/transcript.py` | Show recent voice transcripts |
| `/admin_*` | `command_handlers/admin.py` | Admin-only commands |

### Adding a New Slash Command

1. Create handler in `command_handlers/` (or add to existing file)
2. Export from `command_handlers/__init__.py`
3. Register in `commands.py` `register_commands()` function
4. Add tests in `tests/test_commands.py`

## Voice Ingest

`voice_ingest.py` bridges Discord audio to the SDK voice pipeline:

1. `VoiceIngestSink` receives raw stereo PCM from `discord-ext-voice-recv`
2. Converts stereo to mono, resamples from 48kHz to 16kHz
3. Feeds into `AudioBuffer` per user
4. `transcript_loop_once()` processes buffered audio through VAD → chunk → STT
5. `TranscriptEvent` emitted via callback

### Voice Resilience

`voice_resilience.py` provides `VoiceKeepalive`:
- Heartbeat pings to detect stale connections
- Automatic reconnection on disconnect
- Expected vs unexpected disconnect tracking

### Voice Actor

`voice_actor.py` — actor-based voice management behind `USE_VOICE_ACTOR` flag:
- Encapsulates voice state in an actor pattern
- Thread-safe message passing
- Experimental, not yet default

### TranscriptBuffer

In `voice_ingest.py`, `TranscriptBuffer` maintains a rolling buffer of recent transcripts per guild:
- Used by shitpost command for voice context
- Max 50 events, max 5 minutes age
- Keyed by guild_id (one voice connection per guild)

## Thread Auto-Reply

`command_handlers/thread_chat.py` handles messages in bot-created threads:
- Thread names matching `clanker-{hex}` pattern get automatic LLM responses
- Maintains conversation context within the thread

## Persistence

SQL-based persistence using sqlc-generated queries with SQLAlchemy async:

- `connection.py` — module-level `AsyncEngine` with explicit `init_pool()`/`close_pool()`
- `sql_feedback.py` — implements `FeedbackStore` protocol
- `generated/` — sqlc output (never edit manually)

### Modifying queries

```bash
# Edit db/queries/*.sql, then:
sqlc generate
python3 scripts/fix_sqlc_placeholders.py
uv run ruff check src/clanker_bot/persistence/generated/ --fix
uv run ruff format src/clanker_bot/persistence/generated/
```

## Logging

`logging_config.py` uses loguru with:
- Structured JSON format for file logs
- Console output with colors
- Separate voice log level (`VOICE_LOG_LEVEL`)
- File rotation when `LOG_DIR` is set

## Testing

- `tests/test_commands.py` — slash command tests (dpytest)
- `tests/test_voice_ingest.py` — voice ingest tests
- `tests/test_voice_resilience.py` — keepalive/reconnect tests
- `tests/test_voice_actor.py` — actor pattern tests
- `tests/test_vc_monitor.py` — VC monitor cog tests
- `tests/test_thread_chat.py` — thread auto-reply tests
- `tests/test_shitpost_preview_view.py` — UI view tests

## Gotchas

- Discord.py is async-native; all handlers must be async
- `discord-ext-voice-recv` provides raw stereo PCM at 48kHz — conversion happens in `voice_ingest.py`
- The bot loads opus explicitly at startup and fails fast if unavailable (required for voice)
- `register_commands()` is called once at startup; command tree syncs with Discord API
- Thread auto-reply checks thread name pattern to avoid responding in unrelated threads
- Persistence is optional — bot works without database (feedback logging disabled)
