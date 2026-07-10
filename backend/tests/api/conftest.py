"""Conftest for tests/api — async HTTP client fixture."""

import httpx
import pytest


@pytest.fixture
async def http_client(app) -> httpx.AsyncClient:
    """Async HTTP client wired directly to the FastAPI ASGI app."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
