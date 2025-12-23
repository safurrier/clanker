"""Command handler entrypoints."""

from .admin import (
    handle_admin_active_meetings,
    handle_admin_allow_new_meetings,
    handle_admin_stop_new_meetings,
)
from .chat import handle_chat, handle_shitpost, handle_speak
from .types import BotDependencies
from .voice import handle_join, handle_leave

__all__ = [
    "BotDependencies",
    "handle_admin_active_meetings",
    "handle_admin_allow_new_meetings",
    "handle_admin_stop_new_meetings",
    "handle_chat",
    "handle_join",
    "handle_leave",
    "handle_shitpost",
    "handle_speak",
]
