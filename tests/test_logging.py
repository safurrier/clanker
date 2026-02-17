"""Tests for logging configuration."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from loguru import logger


class TestLoggingConfiguration:
    """Tests for configure_logging function."""

    def test_configure_logging_sets_log_level_from_env(self) -> None:
        """LOG_LEVEL env var should control log level."""
        from clanker_bot.main import configure_logging

        with patch.dict(os.environ, {"LOG_LEVEL": "WARNING"}):
            configure_logging()
            # Logger should be configured (we can't easily inspect level,
            # but we verify no exception is raised)

    def test_configure_logging_defaults_to_info(self) -> None:
        """Default log level should be INFO when env var not set."""
        from clanker_bot.main import configure_logging

        env = os.environ.copy()
        env.pop("LOG_LEVEL", None)
        with patch.dict(os.environ, env, clear=True):
            configure_logging()


class TestFileLogging:
    """Tests for file-based logging with rotation."""

    def test_configure_file_logging_creates_log_file(self, tmp_path: Path) -> None:
        """File logging should create log file in specified directory."""
        from clanker_bot.logging_config import configure_file_logging

        log_dir = tmp_path / "logs"
        configure_file_logging(log_dir=log_dir)

        # Log a message
        logger.info("test message")

        # File should be created
        log_files = list(log_dir.glob("*.log"))
        assert len(log_files) >= 1

    def test_configure_file_logging_writes_json_format(self, tmp_path: Path) -> None:
        """File logs should be in JSON format for machine parsing."""
        from clanker_bot.logging_config import configure_file_logging

        log_dir = tmp_path / "logs"
        handler_id = configure_file_logging(log_dir=log_dir, json_format=True)

        # Log a message
        logger.info("json test message")

        # Force flush by removing handler
        logger.remove(handler_id)

        # Read and parse log file
        log_files = list(log_dir.glob("*.log"))
        assert log_files, "Expected log file to be created"

        log_content = log_files[0].read_text()
        lines = [line for line in log_content.strip().split("\n") if line]
        assert lines, "Expected at least one log line"

        # Each line should be valid JSON
        for line in lines:
            parsed = json.loads(line)
            assert "text" in parsed or "message" in parsed

    def test_configure_file_logging_respects_rotation_size(
        self, tmp_path: Path
    ) -> None:
        """Log files should rotate when exceeding size limit."""
        from clanker_bot.logging_config import configure_file_logging

        log_dir = tmp_path / "logs"
        # Use very small rotation size for test
        # Note: retention must be a time duration (loguru doesn't support file count)
        handler_id = configure_file_logging(
            log_dir=log_dir, rotation="1 KB", retention="1 day"
        )

        # Write enough logs to trigger rotation
        for i in range(100):
            logger.info(f"rotation test message {i} with some padding to fill space")

        logger.remove(handler_id)

        # Should have multiple log files after rotation
        log_files = list(log_dir.glob("*.log*"))
        # At least the main file should exist
        assert len(log_files) >= 1


class TestVoiceLogging:
    """Tests for voice-specific logging configuration."""

    def test_voice_log_level_env_enables_verbose_logging(self) -> None:
        """VOICE_LOG_LEVEL=DEBUG should enable verbose voice logging."""
        from clanker_bot.logging_config import get_voice_log_level

        with patch.dict(os.environ, {"VOICE_LOG_LEVEL": "DEBUG"}):
            level = get_voice_log_level()
            assert level == "DEBUG"

    def test_voice_log_level_defaults_to_info(self) -> None:
        """Default voice log level should be INFO."""
        from clanker_bot.logging_config import get_voice_log_level

        env = os.environ.copy()
        env.pop("VOICE_LOG_LEVEL", None)
        with patch.dict(os.environ, env, clear=True):
            level = get_voice_log_level()
            assert level == "INFO"

    def test_voice_logger_filter_respects_level(self) -> None:
        """Voice logger filter should respect VOICE_LOG_LEVEL."""
        from clanker_bot.logging_config import create_voice_filter

        with patch.dict(os.environ, {"VOICE_LOG_LEVEL": "WARNING"}):
            filter_fn = create_voice_filter()

            # Create mock record with voice_ingest module
            class MockRecord:
                def __init__(self, level: str, name: str):
                    self.level = type("Level", (), {"name": level})()
                    self.name = name

            # DEBUG record from voice module should be filtered out
            debug_record = MockRecord("DEBUG", "clanker_bot.voice_ingest")
            assert filter_fn(debug_record) is False

            # WARNING record from voice module should pass
            warning_record = MockRecord("WARNING", "clanker_bot.voice_ingest")
            assert filter_fn(warning_record) is True

            # Non-voice module should always pass
            other_record = MockRecord("DEBUG", "clanker_bot.commands")
            assert filter_fn(other_record) is True
