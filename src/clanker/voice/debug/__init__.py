"""Voice pipeline debug capture module.

Enable debug capture via environment variables:
    VOICE_DEBUG=1          Enable capture (default: disabled)
    VOICE_DEBUG_DIR=./out  Output directory (default: ./voice_debug)

Usage:
    from clanker.voice.debug import DebugCapture, DebugConfig

    capture = DebugCapture.from_env()
    if capture.enabled:
        capture.start_session(DebugConfig(...))
        # ... capture stages ...
        capture.end_session()
"""

from .capture import DebugCapture
from .models import (
    CapturedUtterance,
    DebugConfig,
    DebugSession,
    UserCapture,
)

__all__ = [
    "CapturedUtterance",
    "DebugCapture",
    "DebugConfig",
    "DebugSession",
    "UserCapture",
]
