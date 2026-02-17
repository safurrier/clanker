# Docker Setups for Clanker9000

This directory contains Docker configurations for both **development** and **production** environments.

## Quick Reference

| File | Purpose |
|------|---------|
| `Dockerfile` | Development environment with Silero VAD |
| `Dockerfile.prod` | Production build (optimized) |
| `docker-compose.yml` | Development setup (mounts code) |
| `docker-compose.prod.yml` | Production deployment |
| `template.env` | Environment variables template |
| `DEPLOYMENT.md` | Full production deployment guide |

---

## Development Environment

**Purpose:** Interactive development with hot-reload

### Setup

1. Copy template.env to .env:
   ```bash
   cp docker/template.env docker/.env
   # Edit docker/.env with your API keys
   ```

2. Start dev environment:
   ```bash
   make dev-env
   # or directly:
   docker compose -f docker/docker-compose.yml up -d dev
   docker exec -it composed_dev /bin/bash
   ```

3. Inside container:
   ```bash
   # Run tests
   pytest tests -m "not network"

   # Run the bot
   python -m clanker_bot.main

   # Run checks
   make check
   ```

### Features

- ✅ Full project directory mounted at `/workspace`
- ✅ All dependencies pre-installed (including voice support)
- ✅ Silero VAD model pre-downloaded
- ✅ Development tools (vim, make, etc.)
- ✅ Code changes reflected immediately (no rebuild needed)

---

## Production Deployment

**Purpose:** Optimized, standalone bot deployment

### Quick Start

1. Create `.env` file:
   ```bash
   # In project root
   cp docker/template.env .env
   # Edit .env with your production credentials
   ```

2. Deploy:
   ```bash
   docker-compose -f docker/docker-compose.prod.yml up -d

   # View logs
   docker-compose -f docker/docker-compose.prod.yml logs -f clanker-bot
   ```

### Features

- ✅ Optimized multi-stage build (~500MB smaller)
- ✅ Pre-downloaded Silero VAD model
- ✅ Voice support (torch/numpy) included
- ✅ Persistent torch model cache
- ✅ Auto-restart on failure
- ✅ Resource limits (2-4GB RAM)

See **`DEPLOYMENT.md`** for comprehensive production deployment guide.

---

## Comparing Dev vs Prod

| Aspect | Development | Production |
|--------|-------------|------------|
| **Base Image** | `python:3.12-slim` | `python:3.11-slim` |
| **Size** | Larger (dev tools) | Smaller (minimal) |
| **Code** | Mounted volume | Copied into image |
| **Hot-reload** | ✅ Yes | ❌ No |
| **Build time** | Faster (cached deps) | Slower (full build) |
| **Tools** | vim, make, curl, etc. | Minimal |
| **Use case** | Local development | Deployment |

---

## Voice Support

Both environments include:
- **libopus** for Discord audio decoding (required for voice receive)
- Pre-downloaded Silero VAD model at `/workspace/silero-vad` or `/app/silero-vad`
- torch and numpy dependencies
- Voice extras: `uv sync --all-extras` (dev) or `pip install -e ".[voice]"` (prod)

The bot explicitly loads opus at startup and fails fast if unavailable.

The Silero VAD model is cloned during image build, avoiding:
- Runtime downloads (faster startup)
- Rate limiting from GitHub
- Network dependencies in production

---

## Makefile Commands

From project root:

```bash
# Development
make dev-env            # Start dev container and enter shell
make refresh-containers # Rebuild and restart containers
make rebuild-images     # Rebuild without cache

# Production (use docker-compose directly)
docker-compose -f docker/docker-compose.prod.yml up -d
docker-compose -f docker/docker-compose.prod.yml down
```

---

## Troubleshooting

### Dev Environment

**Container won't start:**
```bash
make rebuild-images
```

**Dependencies out of sync:**
```bash
# Inside container
uv sync --all-extras
```

### Production

**Voice processing fails:**
```bash
# Check Silero VAD model
docker exec clanker-bot ls -la /app/silero-vad
docker logs clanker-bot | grep -i vad
```

**Out of memory:**
```bash
# Edit docker/docker-compose.prod.yml
# Increase memory limit to 8GB or use EnergyVAD
```

See `DEPLOYMENT.md` for more troubleshooting tips.

---

## Environment Variables

Required for both dev and prod:
- `DISCORD_TOKEN` - Discord bot token
- `OPENAI_API_KEY` - OpenAI API key (for LLM and STT)

Optional:
- `ELEVENLABS_API_KEY` - Text-to-speech (ElevenLabs)
- `CLANKER_CONFIG_PATH` - Custom config file path

Edit `template.env` and copy to `.env` or `docker/.env` depending on your setup.
