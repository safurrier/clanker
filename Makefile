.PHONY: compile-deps setup clean-pyc clean-test clean-venv clean test ty lint format check clean-example docs-install docs-build docs-serve docs-check docs-clean dev-env refresh-containers rebuild-images build-image push-image setup-agent-docs

# Module name - will be updated by init script
MODULE_NAME := clanker
SRC_DIR := src

# Development Setup
#################
compile-deps:  # Compile dependencies from pyproject.toml
	uv pip compile pyproject.toml -o requirements.txt
	uv pip compile pyproject.toml --extra dev -o requirements-dev.txt

PYTHON_VERSION ?= 3.12

ensure-uv:  # Install uv if not present
	@which uv > /dev/null || (curl -LsSf https://astral.sh/uv/install.sh | sh)

setup: ensure-uv ensure-scripts  # Install dependencies
	UV_PYTHON_VERSION=$(PYTHON_VERSION) uv sync --all-extras
	$(MAKE) install-hooks
	$(MAKE) setup-agent-docs

install-hooks:  # Install pre-commit hooks if in a git repo with hooks configured
	@if [ -d .git ] && [ -f .pre-commit-config.yaml ]; then \
		echo "Installing pre-commit hooks..."; \
		uv run pre-commit install -f --hook-type pre-commit; \
	fi

setup-agent-docs:  # Create CLAUDE.md symlink to AGENTS.md for AI agent compatibility
	@if [ -f AGENTS.md ] && [ ! -e CLAUDE.md ]; then \
		echo "Creating CLAUDE.md symlink to AGENTS.md..."; \
		ln -s AGENTS.md CLAUDE.md; \
	fi

ensure-scripts:  # Ensure scripts directory exists and files are executable
	mkdir -p scripts
	chmod +x scripts/*.py

# Cleaning
#########
clean-pyc:  # Remove Python compilation artifacts
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +
	find . -name '__pycache__' -exec rm -fr {} +

clean-test:  # Remove test and coverage artifacts
	rm -f .coverage
	rm -f .coverage.*

clean-venv:  # Remove virtual environment
	rm -rf .venv

clean: clean-pyc clean-test clean-venv

# Testing and Quality Checks
#########################
test: setup  # Run pytest with coverage (excluding network tests)
	uv run -m pytest tests -m "not network" --cov=$(MODULE_NAME) --cov-report=term-missing

ty: setup  # Run type checking
	uv run ty check $(SRC_DIR)

lint: setup  # Run ruff linter with auto-fix
	uv run -m ruff check --fix $(SRC_DIR)

format: setup  # Run ruff formatter
	uv run -m ruff format $(SRC_DIR)

check: setup lint format test ty  # Run all quality checks

# Local CI Testing with act
###########################

# Detect docker socket (Colima, Docker, or Podman)
define docker_socket
$(shell \
	if [ -S $$HOME/.colima/default/docker.sock ]; then \
		echo "$$HOME/.colima/default/docker.sock"; \
	elif [ -S /var/run/docker.sock ]; then \
		echo "/var/run/docker.sock"; \
	elif [ -S $$HOME/.docker/run/docker.sock ]; then \
		echo "$$HOME/.docker/run/docker.sock"; \
	elif [ -S /run/user/$$(id -u)/podman/podman.sock ]; then \
		echo "/run/user/$$(id -u)/podman/podman.sock"; \
	else \
		echo "/var/run/docker.sock"; \
	fi \
)
endef

DOCKER_SOCKET := $(docker_socket)
ACT_IMAGE := catthehacker/ubuntu:act-22.04
ACT_ARCH := linux/amd64

act-check:  # Check if act is installed, install if missing
	@if ! which act > /dev/null 2>&1; then \
		echo "⚠️  act is not installed. Installing automatically..."; \
		$(MAKE) act-install; \
	fi

docker-check:  # Check if Docker/Podman/Colima is running
	@if ! DOCKER_HOST="unix://$(DOCKER_SOCKET)" docker ps >/dev/null 2>&1; then \
		echo "❌ Cannot connect to Docker daemon"; \
		echo ""; \
		echo "Please start your container runtime first:"; \
		echo "  • Docker Desktop: Open Docker Desktop app"; \
		echo "  • Colima: run 'colima start'"; \
		echo "  • Podman: run 'podman machine start'"; \
		echo "  • Docker (Linux): run 'sudo systemctl start docker'"; \
		echo ""; \
		echo "Attempted socket: $(DOCKER_SOCKET)"; \
		exit 1; \
	fi
	@echo "✓ Docker is running (socket: $(DOCKER_SOCKET))"

act-install:  ## Install act for local CI testing
	@echo "Installing act (GitHub Actions local runner)..."
	@if which act > /dev/null 2>&1; then \
		echo "✅ act is already installed: $$(which act)"; \
		act --version; \
	elif which brew > /dev/null 2>&1; then \
		echo "📦 Installing act via Homebrew..."; \
		brew install act; \
	else \
		echo "📦 Installing act via install script..."; \
		curl --proto '=https' --tlsv1.2 -sSf https://raw.githubusercontent.com/nektos/act/master/install.sh | sudo bash; \
	fi
	@echo ""
	@echo "✅ act installed successfully!"
	@echo "💡 Run 'make ci-list' to see available workflows"
	@echo "💡 Run 'make ci-local' to run CI checks locally"

ci-list: act-check docker-check  ## List available GitHub Actions workflows and jobs
	@echo "📋 Available workflows and jobs:"
	@DOCKER_HOST="unix://$(DOCKER_SOCKET)" act -l

ci-local: act-check docker-check  ## Run CI checks locally (tests workflow)
	@echo "🔬 Running local CI checks..."
	@echo "Using Docker socket: $(DOCKER_SOCKET)"
	@echo "Container architecture: $(ACT_ARCH)"
	@echo "Image: $(ACT_IMAGE)"
	@echo ""
	@JOB=$${JOB:-checks}; \
	DOCKER_HOST="unix://$(DOCKER_SOCKET)" act pull_request \
		-W .github/workflows/tests.yml \
		-j $$JOB \
		--container-daemon-socket - \
		--container-architecture $(ACT_ARCH) \
		-P ubuntu-latest=$(ACT_IMAGE)
	@echo ""
	@echo "✅ Local CI checks complete!"

ci-local-docs: act-check docker-check  ## Run documentation build check locally
	@echo "📚 Running local documentation build check..."
	@DOCKER_HOST="unix://$(DOCKER_SOCKET)" act pull_request \
		-W .github/workflows/docs.yml \
		-j build-check \
		--container-daemon-socket - \
		--container-architecture $(ACT_ARCH) \
		-P ubuntu-latest=$(ACT_IMAGE)
	@echo ""
	@echo "✅ Documentation build check complete!"

ci-debug: act-check docker-check  ## Fast local test debugging (uses ci-debug.yml workflow)
	@echo "🔧 Running CI debug workflow for fast iteration"
	@echo "💡 Edit .github/workflows/ci-debug.yml to customize which tests run"
	@echo ""
	@DOCKER_HOST="unix://$(DOCKER_SOCKET)" act workflow_dispatch \
		-W .github/workflows/ci-debug.yml \
		--container-daemon-socket - \
		--container-architecture $(ACT_ARCH) \
		-P ubuntu-latest=$(ACT_IMAGE)
	@echo ""
	@echo "✅ Debug workflow complete!"

ci-clean:  ## Clean up act cache and containers
	@echo "🧹 Cleaning up act cache and containers..."
	@-docker ps -a | grep "act-" | awk '{print $$1}' | xargs docker rm -f 2>/dev/null || true
	@-docker images | grep "act-" | awk '{print $$3}' | xargs docker rmi -f 2>/dev/null || true
	@echo "✅ Cleanup complete!"

# Documentation
###############
DOCS_PORT ?= 8000

docs-install: setup  ## Install documentation dependencies
	@echo "Installing documentation dependencies..."
	uv sync --group dev
	@echo "Documentation dependencies installed"

docs-build: docs-install  ## Build documentation site
	@echo "Building documentation..."
	uv run mkdocs build --strict
	@echo "Documentation built successfully"
	@echo "📄 Site location: site/"
	@echo "🌐 Open site/index.html in your browser to view"

docs-serve: docs-install  ## Serve documentation locally with live reload
	@echo "Starting documentation server with live reload..."
	@echo "📍 Documentation will be available at:"
	@echo "   - Local: http://localhost:$(DOCS_PORT)"
	@echo "🔄 Changes will auto-reload (press Ctrl+C to stop)"
	@echo ""
	@echo "💡 To use a different port: make docs-serve DOCS_PORT=9999"
	uv run mkdocs serve --dev-addr 0.0.0.0:$(DOCS_PORT)

docs-check: docs-build  ## Check documentation build and links
	@echo "Checking documentation..."
	@echo "📊 Site size: $$(du -sh site/ | cut -f1)"
	@echo "📄 Pages built: $$(find site/ -name "*.html" | wc -l)"
	@echo "🔗 Checking for common issues..."
	@if grep -r "404" site/ >/dev/null 2>&1; then \
		echo "⚠️  Found potential 404 errors"; \
	else \
		echo "✅ No obvious 404 errors found"; \
	fi
	@if find site/ -name "*.html" -size 0 | grep -q .; then \
		echo "⚠️  Found empty HTML files"; \
		find site/ -name "*.html" -size 0; \
	else \
		echo "✅ No empty HTML files found"; \
	fi
	@echo "Documentation check complete"

docs-clean:  ## Clean documentation build files
	@echo "Cleaning documentation build files..."
	rm -rf site/
	rm -rf .cache/
	@echo "Documentation cleaned"

# Project Management
##################
clean-example:  # Remove example code (use this to start your own project)
	rm -rf $(MODULE_NAME)/example.py tests/test_example.py
	touch $(MODULE_NAME)/__init__.py tests/__init__.py

init: setup  # Initialize a new project
	uv run python scripts/init_project.py

# Container Engine Support
########################
# Auto-detect container engine (podman or docker)
CONTAINER_ENGINE ?= $(shell command -v podman >/dev/null 2>&1 && echo podman || echo docker)

# Podman-specific adjustments
ifeq ($(CONTAINER_ENGINE),podman)
    # Use podman-compose for compose functionality
    COMPOSE_CMD = podman-compose
    # Use host UID/GID for rootless containers
    CONTAINER_USER_OPTS = --userns=keep-id
    # Podman machine status check
    PODMAN_MACHINE_RUNNING = $(shell podman machine list --format json 2>/dev/null | grep '"Running": true' >/dev/null && echo yes || echo no)
else
    # Docker: use native compose
    COMPOSE_CMD = $(CONTAINER_ENGINE) compose
    # Docker: use current user's UID/GID to avoid permission issues
    CONTAINER_USER_OPTS = --user $(shell id -u):$(shell id -g)
endif

# Docker/Podman Images
#####################
IMAGE_NAME = container-registry.io/python-collab-template
IMAGE_TAG = latest

dev-env: ensure-container-ready refresh-containers
	@echo "Spinning up a dev environment using $(CONTAINER_ENGINE)..."
	@$(COMPOSE_CMD) -f docker/docker-compose.yml down
	@$(COMPOSE_CMD) -f docker/docker-compose.yml up -d dev
	@$(CONTAINER_ENGINE) exec -ti composed_dev /bin/bash

refresh-containers: ensure-container-ready
	@echo "Rebuilding containers using $(CONTAINER_ENGINE)..."
	@$(COMPOSE_CMD) -f docker/docker-compose.yml build

rebuild-images:
	@echo "Rebuilding images with the --no-cache flag using $(CONTAINER_ENGINE)..."
	@$(COMPOSE_CMD) -f docker/docker-compose.yml build --no-cache

build-image:
	@echo Building dev image using $(CONTAINER_ENGINE) and tagging as ${IMAGE_NAME}:${IMAGE_TAG}
	@$(COMPOSE_CMD) -f docker/docker-compose.yml down
	@$(COMPOSE_CMD) -f docker/docker-compose.yml up -d dev
	@$(CONTAINER_ENGINE) tag dev ${IMAGE_NAME}:${IMAGE_TAG}

push-image: build-image
	@echo Pushing image to container registry using $(CONTAINER_ENGINE)
	@$(CONTAINER_ENGINE) push ${IMAGE_NAME}:${IMAGE_TAG}

# Container Engine Info
######################
ensure-container-ready:  # Ensure container engine is ready
ifeq ($(CONTAINER_ENGINE),podman)
	@echo "Checking Podman machine status..."
	@if [ "$(PODMAN_MACHINE_RUNNING)" = "no" ]; then \
		echo "Podman machine is not running. Starting it..."; \
		podman machine start; \
		echo "Waiting for Podman machine to be ready..."; \
		sleep 3; \
	fi
	@if ! command -v podman-compose >/dev/null 2>&1; then \
		echo "Error: podman-compose not found. Install with: brew install podman-compose"; \
		exit 1; \
	fi
else
	@echo "Using Docker engine..."
endif

container-info:  # Display detected container engine and configuration
	@echo "Container Engine: $(CONTAINER_ENGINE)"
	@echo "Compose Command: $(COMPOSE_CMD)"
	@echo "User Options: $(CONTAINER_USER_OPTS)"
ifeq ($(CONTAINER_ENGINE),podman)
	@echo "Podman Machine Running: $(PODMAN_MACHINE_RUNNING)"
	@echo "podman-compose Available: $(shell command -v podman-compose >/dev/null 2>&1 && echo yes || echo no)"
endif
	@echo ""
	@echo "To override, use: CONTAINER_ENGINE=podman make dev-env"
