"""API tests for memory index repair observability endpoints."""

from datetime import UTC, datetime


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


def test_list_memory_index_repairs(client):
    from app.store.database import db

    _insert_repair(db)

    resp = client.get("/api/telemetry/memory-index-repairs?status=failed_permanent")
    assert resp.status_code == 200
    data = resp.json()
    assert data["failed_permanent"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["aggregate_id"] == "mem-1"


def test_retry_memory_index_repair(client):
    from app.store.database import db

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
