"""Rebuild consistency tests for engines migrated to Kernel event writes."""

import os

os.environ.setdefault("LLM_API_KEY", "test-key")

from app.core.agents.memory_engine import MemoryEngine
from app.core.runtime.approval_engine import ApprovalEngine
from app.core.runtime.kernel import Kernel
from app.core.runtime.task_engine import TaskEngine
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
            "app.core.agents.memory_engine.vector_store.add_memory",
            lambda content, metadata, memory_id: f"emb_{memory_id}",
        )
        monkeypatch.setattr("app.core.agents.memory_engine.vector_store.delete_memory", lambda _id: None)

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
        monkeypatch.setattr("app.core.runtime.task_engine.db", db)

        engine = TaskEngine()
        parent = engine.create_task(name="Parent", description="root")
        child = engine.create_task(name="Child", parent_task_id=parent["id"])
        engine.update_task_status(parent["id"], "running")
        engine.update_task_status(child["id"], "running")
        engine.update_task_status(child["id"], "blocked")
        engine.update_task_status(parent["id"], "completed")

        before = snapshot_table(db, "tasks")
        k.rebuild("task")
        after = snapshot_table(db, "tasks")
        assert before == after
        assert any(t["id"] == child["id"] and t["status"] == "blocked" for t in after)

    def test_approval_engine_rebuild(self, tmp_path, monkeypatch):
        k, db = make_kernel(tmp_path)
        monkeypatch.setattr("app.core.runtime.approval_engine.kernel", k)
        monkeypatch.setattr("app.core.runtime.approval_engine.db", db)

        engine = ApprovalEngine()
        req = engine.request_approval("write_file", params={"path": "/tmp/x"}, proposed_by="brain")
        engine.approve(req["id"], resolved_by="user")

        before = snapshot_table(db, "approvals")
        k.rebuild("approval")
        after = snapshot_table(db, "approvals")
        assert before == after
        assert any(a["status"] == "approved" for a in after)
