"""Architecture remediation tests — durable cancel, lifecycle pins, chat C2, prune."""

from __future__ import annotations

import asyncio
import inspect
from datetime import UTC, datetime, timedelta

import pytest

from app.core.runtime.execution import clear_all_cancels
from app.core.runtime.execution_events import (
    emit_execution_completed,
    emit_execution_requested,
    emit_execution_started,
)
from app.core.runtime.kernel.execution_repository import read_scheduled_execution
from app.core.runtime.scheduled_execution import ExecutionPolicy, ScheduledExecution
from app.core.runtime.task_engine import TaskStatus


@pytest.fixture(autouse=True)
def _reset_cancels_and_scheduler():
    from app.core.runtime.agent_scheduler import reset_scheduler

    clear_all_cancels()
    reset_scheduler()
    yield
    clear_all_cancels()
    reset_scheduler()


@pytest.fixture
def kernel(tmp_path):
    from app.core.runtime.kernel import Kernel
    from app.store.database import Database

    return Kernel(db=Database(db_path=str(tmp_path / "arch_remediation.db")))


def test_domain_retrying_not_assigned_in_runtime_production_code():
    """Pin: domain TaskStatus.RETRYING is FSM-only; Lane A owns operational retry."""
    import ast
    from pathlib import Path

    runtime = Path(__file__).resolve().parents[2] / "app" / "core" / "runtime"
    offenders: list[str] = []
    for path in runtime.rglob("*.py"):
        if path.name == "task_engine.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "RETRYING":
                if isinstance(node.value, ast.Name) and node.value.id == "TaskStatus":
                    offenders.append(f"{path.name}:{node.lineno}")
            if isinstance(node, ast.Constant) and node.value == "retrying":
                if path.name in {
                    "agent_scheduler.py",
                    "scheduled_execution.py",
                    "execution_repository.py",
                    "projectors_execution.py",
                    "execution_events.py",
                }:
                    continue
                offenders.append(f"{path.name}:{node.lineno}:literal")
    assert not offenders, f"domain/ops RETRYING leakage: {offenders}"
    assert TaskStatus.RETRYING.value == "retrying"


@pytest.mark.asyncio
async def test_inflight_cancel_projects_failed_before_task_cancel(kernel):
    """ADR-R010: in-flight cancel must leave handler_executions failed (not running)."""
    from app.core.runtime.agent_scheduler import Scheduler

    sch = Scheduler(kernel)
    item = ScheduledExecution(
        id="wi_cancel_d1",
        event_seq=1,
        event_id="ev1",
        event_type="ChatRequested",
        handler_name="on_chat_requested",
        instance_id="test",
        policy=ExecutionPolicy(timeout_seconds=30, max_retries=0),
    )
    emit_execution_requested(kernel, item, actor="scheduler")
    item.transition_to("running")
    emit_execution_started(kernel, item)

    async def _hang():
        await asyncio.sleep(60)

    task = asyncio.create_task(_hang())
    sch._active[item.id] = (item, task)

    assert sch.request_cancel(item.id) is True
    row = read_scheduled_execution(kernel._db, item.id)
    assert row is not None
    assert row.status == "failed"
    assert row.error == "cancelled"
    running, _pending = kernel.recover_scheduled_executions()
    assert all(r.id != item.id for r in running)
    if not task.done():
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


def test_chat_continue_after_tool_is_one_shot_without_tools():
    """ADR-R011 / C2: continue_after_tool_result must not reopen the tool loop."""
    import ast
    from pathlib import Path

    from app.core.agents import brain_llm_ops

    path = Path(brain_llm_ops.__file__)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    fn = None
    for node in tree.body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "continue_after_tool_result":
            fn = node
            break
    assert fn is not None, "continue_after_tool_result missing"

    # No Call with keyword tools=... inside the function body.
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                assert kw.arg != "tools", (
                    "continue_after_tool_result must not pass tools= "
                    "(one-shot completion only; ADR-R011)"
                )

    src = inspect.getsource(brain_llm_ops.continue_after_tool_result)
    assert "chat.completions.create" in src


def test_prune_handler_executions_respects_retention(kernel):
    from app.core.runtime.kernel import sovereignty_ops as ops

    item = ScheduledExecution(
        id="wi_old",
        event_seq=1,
        event_id="ev_old",
        event_type="TimerFired",
        handler_name="on_timer",
        instance_id="test",
    )
    emit_execution_requested(kernel, item, actor="scheduler")
    item.transition_to("running")
    emit_execution_started(kernel, item)
    item.error = None
    item.transition_to("completed")
    emit_execution_completed(kernel, item)

    old_ts = (datetime.now(UTC) - timedelta(days=60)).isoformat()
    with kernel._db.get_db() as conn:
        conn.execute(
            "UPDATE handler_executions SET completed_at = ? WHERE id = ?",
            (old_ts, item.id),
        )

    n = ops.prune_handler_executions(kernel, retention_days=30)
    assert n >= 1
    assert read_scheduled_execution(kernel._db, item.id) is None


def test_philosophy_exceptions_registry_present():
    from app.store.table_registry import PHILOSOPHY_EXCEPTIONS

    assert "knowledge_path_b" in PHILOSOPHY_EXCEPTIONS
    assert "single_process_control_plane" in PHILOSOPHY_EXCEPTIONS
    assert "transport_chat_delta" in PHILOSOPHY_EXCEPTIONS
    assert "handler_executions_soft_prune" in PHILOSOPHY_EXCEPTIONS
