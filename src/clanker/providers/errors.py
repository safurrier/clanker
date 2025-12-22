"""Provider errors and classification."""

from __future__ import annotations


class ProviderError(RuntimeError):
    """Base error for provider failures."""


class TransientProviderError(ProviderError):
    """Retryable error from a provider."""


class PermanentProviderError(ProviderError):
    """Non-retryable error from a provider."""
