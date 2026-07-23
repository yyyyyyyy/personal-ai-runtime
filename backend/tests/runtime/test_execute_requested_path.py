"""Tests for ExecuteRequested production path (port + handler status sync)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.runtime.handlers.execute_handlers import on_execute_requested
from app.core.runtime.plan_resume import clear_plan_resumes, configure_plan_resume_db


@pytest.fixture(autouse=True)
def _clear_resumes(tmp_path):
    configure_plan_resume_db(None)
    clear_plan_resumes()
    yield
    clear_plan_resumes()
    configure_plan_resume_db(None)

@pytest.mark.asyncio
async def test_execute_handler_marks_completed_and_emits(monkeypatch):
    emitted: list[tuple] = []
    notified: list[tuple] = []

    class Ctx:
        execution_id = "ex1"
        correlation_id = "c1"

        def emit(self, *args, **kwargs):
            emitted.append((args, kwargs))

    monkeypatch.setattr(
        "app.core.runtime.read_ports.query_work_item",
        lambda _id: {
            "id": "act_1",
            "status": "running",
            "title": "Step 1",
            "parent_goal_id": "goal_1",
            "executable_plan": '{"steps":[{"tool":"echo","params":{"t":"1"}}]}',
        },
    )
    monkeypatch.setattr(
        "app.core.runtime.read_ports.bump_parent_activity",
        lambda _gid: notified.append(("bump", _gid)),
    )
    monkeypatch.setattr(
        "app.core.runtime.read_ports.notify_goal_action_completed",
        lambda *a: notified.append(("notify", a)),
    )
    monkeypatch.setattr(
        "app.core.runtime.kernel_instance.kernel",
        MagicMock(
            invoke_capability=AsyncMock(
                return_value={"status": "success", "result": "ok"}
            ),
        ),
    )

    event = MagicMock()
    event.id = "evt"
    event.payload = {"action_id": "act_1"}

    await on_execute_requested(Ctx(), event)

    types = [args[0] for args, _ in emitted]
    assert "WorkItemStatusChanged" in types
    assert "ExecuteCompleted" in types
    wi = next(e for e in emitted if e[0][0] == "WorkItemStatusChanged")
    assert wi[1]["payload"]["status"] == "completed"
    done = next(e for e in emitted if e[0][0] == "ExecuteCompleted")
    assert done[1]["payload"]["status"] == "success"
    assert ("bump", "goal_1") in notified
    assert any(n[0] == "notify" for n in notified)


@pytest.mark.asyncio
async def test_execute_handler_waiting_approval_syncs_status(monkeypatch):
    emitted: list[tuple] = []

    class Ctx:
        execution_id = "ex1"
        correlation_id = "c1"

        def emit(self, *args, **kwargs):
            emitted.append((args, kwargs))

    monkeypatch.setattr(
        "app.core.runtime.read_ports.query_work_item",
        lambda _id: {
            "id": "act_2",
            "status": "waiting_approval",
            "executable_plan": '{"steps":[{"tool":"write_file","params":{}}]}',
        },
    )
    monkeypatch.setattr(
        "app.core.runtime.kernel_instance.kernel",
        MagicMock(
            invoke_capability=AsyncMock(
                return_value={"status": "pending", "approval_id": "apr_x"}
            ),
        ),
    )

    event = MagicMock()
    event.id = "evt"
    event.payload = {"action_id": "act_2"}

    await on_execute_requested(Ctx(), event)

    wi_payloads = [
        e[1]["payload"]["status"]
        for e in emitted
        if e[0][0] == "WorkItemStatusChanged"
    ]
    assert "running" in wi_payloads
    assert "waiting_approval" in wi_payloads
