# Web API Example

This example demonstrates how to reuse the core Clanker SDK in a web application without any Discord dependencies.

## What This Shows

The web API reuses the exact same AI capabilities as the Discord bot:
- **Shitpost generation** - template-based LLM content generation
- **Chat** - conversation with personas
- **Provider abstraction** - same LLM/TTS providers

**Key insight**: The core SDK (`src/clanker/`) has zero Discord dependencies, making it trivially reusable in other platforms.

## Quick Start

### 1. Install Dependencies

```bash
# Install web dependencies
uv sync --extra web

# Or with pip
pip install -e ".[web]"
```

### 2. Set Environment Variables

```bash
export OPENAI_API_KEY=your_key_here
export ELEVENLABS_API_KEY=your_key_here  # Optional
```

### 3. Run the Server

```bash
# From the project root
uv run uvicorn examples.web_api:app --reload

# Or
uv run python -m examples.web_api
```

The API will be available at `http://localhost:8000`

## API Endpoints

### GET /

Health check - shows available providers and personas.

```bash
curl http://localhost:8000/
```

### GET /templates

List all available shitpost templates.

```bash
curl http://localhost:8000/templates
```

**Response:**
```json
{
  "count": 15,
  "categories": ["roast", "advice", "fact"],
  "templates": [
    {
      "name": "one_liner",
      "category": "roast",
      "description": "Short, punchy roast",
      "variables": ["target"]
    }
  ]
}
```

### GET /personas

List all available chat personas.

```bash
curl http://localhost:8000/personas
```

### POST /shitpost

Generate a shitpost using the same pipeline as the Discord bot.

```bash
curl -X POST http://localhost:8000/shitpost \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user123",
    "category": "roast",
    "variables": {"target": "JavaScript"}
  }'
```

**Response:**
```json
{
  "shitpost": "JavaScript? More like 'JavaScr-ipt to uninstall my sanity'",
  "template_used": "one_liner"
}
```

**Parameters:**
- `user_id` (required): Unique user identifier
- `category` (optional): Template category (`roast`, `advice`, `fact`)
- `template_name` (optional): Specific template to use
- `variables` (optional): Variables to pass to the template

### POST /chat

Chat with a persona using the same `respond()` function as the Discord bot.

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What is the meaning of life?",
    "user_id": "user123",
    "session_id": "session456",
    "persona_name": "default"
  }'
```

**Response:**
```json
{
  "reply": "42, obviously. But if you're looking for a deeper answer...",
  "audio_url": null
}
```

**Parameters:**
- `message` (required): User's message
- `user_id` (required): Unique user identifier
- `session_id` (optional): Session/conversation ID for context
- `persona_name` (optional): Persona to use (default: "default")

## Interactive API Docs

FastAPI provides automatic interactive documentation:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Architecture Highlights

### Zero Discord Dependencies

```python
# This imports ONLY the SDK - no Discord code
from clanker import respond, Context, Message
from clanker.shitposts import render_shitpost, load_templates
from clanker.providers import ProviderFactory
```

### Platform Adapter Pattern

The web API implements a simple adapter to convert HTTP requests into SDK `Context`:

```python
def build_web_context(
    user_id: str,
    session_id: str | None,
    persona: Persona,
) -> Context:
    """Convert web request to SDK Context."""
    return Context(
        request_id=str(uuid.uuid4()),
        user_id=int(hash(user_id)) % (2**31),
        guild_id=None,  # Not applicable for web
        channel_id=int(hash(session_id or "default")) % (2**31),
        persona=persona,
        messages=[],
        metadata={"source": "web"},
    )
```

### Reuses SDK Functions Directly

```python
# Same function used by the Discord bot!
reply, audio = await respond(context, llm, tts)

# Same shitpost generation!
shitpost = await render_shitpost(context, llm, request)
```

## Extending to Other Platforms

This pattern can be adapted for any platform:

| Platform | Adapter Needed | Complexity |
|----------|----------------|------------|
| **Mobile app (REST)** | Same as this example | ✅ Trivial |
| **Telegram bot** | Telegram → Context adapter | ✅ Easy (~200 lines) |
| **WhatsApp** | WhatsApp webhook adapter | ✅ Easy (~300 lines) |
| **CLI tool** | argparse → Context adapter | ✅ Trivial (~100 lines) |
| **GraphQL API** | GraphQL resolver adapter | ✅ Easy (~200 lines) |

The key is always the same:
1. Convert platform-specific input → SDK `Context`
2. Call SDK functions (which have no platform dependencies)
3. Convert SDK output → platform-specific response

## Code Structure

```
examples/web_api.py
├── Platform adapter (build_web_context)
├── Provider initialization (same as Discord bot)
├── Endpoints (HTTP → SDK → HTTP)
└── Response models (Pydantic)

Depends on:
├── src/clanker/          # Core SDK (no Discord!)
│   ├── respond.py        # Chat orchestration
│   ├── shitposts/        # Shitpost generation
│   ├── providers/        # LLM/TTS abstraction
│   └── models.py         # Domain models
└── config.yaml           # Shared configuration
```

## What's NOT Included

This example intentionally keeps it simple and doesn't include:
- Authentication/authorization
- Rate limiting
- Database/persistent sessions
- Audio file hosting (TTS audio is generated but not stored)
- WebSocket support for streaming
- Production deployment configuration

These would be added based on your specific platform requirements.

## Performance Notes

- Provider initialization happens once at startup (via `lifespan`)
- Each request is stateless (no session management)
- Async all the way through (FastAPI → SDK → OpenAI/ElevenLabs)
- Same performance characteristics as the Discord bot

## Next Steps

To build a production web app, you'd add:
- **Auth**: API keys, OAuth, JWT tokens
- **Database**: Store conversation history, user preferences
- **Caching**: Redis for frequently accessed data
- **Rate limiting**: Per-user request limits
- **Monitoring**: Logging, metrics, error tracking
- **Audio storage**: S3/CDN for TTS audio files

But the core AI logic? **Already done.** You just reuse the SDK.
