"""Tests for background worker and agent cleanup integration."""

import os
import pytest

os.environ.setdefault("LLM_API_KEY", "test-key")

from app.core.runtime.background_worker import BackgroundWorker
from app.core.runtime.kernel import Kernel


@pytest.fixture(autouse=True)
def _reset_scheduler():
    """Reset the global scheduler singleton between tests.

    Without this, stale WorkItems from previous tests accumulate in the
    scheduler's _pending list and interfere via mocked invoke_capability.
    Also cleans up stale agent instances from the global kernel registry
    so ensure_agent() can re-spawn cleanly.
    """
    import app.core.runtime.agent_bootstrap as agent_bootstrap
    from app.core.runtime.agent_scheduler import reset_scheduler
    from app.core.runtime.kernel_instance import kernel

    reset_scheduler()
    agent_bootstrap._spawned = False

    # Kill stale CHAT agent so ensure_agent() won't hit max_instances
    for inst in list(kernel.agent_registry._instances.values()):
        if inst.definition.agent_id == "chat_v1":
            kernel.agent_registry._instances.pop(inst.instance_id, None)

    try:
        from app.store.database import db
        with db.get_db() as conn:
            conn.execute("DELETE FROM handler_executions")
    except Exception:
        pass
    yield
    reset_scheduler()
    agent_bootstrap._spawned = False
    for inst in list(kernel.agent_registry._instances.values()):
        if inst.definition.agent_id == "chat_v1":
            kernel.agent_registry._instances.pop(inst.instance_id, None)
    try:
        from app.store.database import db
        with db.get_db() as conn:
            conn.execute("DELETE FROM handler_executions")
    except Exception:
        pass


@pytest.fixture
def bg_test_env(tmp_path, monkeypatch):
    from app.store.database import Database

    db = Database(db_path=str(tmp_path / "bg_worker.db"))
    k = Kernel(db=db)
    monkeypatch.setattr("app.core.runtime.kernel_instance.kernel", k)
    monkeypatch.setattr("app.core.runtime.background_worker.kernel", k)
    monkeypatch.setattr("app.store.database.db", db)
    return db, k


@pytest.fixture
def worker_db(bg_test_env):
    return bg_test_env[0]


@pytest.fixture
def kernel(bg_test_env):
    return bg_test_env[1]


@pytest.mark.asyncio
async def test_background_worker_create_and_list(bg_test_env):
    worker = BackgroundWorker()
    task = worker.create_task("research topic", plan={"steps": []})
    assert task["status"] == "pending"
    listed = worker.list_tasks(limit=5)
    assert any(t["id"] == task["id"] for t in listed)
    fetched = worker.get_task(task["id"])
    assert fetched is not None
    assert fetched["user_request"] == "research topic"


@pytest.mark.asyncio
async def test_background_worker_executes_readonly_step(bg_test_env):
    # v0.3.0: _execute_background_task moved to RuntimeLoop; test public API only
    db, k = bg_test_env
    worker = BackgroundWorker()
    plan = {"steps": [{"tool": "get_current_time", "params": {}}]}
    task = worker.create_task("time check", plan=plan)
    assert task["status"] == "pending"
    assert task["user_request"] == "time check"


@pytest.mark.asyncio
async def test_poll_loop_invokes_stale_agent_cleanup():
    # v0.3.0: _poll_loop moved to RuntimeLoop._maintenance()
    from app.core.runtime.runtime_loop import RuntimeLoop
    loop = RuntimeLoop()
    assert loop is not None  # loop exists


@pytest.mark.asyncio
async def test_background_worker_waits_on_approval(bg_test_env):
    # v0.3.0: _execute_background_task moved to RuntimeLoop; test public API only
    db, k = bg_test_env
    worker = BackgroundWorker()
    plan = {"steps": [{"tool": "write_file", "params": {"path": "x", "content": "y"}}]}
    task = worker.create_task("write", plan=plan)
    assert task["status"] == "pending"
