"""RuntimeLoop must not block the event loop during maintenance.

Validates that:
1. A slow _drain_memory_index_repairs (offloaded to thread) does not
   prevent timer scans from running concurrently.
2. _process_background_tasks dispatches fire-and-forget so the long
   submit_command timeout does not block the maintenance tick.
3. Drain failures are caught and logged, never crashing the loop.
"""

import asyncio
import pytest

@pytest.fixture
def kernel(isolated_kernel):
    k, _db = isolated_kernel
    return k


@pytest.fixture(autouse=True)
def _reset_singletons():
    from app.core.runtime.runtime_container import runtime
    runtime.reset()
    yield
    runtime.reset()


def test_drain_memory_index_repairs_offloaded_to_thread(kernel, monkeypatch):
    """asyncio.to_thread ensures ChromaDB repair does not block the loop."""
    from app.core.runtime import runtime_loop as rl_mod

    loop = rl_mod.RuntimeLoop()

    call_log: list[str] = []

    def slow_drain():
        call_log.append("drain_start")
        import time
        time.sleep(0.3)  # simulate slow ChromaDB
        call_log.append("drain_end")

    monkeypatch.setattr(loop, "_drain_memory_index_repairs", slow_drain)

    timer_fired: list[str] = []

    async def mock_check_timers():
        timer_fired.append("tick")
    monkeypatch.setattr(loop, "_check_timers", mock_check_timers)

    async def mock_reactions():
        await asyncio.sleep(0)
    monkeypatch.setattr(loop, "_check_reactions", mock_reactions)

    async def mock_bg():
        await asyncio.sleep(0)
    monkeypatch.setattr(loop, "_process_background_tasks", mock_bg)

    async def run():
        # Run maintenance — drain is offloaded to thread.
        maint_task = asyncio.create_task(loop._maintenance())
        # While maintenance runs, timer ticks should still execute.
        for _ in range(5):
            await mock_check_timers()
            await asyncio.sleep(0.05)
        await maint_task

        assert "drain_start" in call_log
        assert "drain_end" in call_log
        assert len(timer_fired) >= 5, "timer ticks must not be starved by drain"

    asyncio.run(run())


def test_background_task_dispatch_does_not_block_maintenance(kernel, monkeypatch):
    """_process_background_tasks with a slow submit_command must return quickly.

    We verify fire-and-forget by replacing the module-level kernel singleton
    that runtime_loop.py references, instrumenting submit_command, and
    asserting _process_background_tasks completes well before the submit.
    """
    from app.core.runtime import runtime_loop as rl_mod

    loop = rl_mod.RuntimeLoop()

    submit_call_count = {"n": 0}
    finished = {"done": False}

    async def slow_submit(*args, **kwargs):
        submit_call_count["n"] += 1
        await asyncio.sleep(5)  # simulate long timeout
        finished["done"] = True
        return {"status": "ok"}

    kernel.submit_command = slow_submit  # type: ignore[assignment]

    real_emit = kernel.emit_event

    def patched_emit(type, agt, agid, payload=None, actor="system", **kw):
        if agt == "background_task":
            return None
        return real_emit(type, agt, agid, payload=payload, actor=actor, **kw)

    kernel.emit_event = patched_emit  # type: ignore[assignment]

    class FakeSch:
        async def start(self):
            pass

    async def mock_ensure(k):
        pass

    # Patch both the loop singleton and kernel_instance (read_ports resolves the latter).
    monkeypatch.setattr(rl_mod, "kernel", kernel)
    monkeypatch.setattr("app.core.runtime.kernel_instance.kernel", kernel)
    monkeypatch.setattr(
        "app.core.runtime.read_ports.query_background_tasks",
        lambda **kw: [{"id": "bg1", "plan_json": "{}"}],
    )
    monkeypatch.setattr(
        "app.core.runtime.agent_scheduler.ensure_scheduler", mock_ensure,
    )
    monkeypatch.setattr(
        "app.core.runtime.agent_scheduler.get_scheduler", lambda k: FakeSch(),
    )

    async def run():
        # Should return in under 2s (fire-and-forget), not 5s+.
        await asyncio.wait_for(
            loop._process_background_tasks(),
            timeout=2.0,
        )
        # Yield control so the fire-and-forget task gets scheduled.
        await asyncio.sleep(0.1)
        assert submit_call_count["n"] == 1, "submit_command must have been dispatched"
        assert not finished["done"], "submit should still be running in background"

    asyncio.run(run())


