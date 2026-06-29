"""ADR-0007 Step 5 — ExecutionContext tests.

Handlers receive ExecutionContext instead of AgentInstance. ctx.emit
produces events with the correct actor and correlation_id.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("LLM_API_KEY", "test-key")


@pytest.fixture(autouse=True)
def _reset_scheduler():
    from app.core.runtime.agent_scheduler import reset_scheduler

    reset_scheduler()
    yield
    reset_scheduler()


@pytest.fixture
def kernel(tmp_path):
    from app.core.runtime.kernel import Kernel
    from app.store.database import Database

    return Kernel(db=Database(db_path=str(tmp_path / "exec_ctx.db")))


@pytest.fixture
def planner_def():
    from app.core.runtime.agent_definition import AgentDefinition, SubscriptionRule

    return AgentDefinition(
        agent_id="ctx_planner",
        subscriptions=[SubscriptionRule(event_type="TaskCreated")],
    )


def test_execution_context_emit_produces_correct_actor_and_correlation(kernel):
    """ctx.emit injects actor and correlation_id automatically."""
    from app.core.runtime.execution_context import ExecutionContext

    ctx = ExecutionContext(
        instance_id="aginst_test123",
        actor="agent:aginst_test123",
        correlation_id="corr_abc",
        _kernel=kernel,
    )

    event = ctx.emit(
        event_type="TestEmitted",
        aggregate_type="task",
        aggregate_id="task_1",
        payload={"x": 1},
    )

    assert event.actor == "agent:aginst_test123"
    assert event.correlation_id == "corr_abc"


def test_execution_context_does_not_expose_kernel(kernel):
    """ExecutionContext must not publicly expose the kernel reference.

    Handlers should use ctx.emit(), not ctx._kernel — the underscore
    prefix signals this is internal. This test documents the contract.
    """
    from app.core.runtime.execution_context import ExecutionContext

    ctx = ExecutionContext(
        instance_id="aginst_test",
        actor="agent:aginst_test",
        correlation_id="",
        _kernel=kernel,
    )

    # The kernel is stored with an underscore prefix — it is not part of
    # the public interface. Handlers that bypass ctx.emit and call
    # ctx._kernel directly are violating the contract.
    assert hasattr(ctx, "_kernel")
    # Public attributes are only: instance_id, actor, correlation_id, principal, emit
    public_attrs = {
        a for a in dir(ctx)
        if not a.startswith("_") and a not in ("emit",)
    }
    # dataclass fields are the only public attrs besides emit
    assert public_attrs <= {"instance_id", "actor", "correlation_id", "principal", "execution_id"}


@pytest.mark.asyncio
async def test_handler_receives_execution_context_not_agent_instance(kernel, planner_def):
    """Scheduler passes ExecutionContext to handlers, not AgentInstance."""
    from app.core.runtime.agent_scheduler import get_scheduler
    from app.core.runtime.execution_context import ExecutionContext
    from app.core.runtime.handler_registry import _registry, subscribe

    received_ctx = []

    @subscribe("CtxVerificationEvent")
    async def on_ctx_verify(ctx, event):
        received_ctx.append(ctx)

    registry = kernel.agent_registry
    planner = await registry.spawn(planner_def)
    scheduler = get_scheduler(kernel)
    await scheduler.start()

    event = kernel.emit_event(
        "CtxVerificationEvent", "task", "task_ctx_1", payload={}, actor="user",
    )
    scheduler.enqueue(planner.instance_id, planner.actor_id(), event)
    await scheduler.flush()
    await scheduler.stop()

    assert len(received_ctx) == 1
    ctx = received_ctx[0]
    assert isinstance(ctx, ExecutionContext)
    assert ctx.instance_id == planner.instance_id
    assert ctx.actor == f"agent:{planner.instance_id}"

    _registry.pop("CtxVerificationEvent", None)
    await registry.kill(planner.instance_id)


@pytest.mark.asyncio
async def test_handler_emit_through_context_matches_old_instance_emit(kernel, planner_def):
    """ctx.emit produces events identical to the old instance.emit path.

    The Planner handler emits TaskPlanned via ctx.emit. The event must
    have the same actor and correlation_id as if instance.emit had been
    used.
    """
    from app.core.runtime.agent_scheduler import get_scheduler
    from app.core.runtime.handler_registry import _registry, subscribe

    @subscribe("CtxEmitParity")
    async def on_ctx_emit(ctx, event):
        await ctx.emit(
            event_type="TaskPlanned",
            aggregate_type="task",
            aggregate_id=event.aggregate_id,
            payload={"plan": {"steps": []}},
            caused_by=event.id,
        )

    registry = kernel.agent_registry
    planner = await registry.spawn(planner_def, correlation_id="corr_parity")
    scheduler = get_scheduler(kernel)
    await scheduler.start()

    trigger = kernel.emit_event(
        "CtxEmitParity", "task", "task_parity_1", payload={}, actor="user",
        correlation_id="corr_parity",
    )
    scheduler.enqueue(planner.instance_id, planner.actor_id(), trigger)
    await scheduler.flush()
    await scheduler.stop()

    planned = kernel.read_events(type="TaskPlanned")
    assert len(planned) >= 1
    assert planned[0].actor == f"agent:{planner.instance_id}"
    assert planned[0].correlation_id == "corr_parity"
    assert planned[0].caused_by == trigger.id

    _registry.pop("CtxEmitParity", None)
    await registry.kill(planner.instance_id)


def test_agent_instance_execution_context_factory(kernel, planner_def):
    """AgentInstance.execution_context() produces a valid ExecutionContext."""
    import asyncio

    from app.core.runtime.execution_context import ExecutionContext

    async def _run():
        registry = kernel.agent_registry
        instance = await registry.spawn(planner_def, correlation_id="corr_factory")
        ctx = instance.execution_context()
        assert isinstance(ctx, ExecutionContext)
        assert ctx.instance_id == instance.instance_id
        assert ctx.actor == instance.actor_id()
        assert ctx.correlation_id == "corr_factory"
        await registry.kill(instance.instance_id)

    asyncio.run(_run())
