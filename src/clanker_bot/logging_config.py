"""Logging configuration for Clanker bot.

Provides:
- File-based logging with rotation for persistent debugging
- JSON format for machine parsing (Datadog/CloudWatch friendly)
- Voice-specific log level control via VOICE_LOG_LEVEL env var
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from loguru import logger

# Log level priority (higher number = more severe)
LEVEL_PRIORITY = {
    "TRACE": 5,
    "DEBUG": 10,
    "INFO": 20,
    "SUCCESS": 25,
    "WARNING": 30,
    "ERROR": 40,
    "CRITICAL": 50,
}

# Modules that use voice-specific log level
VOICE_MODULES = frozenset(
    {
        "clanker_bot.voice_ingest",
        "clanker.voice.worker",
        "clanker.voice.vad",
        "clanker.voice.chunker",
        "clanker.voice.debug",
    }
)


def get_voice_log_level() -> str:
    """Get the voice-specific log level from environment.

    Returns:
        Log level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        Defaults to INFO if not set.
    """
    return os.getenv("VOICE_LOG_LEVEL", "INFO").upper()


def create_voice_filter() -> Callable[[Any], bool]:
    """Create a filter function for voice-specific logging.

    Returns a filter that:
    - Applies VOICE_LOG_LEVEL to voice modules
    - Allows all logs from non-voice modules

    Returns:
        Filter function for use with loguru.
    """
    voice_level = get_voice_log_level()
    voice_priority = LEVEL_PRIORITY.get(voice_level, 20)

    def filter_fn(record: Any) -> bool:
        module_name = record.name if hasattr(record, "name") else ""

        # Check if this is a voice module
        is_voice_module = any(module_name.startswith(vm) for vm in VOICE_MODULES)

        if not is_voice_module:
            return True

        # Apply voice-specific level filter
        record_level = record.level.name if hasattr(record.level, "name") else "INFO"
        record_priority = LEVEL_PRIORITY.get(record_level, 20)

        return record_priority >= voice_priority

    return filter_fn


def configure_file_logging(
    log_dir: Path | str = Path("logs"),
    rotation: str = "50 MB",
    retention: str = "7 days",
    json_format: bool = False,
) -> int:
    """Configure file-based logging with rotation.

    Args:
        log_dir: Directory for log files. Created if doesn't exist.
        rotation: When to rotate (e.g., "50 MB", "1 day", "12:00").
        retention: How long to keep old logs (e.g., "7 days", "3 files").
        json_format: If True, write logs as JSON lines for machine parsing.

    Returns:
        Handler ID that can be used to remove the handler later.
    """
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / "clanker.log"

    if json_format:
        # JSON format for machine parsing
        handler_id = logger.add(
            log_file,
            rotation=rotation,
            retention=retention,
            serialize=True,  # Loguru's built-in JSON serialization
            level="DEBUG",
            enqueue=True,  # Thread-safe async logging
        )
    else:
        # Human-readable format
        handler_id = logger.add(
            log_file,
            rotation=rotation,
            retention=retention,
            format=(
                "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
                "{level: <8} | "
                "{name}:{function}:{line} - "
                "{message}"
            ),
            level="DEBUG",
            enqueue=True,
        )

    return handler_id


def configure_stderr_logging(log_level: str = "INFO") -> int:
    """Configure colored stderr logging for development.

    Args:
        log_level: Minimum log level to display.

    Returns:
        Handler ID that can be used to remove the handler later.
    """
    return logger.add(
        sys.stderr,
        level=log_level.upper(),
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
        colorize=True,
        filter=create_voice_filter(),
    )


def configure_all_logging(
    log_level: str = "INFO",
    log_dir: Path | str | None = None,
    json_format: bool = True,
) -> None:
    """Configure all logging (stderr + optional file logging).

    This is the main entry point for logging configuration.

    Args:
        log_level: Base log level for stderr output.
        log_dir: If provided, enable file logging to this directory.
        json_format: Use JSON format for file logs.
    """
    # Remove default handler
    logger.remove()

    # Add stderr handler with color
    configure_stderr_logging(log_level)

    # Add file handler if directory specified
    if log_dir:
        configure_file_logging(log_dir=log_dir, json_format=json_format)