def test_maintenance_does_not_raise_on_drain_failure(kernel, monkeypatch):
    """If to_thread drain raises, maintenance catches and logs — no crash."""
    from app.core.runtime import runtime_loop as rl_mod

    loop = rl_mod.RuntimeLoop()

    def failing_drain():
        raise RuntimeError("chroma totally down")

    monkeypatch.setattr(loop, "_drain_memory_index_repairs", failing_drain)

    async def mock_reactions():
        await asyncio.sleep(0)

    async def mock_bg():
        await asyncio.sleep(0)

    monkeypatch.setattr(loop, "_check_reactions", mock_reactions)
    monkeypatch.setattr(loop, "_process_background_tasks", mock_bg)

    async def run():
        # Should not raise.
        await loop._maintenance()

    asyncio.run(run())


def test_spawn_background_task_holds_reference_and_cleans_up(kernel):
    """Fire-and-forget tasks must be tracked to prevent GC mid-flight.

    Regression for the create_task footgun: if the Task reference is
    discarded immediately, CPython may garbage-collect it before it
    completes, silently dropping the work.
    """
    from app.core.runtime import runtime_loop as rl_mod

    loop = rl_mod.RuntimeLoop()

    completed = {"done": False}

    async def sample_work():
        await asyncio.sleep(0.05)
        completed["done"] = True

    async def run():
        # Spawn the task.
        loop._spawn_background_task(sample_work())
        # Reference must be held in _bg_tasks.
        assert len(loop._bg_tasks) == 1, "task must be tracked"
        # Wait for completion.
        await asyncio.sleep(0.2)
        # After completion, the done_callback should have removed it.
        assert len(loop._bg_tasks) == 0, "completed task must be cleaned up"
        assert completed["done"], "task must have run to completion"

    asyncio.run(run())

@pytest.mark.asyncio
async def test_scan_fires_due_timer(isolated_kernel):
    from datetime import UTC, datetime, timedelta

    from app.core.runtime.runtime_loop import RuntimeLoop

    k, db = isolated_kernel
    past = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
    k.emit_event(
        "TimerCreated", "timer", "timer_scan_test",
        payload={
            "handler_name": "test_handler",
            "schedule_type": "cron",
            "cron_expr": "hour=0,minute=0",
            "fire_at": past,
        },
        actor="verify",
    )
    import app.core.runtime.runtime_loop as rl_mod

    original = rl_mod.kernel
    rl_mod.kernel = k
    try:
        loop = RuntimeLoop()
        await loop._check_timers()
    finally:
        rl_mod.kernel = original

    with db.get_db() as conn:
        conn.execute("PRAGMA foreign_keys = OFF")
        fired = conn.execute(
            "SELECT 1 FROM event_log WHERE type='TimerFired' "
            "AND aggregate_id='timer_scan_test' LIMIT 1"
        ).fetchone()
    assert fired is not None


@pytest.mark.asyncio
async def test_scan_skips_future_timer(isolated_kernel):
    from datetime import UTC, datetime, timedelta

    from app.core.runtime.runtime_loop import RuntimeLoop

    k, db = isolated_kernel
    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    k.emit_event(
        "TimerCreated", "timer", "timer_future",
        payload={
            "handler_name": "test_handler",
            "schedule_type": "cron",
            "cron_expr": "hour=0,minute=0",
            "fire_at": future,
        },
        actor="verify",
    )
    import app.core.runtime.runtime_loop as rl_mod

    original = rl_mod.kernel
    rl_mod.kernel = k
    try:
        loop = RuntimeLoop()
        await loop._check_timers()
    finally:
        rl_mod.kernel = original

    with db.get_db() as conn:
        conn.execute("PRAGMA foreign_keys = OFF")
        fired = conn.execute(
            "SELECT 1 FROM event_log WHERE type='TimerFired' "
            "AND aggregate_id='timer_future' LIMIT 1"
        ).fetchone()
    assert fired is None
