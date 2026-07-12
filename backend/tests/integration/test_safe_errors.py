"""Integration tests: safe error responses (no raw exception leaks)."""

import importlib

import pytest
from fastapi.testclient import TestClient


async def _noop_start_mcp_mesh() -> int:
    return 0


async def _noop_stop_mcp_mesh() -> None:
    return None


@pytest.fixture
def safe_client(tmp_path, monkeypatch):
    """Test client without auth — uses the global exception handler."""
    db_path = str(tmp_path / "api_test.db")
    monkeypatch.setenv("SQLITE_PATH", db_path)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("VECTOR_DIR", str(tmp_path / "vectors"))
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MCP_EXTERNAL_ENABLED", "false")
    monkeypatch.setenv("AUTH_TOKEN", "")

    import app.config
    app.config.reset_settings()

    # Modules that capture ``settings`` at import time must be refreshed after
    # the isolated environment is installed.
    import app.core.runtime.runtime_config
    import app.store.database
    importlib.reload(app.store.database)
    importlib.reload(app.core.runtime.runtime_config)
    from app.core.runtime.runtime_container import runtime
    runtime.reset()
    app.core.runtime.runtime_config.invalidate_runtime_config_cache()

    monkeypatch.setattr(
        "app.core.harness.mcp_lifecycle.start_mcp_mesh",
        _noop_start_mcp_mesh,
    )
    monkeypatch.setattr(
        "app.core.harness.mcp_lifecycle.stop_mcp_mesh",
        _noop_stop_mcp_mesh,
    )

    import app.api.system
    import app.main
    from app.core.rate_limit import reset_rate_limits
    from app.core.startup_health import enrich_with_mcp_status, run_startup_checks

    importlib.reload(app.api.system)
    importlib.reload(app.main)
    reset_rate_limits()

    app = app.main.app
    app.state.startup_health = enrich_with_mcp_status(run_startup_checks())

    yield TestClient(app)


def test_unhandled_exception_returns_safe_500(safe_client: TestClient, monkeypatch):
    """When a route raises unhandled Exception, client sees generic 500."""

    # Force the inbox endpoint to raise an unexpected exception.
    def _evil(*_args, **_kwargs):
        raise RuntimeError("secret file /etc/shadow not readable")

    monkeypatch.setattr(
        "app.api.inbox.mark_inbox_email_status",
        _evil,
    )

    r = safe_client.patch("/api/inbox/fake-id/status", json={"status": "read"})
    assert r.status_code == 500
    body = r.json()
    assert body["detail"] == "Internal server error"
    assert "secret" not in str(body)
    assert "/etc" not in str(body)
    assert "request_id" in body


def test_global_handler_includes_request_id(safe_client: TestClient, monkeypatch):
    def _evil(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.api.inbox.mark_inbox_email_status", _evil)

    r = safe_client.patch(
        "/api/inbox/fake-id/status",
        json={"status": "read"},
        headers={"Origin": "http://localhost:5173"},
    )
    body = r.json()
    rid = body.get("request_id")
    assert rid is not None and rid != "", f"Expected non-empty request_id, got: {rid!r}"
    assert r.headers["x-request-id"] == rid
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_settings_capability_policy_does_not_leak_os_error(safe_client: TestClient, monkeypatch):
    """Verifies the raw OS error text is not in the response body."""
    # Monkeypatch the file read at the source: path.read_text.
    from pathlib import Path

    original_read = Path.read_text

    def _failing_read(self, *args, **kwargs):
        if "capability_policy.json" in str(self):
            raise OSError("access denied /secret/path")
        return original_read(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _failing_read)

    r = safe_client.get("/api/settings/capability-policy")
    assert r.status_code == 500
    body = r.json()
    assert body["detail"] == "Failed to read capability policy"
    # Raw path must not leak.
    assert "/secret" not in str(body)
    assert "denied" not in str(body)


def test_llm_test_endpoint_safe_error(safe_client: TestClient, monkeypatch):
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

    r = safe_client.post("/api/settings/llm/test", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["error"] == "Connection test failed — check provider URL and credentials"
    assert sensitive_marker not in str(body)
