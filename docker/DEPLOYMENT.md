# Docker Deployment Guide

## Quick Start

### 1. Set Environment Variables

Create a `.env` file in the project root:

```bash
# Required
DISCORD_TOKEN=your_discord_bot_token_here
OPENAI_API_KEY=your_openai_api_key_here

# Optional
ELEVENLABS_API_KEY=your_elevenlabs_api_key_here
```

### 2. Build and Run with Docker Compose

```bash
# Build the image
docker-compose build

# Run the bot
docker-compose up -d

# View logs
docker-compose logs -f clanker-bot

# Stop the bot
docker-compose down
```

## Manual Docker Commands

### Build Image

```bash
docker build -t clanker9000:latest .
```

### Run Container

```bash
docker run -d \
  --name clanker-bot \
  --restart unless-stopped \
  -e DISCORD_TOKEN=$DISCORD_TOKEN \
  -e OPENAI_API_KEY=$OPENAI_API_KEY \
  -e ELEVENLABS_API_KEY=$ELEVENLABS_API_KEY \
  -v $(pwd)/config.yaml:/app/config.yaml:ro \
  -v torch-cache:/app/.cache/torch \
  clanker9000:latest
```

### View Logs

```bash
docker logs -f clanker-bot
```

### Stop and Remove

```bash
docker stop clanker-bot
docker rm clanker-bot
```

## Features of the Docker Setup

### Pre-downloaded Silero VAD Model

The Dockerfile includes a multi-stage build that:
- Clones the Silero VAD repository during build time
- Copies it into the final image
- Avoids rate limiting from the Silero repo in production
- Enables faster startup (no download needed)

### Optimized Python Environment

- Uses `uv` for fast package installation
- Installs with `[voice]` extras for torch/numpy support
- Slim base image to reduce size
- System-wide pip installation for simpler deployment

### Persistent Storage

The docker-compose setup includes:
- **torch-cache volume**: Persists downloaded PyTorch models
- **config.yaml mount**: Use your local config file
- **logs directory**: Optional log persistence

### Resource Limits

Default limits (adjust in docker-compose.yml):
- **CPU**: 1-2 cores
- **Memory**: 2-4 GB

Voice processing with Silero VAD requires more memory than Energy VAD.

## Development Setup with Docker

For development, you can mount the source code:

```bash
docker run -it --rm \
  -v $(pwd)/src:/app/src \
  -e DISCORD_TOKEN=$DISCORD_TOKEN \
  -e OPENAI_API_KEY=$OPENAI_API_KEY \
  clanker9000:latest \
  bash
```

Then run commands inside the container:
```bash
# Run tests
pytest tests -m "not network"

# Start the bot
python -m clanker_bot.main
```

## Troubleshooting

### Silero VAD Model Not Loading

If you see errors about Silero VAD:

1. Check that the image was built with the multi-stage process:
   ```bash
   docker run --rm clanker9000:latest ls -la /app/silero-vad
   ```

2. Verify torch is installed:
   ```bash
   docker run --rm clanker9000:latest python -c "import torch; print(torch.__version__)"
   ```

3. Check logs for fallback to EnergyVAD:
   ```bash
   docker logs clanker-bot | grep -i "vad"
   ```

### Out of Memory

If the bot crashes with OOM errors:

1. Increase memory limit in docker-compose.yml:
   ```yaml
   deploy:
     resources:
       limits:
         memory: 8G
   ```

2. Or use EnergyVAD instead of Silero by setting in config.yaml:
   ```yaml
   voice:
     detector: "energy"
   ```

### Permission Issues

If you get permission errors with volumes:

```bash
# Fix ownership (Linux)
sudo chown -R $(id -u):$(id -g) logs/

# Or run with user mapping
docker run --user $(id -u):$(id -g) ...
```

## Production Deployment

### Using Docker Swarm

```bash
docker stack deploy -c docker-compose.yml clanker
```

### Using Kubernetes

Convert the docker-compose.yml to k8s manifests:

```bash
kompose convert -f docker-compose.yml
kubectl apply -f .
```

### Health Monitoring

Add a health check endpoint to your bot and uncomment the HEALTHCHECK in the Dockerfile.

### Secrets Management

For production, use Docker secrets or Kubernetes secrets instead of environment variables:

```bash
echo "$DISCORD_TOKEN" | docker secret create discord_token -
echo "$OPENAI_API_KEY" | docker secret create openai_key -
```

Then update docker-compose.yml to use secrets instead of environment variables.
