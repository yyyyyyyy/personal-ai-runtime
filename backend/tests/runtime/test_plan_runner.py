"""Tests for shared plan runner and approval resume dispatch."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.runtime.handlers.plan_runner import parse_plan_steps, run_plan_steps
from app.core.runtime.plan_resume import (
    PlanResume,
    clear_plan_resumes,
    peek_plan_resume,
    register_plan_resume,
    take_plan_resume,
)


@pytest.fixture(autouse=True)
def _clear_resumes():
    clear_plan_resumes()
    yield
    clear_plan_resumes()


def test_parse_plan_steps_rejects_bad_json():
    with pytest.raises(ValueError, match="invalid plan JSON"):
        parse_plan_steps("{not-json")


def test_parse_plan_steps_ok():
    steps = parse_plan_steps('{"steps": [{"tool": "web_search", "params": {"query": "x"}}]}')
    assert len(steps) == 1
    assert steps[0]["tool"] == "web_search"


@pytest.mark.asyncio
async def test_run_plan_steps_success_and_resume_from():
    kernel = MagicMock()
    kernel.invoke_capability = AsyncMock(
        side_effect=[
            {"status": "success", "result": "a"},
            {"status": "success", "result": "b"},
        ]
    )
    steps = [
        {"tool": "t1", "params": {}},
        {"tool": "t2", "params": {}},
    ]
    outcome = await run_plan_steps(
        steps=steps,
        kernel=kernel,
        actor="executor",
        execution_id="ex1",
        correlation_id="c1",
        resume_from=1,
    )
    assert outcome.stopped_reason == "completed"
    assert outcome.completed_steps == 1
    assert kernel.invoke_capability.await_count == 1
    assert kernel.invoke_capability.await_args.kwargs["name"] == "t2"


@pytest.mark.asyncio
async def test_run_plan_steps_missing_tool_fails():
    kernel = MagicMock()
    kernel.invoke_capability = AsyncMock()
    outcome = await run_plan_steps(
        steps=[{"params": {"query": "x"}}],
        kernel=kernel,
        actor="background",
        execution_id="ex1",
        correlation_id=None,
    )
    assert outcome.stopped_reason == "failed"
    kernel.invoke_capability.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_plan_steps_failed_status_stops():
    kernel = MagicMock()
    kernel.invoke_capability = AsyncMock(
        return_value={"status": "error", "error": "denied"}
    )
    outcome = await run_plan_steps(
        steps=[{"tool": "shell_exec", "params": {"command": "ls"}}],
        kernel=kernel,
        actor="background",
        execution_id="ex1",
        correlation_id=None,
    )
    assert outcome.stopped_reason == "failed"
    assert outcome.results[0].status == "failed"


@pytest.mark.asyncio
async def test_run_plan_steps_pending_registers_via_factory():
    kernel = MagicMock()
    kernel.invoke_capability = AsyncMock(
        return_value={"status": "pending", "approval_id": "apr_1"}
    )
    outcome = await run_plan_steps(
        steps=[
            {"tool": "write_file", "params": {"path": "/a", "content": "x"}},
            {"tool": "web_search", "params": {"query": "y"}},
        ],
        kernel=kernel,
        actor="executor",
        execution_id="ex1",
        correlation_id="c1",
        resume_factory=lambda o: PlanResume(
            kind="execute",
            resume_from=o.next_resume_from or 0,
            previous_output=o.previous_output,
            action_id="act1",
        ),
    )
    assert outcome.stopped_reason == "pending"
    assert outcome.next_resume_from == 1
    got = peek_plan_resume("apr_1")
    assert got is not None
    assert got.action_id == "act1"
    assert got.resume_from == 1


def test_plan_resume_with_step_output():
    resume = PlanResume(kind="execute", resume_from=1, action_id="a")
    updated = resume.with_step_output(0, "approved-result")
    assert updated.previous_output == {"step_0_output": "approved-result"}


@pytest.mark.asyncio
async def test_approve_dispatches_execute_resume_with_step_output(monkeypatch):
    from app.core.runtime.handlers import approve_handlers as mod

    register_plan_resume(
        "apr_resume",
        PlanResume(
            kind="execute",
            resume_from=1,
            action_id="act_99",
            previous_output={},
        ),
    )

    emitted: list[tuple] = []

    class Ctx:
        execution_id = "ex"
        correlation_id = "corr"

        def emit(self, *args, **kwargs):
            emitted.append((args, kwargs))

    async def fake_invoke(**kwargs):
        return {"status": "success", "result": "written-ok"}

    monkeypatch.setattr(
        "app.core.runtime.kernel_instance.kernel",
        MagicMock(
            invoke_capability=AsyncMock(side_effect=fake_invoke),
            deny_approval=MagicMock(),
        ),
    )

    event = MagicMock()
    event.id = "evt1"
    event.payload = {
        "approval_id": "apr_resume",
        "decision": "approve",
        "tool_name": "write_file",
        "tool_args": {"path": "/a", "content": "x"},
        "conv_id": "",
        "tool_call_id": "",
    }

    await mod.on_approve_requested(Ctx(), event)

    resume_emits = [e for e in emitted if e[0] and e[0][0] == "ExecuteRequested"]
    assert len(resume_emits) == 1
    payload = resume_emits[0][1]["payload"]
    assert payload["action_id"] == "act_99"
    assert payload["resume_from"] == 1
    assert payload["previous_output"]["step_0_output"] == "written-ok"
    assert take_plan_resume("apr_resume") is None


@pytest.mark.asyncio
async def test_approve_keeps_resume_when_dispatch_fails(monkeypatch):
    from app.core.runtime.handlers import approve_handlers as mod

    register_plan_resume(
        "apr_keep",
        PlanResume(kind="execute", resume_from=1, action_id="act_1"),
    )

    class Ctx:
        execution_id = "ex"
        correlation_id = "corr"

        def emit(self, *args, **kwargs):
            if args and args[0] == "ExecuteRequested":
                raise RuntimeError("emit failed")
            # ApproveCompleted still emitted

    monkeypatch.setattr(
        "app.core.runtime.kernel_instance.kernel",
        MagicMock(
            invoke_capability=AsyncMock(
                return_value={"status": "success", "result": "ok"}
            ),
        ),
    )

    event = MagicMock()
    event.id = "evt1"
    event.payload = {
        "approval_id": "apr_keep",
        "decision": "approve",
        "tool_name": "write_file",
        "tool_args": {},
        "conv_id": "",
        "tool_call_id": "",
    }

    await mod.on_approve_requested(Ctx(), event)
    kept = peek_plan_resume("apr_keep")
    assert kept is not None
    assert kept.previous_output == {"step_0_output": "ok"}
