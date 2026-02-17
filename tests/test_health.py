"""Tests for health endpoint."""

import time

import pytest
from aiohttp.test_utils import TestClient, TestServer

from clanker_bot.health import HealthState, create_health_app


@pytest.mark.asyncio()
async def test_status_endpoint() -> None:
    state = HealthState(
        started_at=time.time() - 5,
        active_voice_provider=lambda: False,
        version="0.1.0",
    )
    app = create_health_app(state)
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()
    try:
        resp = await client.get("/status")
        assert resp.status == 200
        payload = await resp.json()
        assert payload["version"] == "0.1.0"
        assert payload["uptime"] >= 0
    finally:
        await client.close()
