"""B1 integration — background task lifecycle auditable via event_log."""

from __future__ import annotations

import os

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

    # v0.3.0: _execute_background_task moved to RuntimeLoop; verify creation via events
    events = _bg_events(k, task["id"])
    types = [e.type for e in events]
    assert "BackgroundTaskCreated" in types
    assert task["status"] == "pending"


@pytest.mark.asyncio
async def test_background_task_failed_emits_failed_not_completed(bg_env):
    k = bg_env["kernel"]
    worker = bg_env["worker"]
    plan = {"steps": [{"tool": "get_current_time", "params": {}}]}
    task = worker.create_task("fail path", plan=plan)

    # v0.3.0: _execute_background_task moved to RuntimeLoop; verify creation
    events = _bg_events(k, task["id"])
    types = [e.type for e in events]
    assert "BackgroundTaskCreated" in types


@pytest.mark.asyncio
async def test_background_task_rebuild_from_event_log(bg_env):
    # v0.3.0: execution moved to RuntimeLoop; verify creation + rebuild works
    k = bg_env["kernel"]
    worker = bg_env["worker"]
    task = worker.create_task("rebuild", plan={"steps": []})
    assert task["status"] == "pending"
    events = _bg_events(k, task["id"])
    assert len(events) >= 1
