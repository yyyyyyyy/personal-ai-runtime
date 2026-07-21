"""Rebuild consistency tests for engines migrated to Kernel event writes."""

from app.core.agents.memory_engine import MemoryEngine
from app.core.runtime.kernel import Kernel
from app.core.runtime.task_engine import (
    create_task,
    update_task_status,
)
from app.store.database import Database


def snapshot_table(db: Database, table: str) -> list[dict]:
    with db.get_db() as conn:
        return [dict(r) for r in conn.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()]


def make_kernel(tmp_path):
    db = Database(db_path=str(tmp_path / "rebuild.db"))
    k = Kernel(db=db)
    return k, db


class TestEngineRebuildConsistency:
    def test_memory_engine_rebuild(self, tmp_path, monkeypatch):
        k, db = make_kernel(tmp_path)
        monkeypatch.setattr("app.core.agents.memory_engine.kernel", k)
        monkeypatch.setattr(
            "app.store.vector.vector_store.add_memory",
            lambda content, metadata, memory_id: f"emb_{memory_id}",
        )
        monkeypatch.setattr("app.store.vector.vector_store.delete_memory", lambda _id: None)

        engine = MemoryEngine()
        mid = engine.store_memory("User likes tea", category="preference", actor="user")
        engine.update_memory(mid, "User prefers green tea", category="preference")
        engine.delete_memory(mid)

        before = snapshot_table(db, "memories")
        k.rebuild("memory")
        after = snapshot_table(db, "memories")
        assert before == after

    def test_task_engine_rebuild(self, tmp_path, monkeypatch):
        k, db = make_kernel(tmp_path)
        monkeypatch.setattr("app.core.runtime.task_engine.kernel", k)
        monkeypatch.setattr("app.core.runtime.kernel_instance.kernel", k)

        parent = create_task(name="Parent", description="root")
        child = create_task(name="Child", parent_task_id=parent["id"])
        update_task_status(parent["id"], "running")
        update_task_status(child["id"], "running")
        update_task_status(child["id"], "blocked")
        update_task_status(parent["id"], "completed")

        before = snapshot_table(db, "work_items")
        assert before, "work_items table should have entries"
        k.rebuild("work_item")
        after = snapshot_table(db, "work_items")
        assert before == after
        assert any(t["id"] == child["id"] and t["status"] == "blocked" for t in after)

    def test_approval_engine_rebuild(self, tmp_path, monkeypatch):
        k, db = make_kernel(tmp_path)

        result = k.request_approval(
            action="write_file",
            risk="high",
            ctx={"args": {"path": "/tmp/x"}, "proposed_by": "brain"},
            actor="brain",
        )
        k.grant_approval(result["approval_id"], action="write_file", actor="user", reason="test")

        before = snapshot_table(db, "approvals")
        k.rebuild("approval")
        after = snapshot_table(db, "approvals")
        assert before == after
        assert any(a["status"] == "approved" for a in after)

def test_rebuild_single_work_item_aggregate(isolated_kernel):
    k, _db = isolated_kernel
    k.emit_event(
        "WorkItemCreated", "work_item", "goal_rebuild_test",
        payload={"work_type": "goal", "status": "active", "title": "Rebuild test"},
        actor="verify",
    )
    result = k.rebuild("work_item")
    assert result == 1
    rows = k.query_state("work_items", id="goal_rebuild_test")
    assert rows and rows[0]["title"] == "Rebuild test"


def test_rebuild_all_reports_work_item(isolated_kernel):
    k, _db = isolated_kernel
    k.emit_event(
        "WorkItemCreated", "work_item", "goal_all",
        payload={"title": "All rebuild test"},
        actor="verify",
    )
    result = k.rebuild_all()
    assert "work_item" in result
    assert result["work_item"] >= 1


def test_user_profile_rebuild_preserves_rows_and_created_at(isolated_kernel):
    """user_profile is GOVERNED + owned; rebuild must replay and keep created_at."""
    k, db = isolated_kernel
    k.emit_event(
        "UserProfileUpdated",
        "user_profile",
        "preferences",
        payload={
            "category": "preferences",
            "data_json": '{"theme":"dark"}',
            "confidence": 0.8,
        },
        actor="verify",
    )
    k.emit_event(
        "UserProfileUpdated",
        "user_profile",
        "preferences",
        payload={
            "category": "preferences",
            "data_json": '{"theme":"light"}',
            "confidence": 0.9,
        },
        actor="verify",
    )
    before = snapshot_table(db, "user_profile")
    assert len(before) == 1
    assert before[0]["created_at"]
    created_at = before[0]["created_at"]
    assert before[0]["data_json"] == '{"theme":"light"}'

    assert k.rebuild("user_profile") == 2
    after = snapshot_table(db, "user_profile")
    assert before == after
    assert after[0]["created_at"] == created_at
    assert "user_profile" in k.rebuild_all()
