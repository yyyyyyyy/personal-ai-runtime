"""Tests for startup health checks."""

from app.core.startup_health import run_startup_checks, sanitize_startup_for_public


def test_startup_checks_returns_structure(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    snapshot = run_startup_checks()
    assert snapshot["status"] in ("ok", "degraded")
    assert "checks" in snapshot
    assert "storage" in snapshot["checks"]
    assert "llm" in snapshot["checks"]
    assert snapshot["checks"]["llm"]["configured"] is True


def test_sanitize_startup_strips_sensitive_fields():
    snapshot = {
        "status": "degraded",
        "warnings": ["data_dir='/secret/path' looks like a ghost path"],
        "checks": {
            "storage": {
                "data_dir": "/secret/data",
                "sqlite_path": "/secret/db.sqlite",
                "vector_dir": "/secret/vectors",
                "data_dir_exists": True,
                "data_dir_writable": True,
                "sqlite_exists": False,
            },
            "llm": {
                "configured": True,
                "model": "deepseek-chat",
                "base_url": "https://api.example.com/v1",
            },
            "auth": {"enabled": True, "host": "127.0.0.1"},
            "email": {"configured": False},
            "mcp": {
                "servers": [
                    {"name": "email", "status": "connected", "startup_connect": True},
                    {"name": "calendar", "status": "disconnected", "startup_connect": True},
                ]
            },
        },
    }
    public = sanitize_startup_for_public(snapshot)
    assert public is not None
    assert public["warning_count"] == 1
    assert "warnings" not in public
    storage = public["checks"]["storage"]
    assert "data_dir" not in storage
    assert storage["sqlite_exists"] is False
    assert "base_url" not in public["checks"]["llm"]
    assert "host" not in public["checks"]["auth"]
    assert public["checks"]["mcp"] == {"total": 2, "connected": 1, "failed": 1}


def test_enrich_with_mcp_status_marks_disconnected_as_degraded(monkeypatch):
    snapshot = {"status": "ok", "checks": {}, "warnings": []}

    class FakeMesh:
        @staticmethod
        def get_server_status():
            return {
                "enabled": True,
                "servers": [
                    {"name": "email", "status": "connected", "startup_connect": True},
                    {"name": "calendar", "status": "disconnected", "startup_connect": True},
                ],
                "total_tools": 1,
            }

    monkeypatch.setattr(
        "app.core.harness.mcp_mesh.mcp_mesh",
        FakeMesh(),
    )
    from app.core.startup_health import enrich_with_mcp_status

    result = enrich_with_mcp_status(snapshot)
    assert result["status"] == "degraded"
    assert any("calendar" in w for w in result["warnings"])
