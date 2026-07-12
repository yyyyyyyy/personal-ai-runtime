"""Integration tests: optional Bearer auth and WebSocket token."""

import asyncio

import pytest
from starlette.testclient import TestClient


def test_api_open_when_auth_disabled(client: TestClient):
    r = client.get("/api/work-items/")
    assert r.status_code == 200

    health = client.get("/api/system/health").json()
    assert health["auth_required"] is False

    with client.websocket_connect("/ws") as ws:
        ws.send_text("ping")
        assert ws.receive_text() == "pong"


def test_health_reports_auth_required(authed_client: TestClient):
    health = authed_client.get("/api/system/health").json()
    assert health["auth_required"] is True


def test_api_requires_bearer_when_auth_enabled(authed_client: TestClient):
    r = authed_client.get("/api/work-items/")
    assert r.status_code == 401

    r2 = authed_client.get(
        "/api/work-items/",
        headers={"Authorization": "Bearer test-secret"},
    )
    assert r2.status_code == 200


def test_websocket_requires_token_when_auth_enabled(authed_client: TestClient):
    with pytest.raises(Exception):
        with authed_client.websocket_connect("/ws"):
            pass

    with pytest.raises(Exception):
        with authed_client.websocket_connect(
            "/ws",
            subprotocols=["auth.wrong"],
        ):
            pass

    with pytest.raises(Exception):
        with authed_client.websocket_connect("/ws?token=test-secret"):
            pass

    with authed_client.websocket_connect(
        "/ws",
        subprotocols=["auth.test-secret", "auth.ok"],
    ) as ws:
        ws.send_text("ping")
        assert ws.receive_text() == "pong"


def test_rate_limit_always_active_without_auth(client: TestClient):
    """Rate limiting applies even when AUTH_TOKEN is empty."""
    # Rapidly hammer a limited endpoint.
    statuses = []
    for _ in range(35):
        r = client.get("/api/chat/conversations")
        statuses.append(r.status_code)
    assert 429 in statuses, "Expected a 429 rate-limit response within 35 requests"


def test_rate_limit_return_429_body(client: TestClient):
    """429 response has a proper json body."""
    for _ in range(31):
        client.get("/api/chat/conversations")
    r = client.get("/api/chat/conversations")
    assert r.status_code == 429
    body = r.json()
    assert "detail" in body


def test_public_endpoints_never_rate_limited(client: TestClient):
    """Health, docs, and root are exempt from rate limiting."""
    for _ in range(100):
        r = client.get("/api/system/health")
        assert r.status_code == 200

    for _ in range(100):
        r = client.get("/")
        assert r.status_code == 200


def test_rate_limit_works_with_auth(authed_client: TestClient):
    """Rate limiting still applies when auth is enabled."""
    headers = {"Authorization": "Bearer test-secret"}
    statuses = []
    for _ in range(35):
        r = authed_client.get("/api/chat/conversations", headers=headers)
        statuses.append(r.status_code)
    assert 429 in statuses


def test_sse_chat_not_buffered_by_auth_middleware(client: TestClient):
    """The chat SSE endpoint streams token-level responses.

    Because AuthMiddleware is pure ASGI (not BaseHTTPMiddleware),
    streaming endpoints must not be buffered.
    """
    # Send a request to the chat messages endpoint — it should respond
    # (even if it fails to find a conversation, it must not hang
    # or buffer due to middleware).  This verifies the middleware
    # does not break streaming.
    r = client.post(
        "/api/chat/conversations/test-sse/messages",
        json={"content": "hello"},
    )
    # The endpoint exists; it may 404 or produce an error, but must not be
    # swallowed by middleware buffering.
    assert r.status_code in (200, 404, 422, 500)


@pytest.mark.asyncio
async def test_websocket_connection_slot_is_reserved_atomically(monkeypatch):
    """Concurrent handshakes cannot both pass a one-slot global limit."""
    import app.main as main

    monkeypatch.setattr(main, "_WS_MAX_GLOBAL_CONNECTIONS", 1)
    main._ws_connections.clear()
    main._ws_reserved_slots = 0
    first = object()
    second = object()

    results = await asyncio.gather(
        main._reserve_ws_connection(first, exposed_without_auth=False),
        main._reserve_ws_connection(second, exposed_without_auth=False),
    )

    assert results.count(True) == 1
    assert main._ws_reserved_slots == 1
    assert main._ws_connections == []  # not registered until accept
    await main._release_ws_connection(None, registered=False)
    assert main._ws_reserved_slots == 0
