FROM python:3.12-slim AS builder

# Install build dependencies and git
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Clone Silero VAD model (for voice support)
FROM builder AS silero-vad
RUN git clone https://github.com/snakers4/silero-vad.git /silero-vad && \
    rm -rf /silero-vad/.git

# Development image with all tools
FROM python:3.12-slim

# Install development tools and libopus for Discord voice
RUN apt-get update && apt-get install -y --no-install-recommends \
    make \
    curl \
    gcc \
    git \
    vim \
    libopus0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# Install uv and pre-install dependencies
# Note: The project itself is mounted at runtime, so we just need deps
COPY pyproject.toml uv.lock README.md /tmp/deps/
COPY src /tmp/deps/src

RUN pip install -U pip uv \
    && cd /tmp/deps \
    && uv pip install --system ".[voice]" \
    && rm -rf /tmp/deps

# Copy pre-downloaded Silero model for voice support
COPY --from=silero-vad /silero-vad /workspace/silero-vad

# Set environment for voice processing
ENV PYTHONUNBUFFERED=1
ENV TORCH_HOME=/workspace/.cache/torch
ENV SILERO_VAD_PATH=/workspace/silero-vad

CMD ["/bin/bash"]
