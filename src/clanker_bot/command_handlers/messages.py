"""Response message constants for command handlers."""

from __future__ import annotations

from enum import Enum


class ResponseMessage(str, Enum):
    """Standard response messages for Discord commands."""

    # Authorization
    NOT_AUTHORIZED = "Not authorized."

    # Voice channel
    JOIN_VOICE_FIRST = "Join a voice channel first."
    JOINED_VOICE = "Joined voice channel."
    LEFT_VOICE = "Left voice channel."
    UNABLE_TO_RESOLVE_VOICE = "Unable to resolve voice channel."
    NEW_MEETINGS_DISABLED = "New meetings are disabled."

    # Threading
    REPLY_IN_THREAD = "Reply posted in thread."

    # Transcription status
    TRANSCRIPTION_UNAVAILABLE_NO_STT = "Transcription unavailable; STT not configured."
    TRANSCRIPTION_UNAVAILABLE_BUILD = "Transcription unavailable in this host build."
    TRANSCRIPTION_ENABLED = "Transcription enabled."
    TRANSCRIPTION_SETUP_ERROR = "Transcription unavailable due to setup error."

    # Admin
    NEW_MEETINGS_ENABLED = "New meetings enabled."
    ACTIVE_VOICE_NONE = "none"

    # Error messages
    REQUEST_BLOCKED = "❌ Request blocked"
    SERVICE_UNAVAILABLE = "⏳ Service temporarily unavailable. Please try again."
    CONFIG_ERROR = "❌ Configuration error. Please contact an admin."
    UNEXPECTED_ERROR = "❌ An unexpected error occurred."

    # Invalid input
    INVALID_CATEGORY = "❌ Invalid category"
