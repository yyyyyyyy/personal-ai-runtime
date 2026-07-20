"""Integration tests: optional Bearer auth and WebSocket token."""

import asyncio

import pytest
from fastapi.testclient import TestClient


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
    """429 response has a proper json body and Retry-After."""
    for _ in range(31):
        client.get("/api/chat/conversations")
    r = client.get("/api/chat/conversations")
    assert r.status_code == 429
    body = r.json()
    assert "detail" in body
    assert r.headers.get("retry-after") is not None
    assert int(r.headers["retry-after"]) >= 1


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


def test_sse_chat_not_buffered_by_auth_middleware(client: TestClient, fake_brain):
    """AuthMiddleware must expose chat SSE headers and stream body (not buffer)."""
    fake_brain.set_script([
        {"type": "text_delta", "content": "ping"},
        {"type": "done"},
    ])
    conv = client.post("/api/chat/conversations", params={"title": "SSE auth"})
    assert conv.status_code == 200
    conv_id = conv.json()["id"]

    r = client.post(
        f"/api/chat/conversations/{conv_id}/messages",
        json={"content": "hello"},
    )
    assert r.status_code == 200
    assert "text/event-stream" in r.headers.get("content-type", "")
    assert r.headers.get("cache-control") == "no-cache"
    assert "data:" in r.text
    assert "ping" in r.text or "done" in r.text


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
