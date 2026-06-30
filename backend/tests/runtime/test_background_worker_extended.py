"""Tests for background worker and agent cleanup integration."""

import os
from unittest.mock import AsyncMock, patch

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
    db, k = bg_test_env
    worker = BackgroundWorker()
    plan = {"steps": [{"tool": "get_current_time", "params": {}}]}
    task = worker.create_task("time check", plan=plan)

    with patch.object(k, "invoke_capability", new=AsyncMock(return_value={"status": "success", "result": "2026-01-01"})):
        await worker._execute_background_task(task)

    updated = worker.get_task(task["id"])
    assert updated["status"] == "completed"
    assert updated["progress"] == 1.0


@pytest.mark.asyncio
async def test_poll_loop_invokes_stale_agent_cleanup():
    worker = BackgroundWorker()
    with patch(
        "app.core.runtime.background_worker.kernel.agent_registry.cleanup_stale",
        return_value=[],
    ) as cleanup:
        with patch.object(worker, "_process_pending", new=AsyncMock()):
            worker._running = True
            loop_task = __import__("asyncio").create_task(worker._poll_loop())
            await __import__("asyncio").sleep(0.05)
            worker._running = False
            loop_task.cancel()
            try:
                await loop_task
            except __import__("asyncio").CancelledError:
                pass
    cleanup.assert_called()


@pytest.mark.asyncio
async def test_background_worker_waits_on_approval(bg_test_env):
    db, k = bg_test_env
    worker = BackgroundWorker()
    plan = {"steps": [{"tool": "write_file", "params": {"path": "x", "content": "y"}}]}
    task = worker.create_task("write", plan=plan)

    with patch.object(k, "invoke_capability", new=AsyncMock(return_value={"status": "pending", "approval_id": "apr_x"})):
        await worker._execute_background_task(task)

    updated = worker.get_task(task["id"])
    assert updated["status"] == "waiting_approval"
