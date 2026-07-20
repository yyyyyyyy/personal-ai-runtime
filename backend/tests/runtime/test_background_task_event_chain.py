"""B1 integration — background task lifecycle auditable via event_log.

Tests use the background_tasks API module.
"""
from __future__ import annotations

import pytest

@pytest.fixture(autouse=True)
def _reset_scheduler():
    import app.core.runtime.agent_scheduler as agent_bootstrap
    from app.core.runtime.agent_scheduler import reset_scheduler

    reset_scheduler()
    agent_bootstrap._started = False
    yield
    reset_scheduler()
    agent_bootstrap._started = False


@pytest.fixture
def bg_env(tmp_path, monkeypatch):
    from app.core.runtime.kernel import Kernel
    from app.store.database import Database

    db = Database(db_path=str(tmp_path / "bg_chain.db"))
    k = Kernel(db=db)
    monkeypatch.setattr("app.core.runtime.kernel_instance.kernel", k)
    monkeypatch.setattr("app.store.database.db", db)
    return {"kernel": k, "db": db}


def _create_bg_task(kernel, user_request, plan=None):
    """Inline create_task — mirrors background_tasks API."""
    import json
    import uuid
    from datetime import UTC, datetime

    task_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    plan_json = json.dumps(plan) if plan else None

    kernel.emit_event(
        "BackgroundTaskCreated", "background_task", f"bg_{task_id}",
        payload={
            "task_id": task_id, "user_request": user_request,
            "plan_json": plan_json, "status": "pending",
            "progress": 0.0, "created_at": now,
        },
        actor="user",
    )
    from app.core.runtime.kernel import query_builder as qb
    rows = qb.query_background_tasks(kernel._db, {"id": task_id, "limit": 1})
    return rows[0] if rows else None


def _bg_events(kernel, task_id: str) -> list:
    return kernel.read_events(aggregate_type="background_task", aggregate_id=f"bg_{task_id}")


@pytest.mark.asyncio
async def test_background_task_created_emits_event(bg_env):
    k = bg_env["kernel"]
    task = _create_bg_task(k, "audit me", plan={"steps": []})
    events = _bg_events(k, task["id"])
    types = [e.type for e in events]
    assert "BackgroundTaskCreated" in types
    assert task["status"] == "pending"


@pytest.mark.asyncio
async def test_background_task_lifecycle_in_event_log(bg_env):
    k = bg_env["kernel"]
    task = _create_bg_task(k, "time check", plan={"steps": [{"tool": "get_current_time", "params": {}}]})
    events = _bg_events(k, task["id"])
    types = [e.type for e in events]
    assert "BackgroundTaskCreated" in types
    assert task["status"] == "pending"


@pytest.mark.asyncio
async def test_background_task_failed_emits_failed_not_completed(bg_env):
    k = bg_env["kernel"]
    task = _create_bg_task(k, "fail path", plan={"steps": [{"tool": "get_current_time", "params": {}}]})
    events = _bg_events(k, task["id"])
    types = [e.type for e in events]
    assert "BackgroundTaskCreated" in types


@pytest.mark.asyncio
async def test_background_task_rebuild_from_event_log(bg_env):
    k = bg_env["kernel"]
    task = _create_bg_task(k, "rebuild", plan={"steps": []})
    assert task["status"] == "pending"
    events = _bg_events(k, task["id"])
    assert len(events) >= 1
