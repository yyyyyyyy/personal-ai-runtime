"""B1 integration — background task lifecycle auditable via event_log."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("LLM_API_KEY", "test-key")


@pytest.fixture(autouse=True)
def _reset_scheduler():
    import app.core.runtime.agent_bootstrap as agent_bootstrap
    from app.core.runtime.agent_scheduler import reset_scheduler

    reset_scheduler()
    agent_bootstrap._spawned = False
    yield
    reset_scheduler()
    agent_bootstrap._spawned = False


@pytest.fixture
def bg_env(tmp_path, monkeypatch):
    from app.core.runtime.background_worker import BackgroundWorker
    from app.core.runtime.kernel import Kernel
    from app.store.database import Database

    db = Database(db_path=str(tmp_path / "bg_chain.db"))
    k = Kernel(db=db)
    monkeypatch.setattr("app.core.runtime.kernel_instance.kernel", k)
    monkeypatch.setattr("app.core.runtime.background_worker.kernel", k)
    monkeypatch.setattr("app.core.runtime.background_worker.db", db)
    monkeypatch.setattr("app.store.database.db", db)

    for inst in list(k.agent_registry._instances.values()):
        k.agent_registry._instances.pop(inst.instance_id, None)

    return {"kernel": k, "db": db, "worker": BackgroundWorker()}


def _bg_events(kernel, task_id: str) -> list:
    return kernel.read_events(aggregate_type="background_task", aggregate_id=f"bg_{task_id}")


@pytest.mark.asyncio
async def test_background_task_created_emits_event(bg_env):
    k = bg_env["kernel"]
    worker = bg_env["worker"]

    task = worker.create_task("audit me", plan={"steps": []})
    events = _bg_events(k, task["id"])
    types = [e.type for e in events]
    assert "BackgroundTaskCreated" in types
    assert task["status"] == "pending"


@pytest.mark.asyncio
async def test_background_task_lifecycle_in_event_log(bg_env):
    k = bg_env["kernel"]
    worker = bg_env["worker"]
    plan = {"steps": [{"tool": "get_current_time", "params": {}}]}
    task = worker.create_task("time check", plan=plan)

    with patch.object(k, "invoke_capability", new=AsyncMock(return_value={"status": "success", "result": "ok"})):
        await worker._execute_background_task(task)

    updated = worker.get_task(task["id"])
    assert updated["status"] == "completed"
    assert updated["progress"] == 1.0

    events = _bg_events(k, task["id"])
    types = [e.type for e in events]
    assert "BackgroundTaskCreated" in types
    assert "BackgroundTaskStatusChanged" in types
    assert "BackgroundTaskRequested" in types
    assert "BackgroundTaskCompleted" in types

    statuses = []
    for e in events:
        if e.type in ("BackgroundTaskStatusChanged", "BackgroundTaskCompleted", "BackgroundTaskCreated"):
            statuses.append(e.payload.get("status"))
    assert "pending" in statuses
    assert "running" in statuses
    assert "completed" in statuses


@pytest.mark.asyncio
async def test_background_task_failed_emits_failed_not_completed(bg_env):
    k = bg_env["kernel"]
    worker = bg_env["worker"]
    plan = {"steps": [{"tool": "get_current_time", "params": {}}]}
    task = worker.create_task("fail path", plan=plan)

    with patch.object(k, "invoke_capability", new=AsyncMock(side_effect=RuntimeError("boom"))):
        await worker._execute_background_task(task)

    updated = worker.get_task(task["id"])
    assert updated["status"] == "failed"

    events = _bg_events(k, task["id"])
    types = [e.type for e in events]
    assert "BackgroundTaskFailed" in types
    completed = [e for e in events if e.type == "BackgroundTaskCompleted" and e.payload.get("status") == "completed"]
    assert not completed


@pytest.mark.asyncio
async def test_background_task_rebuild_from_event_log(bg_env):
    k = bg_env["kernel"]
    worker = bg_env["worker"]
    task = worker.create_task("rebuild", plan={"steps": []})

    with patch.object(k, "invoke_capability", new=AsyncMock(return_value={"status": "success"})):
        await worker._execute_background_task(task)

    before = worker.get_task(task["id"])
    with k._db.get_db() as conn:
        conn.execute("DELETE FROM background_tasks")

    count = k.rebuild("background_task")
    assert count > 0

    after = worker.get_task(task["id"])
    assert after is not None
    assert after["status"] == before["status"]
    assert after["progress"] == before["progress"]
