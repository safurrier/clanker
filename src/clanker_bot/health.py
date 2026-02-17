"""Health endpoint utilities."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from aiohttp import web


@dataclass
class HealthState:
    """State for the health endpoint."""

    started_at: float
    active_voice_provider: Callable[[], bool]
    version: str


def create_health_app(state: HealthState) -> web.Application:
    """Create an aiohttp app exposing /status."""
    app = web.Application()

    async def status(_request: web.Request) -> web.Response:
        uptime = time.time() - state.started_at
        payload = {
            "uptime": uptime,
            "active_voice": state.active_voice_provider(),
            "version": state.version,
        }
        return web.json_response(payload)

    app.router.add_get("/status", status)
    return app
