# Clanker SDK Examples

This directory contains examples demonstrating how to reuse the core Clanker SDK across different platforms **without any Discord dependencies**.

## 🎯 Key Insight

The core SDK (`src/clanker/`) has **zero Discord dependencies**, making it trivially reusable in:
- ✅ Web applications (FastAPI, Flask)
- ✅ Mobile apps (via REST API)
- ✅ Messaging platforms (WhatsApp, Telegram, etc.)
- ✅ Command-line tools
- ✅ Any async Python application

**All examples reuse the exact same:**
- Shitpost generation pipeline
- Chat/conversation orchestration
- LLM/TTS provider abstraction
- Domain models and protocols

---

## 📚 Available Examples

| Example | Platform | Dependencies | Lines of Code | Complexity |
|---------|----------|--------------|---------------|------------|
| [Web API](#1-web-api-fastapi) | HTTP/REST | FastAPI, uvicorn | ~250 | ✅ Trivial |
| [WhatsApp Bot](#2-whatsapp-bot-twilio) | WhatsApp | Flask, Twilio | ~350 | ✅ Easy |
| [CLI Tool](#3-cli-tool-click) | Terminal | Click | ~300 | ✅ Easy |

---

## 1. Web API (FastAPI)

RESTful API demonstrating SDK reusability in web applications.

### Installation

```bash
# Install dependencies
uv sync --extra web

# Or with pip
pip install -e ".[web]"
```

### Configuration

```bash
export OPENAI_API_KEY=your_key_here
export ELEVENLABS_API_KEY=your_key_here  # Optional
```

### Usage

```bash
# Start server
uv run uvicorn examples.web_api:app --reload

# Server runs on http://localhost:8000
```

### Endpoints

- `GET /` - Health check
- `GET /templates` - List shitpost templates
- `GET /personas` - List chat personas
- `POST /shitpost` - Generate shitpost
- `POST /chat` - Chat with AI

### Example Requests

```bash
# Generate shitpost
curl -X POST http://localhost:8000/shitpost \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user123", "category": "roast"}'

# Chat
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello!", "user_id": "user123"}'
```

### Interactive Docs

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Demo Client

```bash
# Run example client
uv run python examples/client_example.py
```

---

## 2. WhatsApp Bot (Twilio)

WhatsApp bot using Twilio API, demonstrating messaging platform integration.

### Installation

```bash
# Install dependencies
uv sync --extra whatsapp

# Or with pip
pip install -e ".[whatsapp]"
```

### Configuration

```bash
export OPENAI_API_KEY=your_key_here
export ELEVENLABS_API_KEY=your_key_here  # Optional
export TWILIO_ACCOUNT_SID=your_twilio_sid
export TWILIO_AUTH_TOKEN=your_twilio_token
```

### Setup Twilio WhatsApp

1. **Create Twilio Account**: https://www.twilio.com/console
2. **Enable WhatsApp Sandbox**: https://www.twilio.com/console/sms/whatsapp/sandbox
3. **Note your sandbox number** (e.g., `whatsapp:+14155238886`)

### Local Development

```bash
# 1. Start the bot
uv run python examples/whatsapp_bot.py

# 2. In another terminal, start ngrok
ngrok http 5000

# 3. Copy the ngrok HTTPS URL (e.g., https://abc123.ngrok.io)

# 4. Configure Twilio webhook:
#    Go to: https://www.twilio.com/console/sms/whatsapp/sandbox
#    Set "When a message comes in" to: https://abc123.ngrok.io/webhook

# 5. Send a message to your Twilio WhatsApp number!
```

### WhatsApp Commands

Send these messages to your WhatsApp bot:

```
# Chat normally
What is Python?

# Generate shitpost
/shitpost

# Generate shitpost in category
/shitpost roast

# List templates
/templates

# Show help
/help
```

### Production Deployment

For production, deploy to:
- **Heroku**: Easy deployment with free tier
- **AWS Elastic Beanstalk**: Scalable with load balancing
- **DigitalOcean App Platform**: Simple container deployment
- **Railway/Render**: Modern PaaS options

Use `gunicorn` for production:
```bash
gunicorn examples.whatsapp_bot:app --workers 4 --bind 0.0.0.0:5000
```

---

## 3. CLI Tool (Click)

Command-line interface demonstrating SDK usage in terminal applications.

### Installation

```bash
# Install dependencies
uv sync --extra cli

# Or with pip
pip install -e ".[cli]"

# After installation, 'clanker' command is available
```

### Configuration

```bash
export OPENAI_API_KEY=your_key_here
export ELEVENLABS_API_KEY=your_key_here  # Optional
```

### Usage

```bash
# Show help
clanker --help

# Chat (one-off)
clanker chat "What is the meaning of life?"

# Chat (interactive mode)
clanker chat --interactive

# Chat with specific persona
clanker chat --persona shitposter "Tell me a joke"

# Generate shitpost
clanker shitpost

# Generate multiple shitposts
clanker shitpost --count 5

# Generate shitpost in category
clanker shitpost --category roast

# Generate from specific template
clanker shitpost --template one_liner

# List templates
clanker templates

# List personas
clanker personas

# Show SDK info
clanker info
```

### Interactive Mode

```bash
$ clanker chat --interactive
💬 Interactive chat with default
Type 'exit' or 'quit' to end the conversation

You: What is Python?
🤔 Thinking...

🤖 default:
Python is a high-level, interpreted programming language...

You: exit
👋 Goodbye!
```

### Features

- ✅ Colored output with Click styling
- ✅ Interactive and non-interactive modes
- ✅ Progress indicators
- ✅ Async command support
- ✅ Proper error handling
- ✅ Context management

---

## 🏗️ Architecture: The Adapter Pattern

All examples follow the same pattern:

```python
# 1. Import core SDK (no Discord!)
from clanker import respond, Context, Message
from clanker.shitposts import render_shitpost, load_templates
from clanker.providers import ProviderFactory

# 2. Initialize providers (same as Discord bot)
factory = ProviderFactory()
llm = factory.get_llm("openai")
tts = factory.get_tts("elevenlabs")

# 3. Create platform adapter
def build_context(platform_data) -> Context:
    """Convert platform-specific data to SDK Context."""
    return Context(
        request_id=...,
        user_id=...,
        guild_id=None,  # Not applicable
        channel_id=...,
        persona=...,
        messages=[...],
        metadata={"source": "your_platform"},
    )

# 4. Use SDK functions directly
reply = await render_shitpost(context, llm, request)
reply, audio = await respond(context, llm, tts)

# 5. Convert SDK output to platform response
return platform_specific_format(reply.content)
```

## 📊 Reusability Comparison

| Component | Discord Bot | Web API | WhatsApp | CLI |
|-----------|-------------|---------|----------|-----|
| **Core SDK** | ✅ | ✅ | ✅ | ✅ |
| **Shitpost generation** | ✅ | ✅ | ✅ | ✅ |
| **Chat/respond** | ✅ | ✅ | ✅ | ✅ |
| **LLM providers** | ✅ | ✅ | ✅ | ✅ |
| **TTS providers** | ✅ | ✅ | ✅ | ✅ |
| **Platform adapter** | Discord.py | HTTP/JSON | Twilio/TwiML | Click/Terminal |
| **Adapter size** | ~400 lines | ~250 lines | ~350 lines | ~300 lines |
| **SDK changes needed** | 0 | 0 | 0 | 0 |

**Key Takeaway**: The core SDK is 100% reusable. Only the platform adapter changes.

---

## 🚀 Extending to Other Platforms

Want to build for another platform? Here's the effort estimate:

| Platform | Adapter Needed | Estimated LOC | Complexity |
|----------|----------------|---------------|------------|
| **Telegram bot** | python-telegram-bot | ~250 lines | ✅ Easy |
| **Slack bot** | slack-bolt | ~200 lines | ✅ Easy |
| **Discord DMs only** | discord.py (minimal) | ~150 lines | ✅ Trivial |
| **SMS (Twilio)** | Flask + Twilio | ~200 lines | ✅ Easy |
| **GraphQL API** | Strawberry/Ariadne | ~300 lines | ✅ Medium |
| **gRPC API** | grpcio | ~400 lines | ⚠️ Medium |
| **Mobile app (REST)** | Same as Web API | 0 lines | ✅ Trivial |
| **Alexa Skill** | Flask-ask | ~300 lines | ⚠️ Medium |
| **iOS Keyboard** | Swift + Python bridge | ~600 lines | ❌ Hard |

### Pattern for Any Platform

1. **Install platform SDK** (e.g., telegram, slack-bolt)
2. **Write adapter** (~200-400 lines):
   - Convert platform input → SDK `Context`
   - Call SDK functions
   - Convert SDK output → platform response
3. **Done!** All AI logic is reused from the SDK

---

## 📝 Code Structure

```
examples/
├── README.md              # This file
├── web_api.py            # FastAPI web server
├── whatsapp_bot.py       # Twilio WhatsApp bot
├── cli_tool.py           # Click CLI application
└── client_example.py     # Demo client for web API

Shared dependencies:
├── src/clanker/          # Core SDK (platform-agnostic)
│   ├── respond.py        # Chat orchestration
│   ├── shitposts/        # Shitpost generation
│   ├── providers/        # LLM/TTS abstraction
│   ├── models.py         # Domain models
│   └── config/           # Configuration
└── config.yaml           # Shared configuration
```

---

## 🔧 Development Best Practices

### Research Sources

This implementation follows best practices from:

**WhatsApp/Twilio:**
- [Twilio WhatsApp Bot with Python and Flask](https://www.twilio.com/en-us/blog/build-a-whatsapp-chatbot-with-python-flask-and-twilio)
- [Building WhatsApp bot on Python - GeeksforGeeks](https://www.geeksforgeeks.org/python/building-whatsapp-bot-on-python/)
- [WhatsApp Chatbot Using Python and Twilio API](https://dev.to/gbwadown/how-to-build-a-whatsapp-chatbot-using-python-and-twilio-api-2c75)

**Click CLI:**
- [Click Official Documentation](https://click.palletsprojects.com/)
- [Building User-Friendly Python CLI with Click](https://www.qodo.ai/blog/building-user-friendly-python-command-line-interfaces-with-click-and-command-line/)
- [Creating composable CLIs with click](https://betterstack.com/community/guides/scaling-python/click-explained/)

### Async Handling

- **Web API**: FastAPI is async-native ✅
- **WhatsApp**: Flask is sync, use `asyncio.run()` in webhook
- **CLI**: Click is sync, use decorator with `asyncio.run()`

### Error Handling

All examples include:
- Graceful error messages
- Logging for debugging
- Fallback responses
- Input validation

### Testing

All adapters can be tested independently:

```python
# Test the adapter (no external APIs needed)
from examples.web_api import build_web_context
from tests.fakes import FakeLLM

context = build_web_context("user123", "session456", persona)
reply = await render_shitpost(context, FakeLLM(), request)
```

---

## 💡 Tips & Tricks

### Environment Variables

Create a `.env` file for development:

```bash
OPENAI_API_KEY=sk-...
ELEVENLABS_API_KEY=...
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
```

Use `python-dotenv` to load:
```python
from dotenv import load_dotenv
load_dotenv()
```

### Production Considerations

Before deploying to production, add:
- **Authentication/Authorization**
- **Rate limiting** (prevent abuse)
- **Caching** (reduce API costs)
- **Monitoring** (logs, metrics, alerts)
- **Database** (store conversation history)
- **Queue system** (handle high traffic)
- **Error tracking** (Sentry, Rollbar)

### Cost Optimization

- Cache LLM responses for common queries
- Use cheaper models for simple tasks
- Implement request throttling
- Add usage analytics

---

## ❓ FAQ

**Q: Do I need Discord to use these examples?**
A: No! That's the whole point. The SDK has zero Discord dependencies.

**Q: Can I use a different LLM provider?**
A: Yes! The SDK uses protocol-based providers. Swap OpenAI for Anthropic, Cohere, etc. by implementing the `LLM` protocol.

**Q: Can I deploy these to production?**
A: Yes, but add authentication, rate limiting, monitoring, etc. first.

**Q: How do I add a new platform?**
A: Write a ~200-300 line adapter following the pattern shown above.

**Q: Will the SDK work with older Python versions?**
A: Requires Python 3.10+. Uses modern async/await, type hints, and dataclasses.

**Q: Can I use this for commercial projects?**
A: Check the license in the root README.

---

## 🎓 Next Steps

1. **Try the examples** - Start with the web API or CLI
2. **Read the code** - See how simple the adapters are
3. **Build your own** - Pick a platform and write an adapter
4. **Share it** - Contribute your adapter as an example!

**Remember**: The hard work (AI logic, provider abstraction, models) is already done in the SDK. You just need a thin adapter for your platform.
