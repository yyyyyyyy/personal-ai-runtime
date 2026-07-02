"""Tests for RequestIDMiddleware."""

import os

os.environ.setdefault("LLM_API_KEY", "test-key")

from starlette.testclient import TestClient


def test_response_has_request_id_header():
    """Every response must carry an X-Request-ID header."""
    from app.main import app

    with TestClient(app) as client:
        resp = client.get("/")
    assert resp.status_code == 200
    assert "x-request-id" in {k.lower() for k in resp.headers.keys()}


def test_inbound_request_id_is_preserved():
    """An upstream-provided X-Request-ID is echoed back unchanged."""
    from app.main import app

    with TestClient(app) as client:
        resp = client.get("/", headers={"X-Request-ID": "upstream-123"})
    assert resp.headers.get("x-request-id") == "upstream-123"


def test_request_id_contextvar_populated():
    """The request_id contextvar is set during request handling."""
    from app.main import app, get_request_id

    captured: list[str] = []

    @app.get("/__test_rid__")
    def _capture():
        captured.append(get_request_id())
        return {"ok": True}

    with TestClient(app) as client:
        resp = client.get("/__test_rid__", headers={"X-Request-ID": "ctx-test"})
    assert resp.status_code == 200
    assert captured == ["ctx-test"]
