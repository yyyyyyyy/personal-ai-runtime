"""API tests for memory index repair observability endpoints."""

import os
from datetime import UTC, datetime

os.environ.setdefault("LLM_API_KEY", "test-key")

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = str(tmp_path / "repairs_api_client.db")
    monkeypatch.setenv("SQLITE_PATH", db_path)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("VECTOR_DIR", str(tmp_path / "vectors"))
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MCP_EXTERNAL_ENABLED", "false")
    monkeypatch.setenv("AUTH_TOKEN", "")

    async def _noop_start():
        return 0

    async def _noop_stop():
        return None

    monkeypatch.setattr("app.core.harness.mcp_lifecycle.start_mcp_mesh", _noop_start)
    monkeypatch.setattr("app.core.harness.mcp_lifecycle.stop_mcp_mesh", _noop_stop)

    import app.api.system
    import app.config
    import app.main

    app.config.reset_settings()
    importlib.reload(app.api.system)
    importlib.reload(app.main)

    yield TestClient(app.main.app)


def _insert_repair(db, *, status="failed_permanent", aggregate_id="mem-1"):
    now = datetime.now(UTC).isoformat()
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO memory_index_repairs "
            "(aggregate_id, event_type, event_seq, error, retry_count, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (aggregate_id, "MemoryUpdated", 3, "chroma down", 5, status, now),
        )
        row_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    return row_id


def test_list_memory_index_repairs(client, tmp_path, monkeypatch):
    from app.store.database import Database

    db = Database(db_path=str(tmp_path / "repairs_api.db"))
    monkeypatch.setattr("app.core.telemetry.telemetry.db", db)
    _insert_repair(db)

    resp = client.get("/api/telemetry/memory-index-repairs?status=failed_permanent")
    assert resp.status_code == 200
    data = resp.json()
    assert data["failed_permanent"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["aggregate_id"] == "mem-1"


def test_retry_memory_index_repair(client, tmp_path, monkeypatch):
    from app.store.database import Database

    db = Database(db_path=str(tmp_path / "repairs_retry.db"))
    monkeypatch.setattr("app.core.telemetry.telemetry.db", db)
    repair_id = _insert_repair(db)

    resp = client.post(f"/api/telemetry/memory-index-repairs/{repair_id}/retry")
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"

    with db.get_db() as conn:
        row = conn.execute(
            "SELECT status, retry_count FROM memory_index_repairs WHERE id = ?",
            (repair_id,),
        ).fetchone()
    assert row["status"] == "pending"
    assert row["retry_count"] == 0


def test_retry_memory_index_repair_not_found(client):
    resp = client.post("/api/telemetry/memory-index-repairs/99999/retry")
    assert resp.status_code == 404
