"""Coverage tests for agent_scheduler start/stop lifecycle."""
import pytest

from app.core.runtime.agent_scheduler import Scheduler


@pytest.mark.asyncio
async def test_scheduler_start_stop(isolated_kernel):
    """Scheduler start/stop lifecycle should work cleanly."""
    k, db = isolated_kernel
    sched = Scheduler(kernel=k)
    await sched.start()
    assert sched._running is True
    assert sched._worker_task is not None
    await sched.stop()
    assert sched._running is False


@pytest.mark.asyncio
async def test_scheduler_start_twice(isolated_kernel):
    """Starting a scheduler twice should be idempotent."""
    k, db = isolated_kernel
    sched = Scheduler(kernel=k)
    await sched.start()
    await sched.start()
    assert sched._running is True
    await sched.stop()


@pytest.mark.asyncio
async def test_scheduler_stop_before_start(isolated_kernel):
    """Stopping a scheduler that was never started should not crash."""
    k, db = isolated_kernel
    sched = Scheduler(kernel=k)
    await sched.stop()
    assert sched._running is False


@pytest.mark.asyncio
async def test_scheduler_stop_and_restart(isolated_kernel):
    """Stop and restart scheduler should work."""
    k, db = isolated_kernel
    sched = Scheduler(kernel=k)
    await sched.start()
    await sched.stop()
    await sched.start()
    assert sched._running is True
    await sched.stop()
