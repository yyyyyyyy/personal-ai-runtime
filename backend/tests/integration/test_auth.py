"""Integration tests: optional Bearer auth and WebSocket token."""

import pytest
from starlette.testclient import TestClient


def test_api_open_when_auth_disabled(client: TestClient):
    r = client.get("/api/goals/")
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
    r = authed_client.get("/api/goals/")
    assert r.status_code == 401

    r2 = authed_client.get(
        "/api/goals/",
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
