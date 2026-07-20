"""Integration tests: safe error responses (no raw exception leaks)."""

from fastapi.testclient import TestClient


def test_unhandled_exception_returns_safe_500(client: TestClient, monkeypatch):
    """When a route raises unhandled Exception, client sees generic 500."""

    def _evil(*_args, **_kwargs):
        raise RuntimeError("secret file /etc/shadow not readable")

    monkeypatch.setattr(
        "app.api.inbox.mark_inbox_email_status",
        _evil,
    )

    r = client.patch("/api/inbox/fake-id/status", json={"status": "read"})
    assert r.status_code == 500
    body = r.json()
    assert body["detail"] == "Internal server error"
    assert "secret" not in str(body)
    assert "/etc" not in str(body)
    assert "request_id" in body


def test_global_handler_includes_request_id(client: TestClient, monkeypatch):
    def _evil(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.api.inbox.mark_inbox_email_status", _evil)

    r = client.patch(
        "/api/inbox/fake-id/status",
        json={"status": "read"},
        headers={"Origin": "http://localhost:5173"},
    )
    body = r.json()
    rid = body.get("request_id")
    assert rid is not None and rid != "", f"Expected non-empty request_id, got: {rid!r}"
    assert r.headers["x-request-id"] == rid
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_settings_capability_policy_does_not_leak_os_error(client: TestClient, monkeypatch):
    """Verifies the raw OS error text is not in the response body."""
    from pathlib import Path

    original_read = Path.read_text

    def _failing_read(self, *args, **kwargs):
        if "capability_policy.json" in str(self):
            raise OSError("access denied /secret/path")
        return original_read(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _failing_read)

    r = client.get("/api/settings/capability-policy")
    assert r.status_code == 500
    body = r.json()
    assert body["detail"] == "Failed to read capability policy"
    assert "/secret" not in str(body)
    assert "denied" not in str(body)


def test_llm_test_endpoint_safe_error(client: TestClient, monkeypatch):
    """LLM test failures return generic message, not raw exception text."""
    sensitive_marker = "SECRET_MARKER_/private/provider"

    class _FailingCompletions:
        async def create(self, **_kwargs):
            raise RuntimeError(sensitive_marker)

    class _FailingClient:
        def __init__(self, **_kwargs):
            self.chat = type("Chat", (), {"completions": _FailingCompletions()})()

    monkeypatch.setattr("app.api.settings_api.AsyncOpenAI", _FailingClient)
    monkeypatch.setattr(
        "app.api.settings_api.runtime_config.get_llm_config",
        lambda masked=False: {"default_provider": "test"},
    )
    monkeypatch.setattr(
        "app.api.settings_api.runtime_config.get_provider_credentials",
        lambda _provider_id: [{
            "id": "test",
            "type": "openai_compatible",
            "api_key": "fake-key",
            "base_url": "http://127.0.0.1:1/v1",
            "model": "fake",
        }],
    )

    r = client.post("/api/settings/llm/test", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["error"] == "Connection test failed — check provider URL and credentials"
    assert sensitive_marker not in str(body)
