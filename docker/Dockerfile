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

# Install Auxiliary Software for development
RUN apt-get update && apt-get install -y \
    make \
    apt-utils \
    apt-transport-https \
    curl \
    gcc \
    gnupg \
    gnupg-agent \
    graphviz \
    software-properties-common \
    vim \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# Copy essential files for dependency resolution to temp location
COPY pyproject.toml uv.lock /tmp/
COPY README.md /tmp/

RUN pip install -U pip uv \
    && cd /tmp \
    && uv sync --system --all-extras \
    && rm -rf /tmp/pyproject.toml /tmp/uv.lock /tmp/README.md

# Copy pre-downloaded Silero model for voice support
COPY --from=silero-vad /silero-vad /workspace/silero-vad

# Set environment for voice processing
ENV PYTHONUNBUFFERED=1
ENV TORCH_HOME=/workspace/.cache/torch
ENV SILERO_VAD_PATH=/workspace/silero-vad

CMD ["/bin/bash"]
