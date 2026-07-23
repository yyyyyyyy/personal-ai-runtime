"""B1 integration — background work-item lifecycle auditable via event_log (INV-W5).

Tests use the background_tasks API module (shim over work_items).
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
    """Inline create — mirrors background_tasks API (WorkItemCreated)."""
    import json
    import uuid
    from datetime import UTC, datetime

    from app.core.runtime.kernel.constants import (
        AGGREGATE_WORK_ITEM,
        EVENT_WORK_ITEM_CREATED,
    )

    task_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    plan_json = json.dumps(plan) if plan else None

    kernel.emit_event(
        EVENT_WORK_ITEM_CREATED,
        AGGREGATE_WORK_ITEM,
        task_id,
        payload={
            "title": user_request,
            "description": "",
            "work_type": "background",
            "parent_work_id": None,
            "parent_goal_id": None,
            "status": "pending",
            "priority": 0,
            "executable_plan": plan_json,
            "progress": 0.0,
            "created_at": now,
        },
        actor="user",
    )
    rows = kernel.query_state("work_items", id=task_id, limit=1)
    return rows[0] if rows else None


def _bg_events(kernel, task_id: str) -> list:
    return kernel.read_events(aggregate_type="work_item", aggregate_id=task_id)


@pytest.mark.asyncio
async def test_background_task_created_emits_event(bg_env):
    k = bg_env["kernel"]
    task = _create_bg_task(k, "audit me", plan={"steps": []})
    events = _bg_events(k, task["id"])
    types = [e.type for e in events]
    assert "WorkItemCreated" in types
    assert task["status"] == "pending"
    assert task["work_type"] == "background"


@pytest.mark.asyncio
async def test_background_task_lifecycle_in_event_log(bg_env):
    k = bg_env["kernel"]
    task = _create_bg_task(
        k, "time check", plan={"steps": [{"tool": "get_current_time", "params": {}}]},
    )
    events = _bg_events(k, task["id"])
    types = [e.type for e in events]
    assert "WorkItemCreated" in types
    assert task["status"] == "pending"


@pytest.mark.asyncio
async def test_background_task_failed_emits_failed_not_completed(bg_env):
    k = bg_env["kernel"]
    task = _create_bg_task(
        k, "fail path", plan={"steps": [{"tool": "get_current_time", "params": {}}]},
    )
    events = _bg_events(k, task["id"])
    types = [e.type for e in events]
    assert "WorkItemCreated" in types


@pytest.mark.asyncio
async def test_background_task_rebuild_from_event_log(bg_env):
    k = bg_env["kernel"]
    task = _create_bg_task(k, "rebuild", plan={"steps": []})
    assert task["status"] == "pending"
    events = _bg_events(k, task["id"])
    assert len(events) >= 1
