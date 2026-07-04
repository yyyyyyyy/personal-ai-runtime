"""Test agent_bootstrap — ensure_scheduler covers the cache path and dispatcher registration.

v0.6.0: ensure_agent renamed to ensure_scheduler.
"""
import pytest


@pytest.mark.asyncio
async def test_ensure_scheduler_creates_and_caches(monkeypatch, tmp_path):
    """Calling ensure_scheduler twice only initialises once."""
    from app.core.runtime.kernel import Kernel
    from app.store.database import Database

    k = Kernel(db=Database(db_path=str(tmp_path / "boot.db")))
    monkeypatch.setattr("app.core.runtime.kernel_instance.kernel", k)

    import app.core.runtime.agent_bootstrap as boot
    boot._started = False

    await boot.ensure_scheduler(k)
    assert boot._started is True

    # Second call: covers the cached return path
    await boot.ensure_scheduler(k)
    assert boot._started is True


@pytest.mark.asyncio
async def test_ensure_scheduler_registers_async_dispatcher(monkeypatch, tmp_path):
    """ensure_scheduler should register a dispatcher with the kernel."""
    from app.core.runtime.kernel import Kernel
    from app.store.database import Database

    k = Kernel(db=Database(db_path=str(tmp_path / "boot2.db")))
    monkeypatch.setattr("app.core.runtime.kernel_instance.kernel", k)

    import app.core.runtime.agent_bootstrap as boot
    boot._started = False

    # Before ensure_scheduler, no dispatchers
    assert len(k._async_dispatchers) == 0

    await boot.ensure_scheduler(k)

    # After ensure_scheduler, one dispatcher registered
    assert len(k._async_dispatchers) >= 1
    assert callable(k._async_dispatchers[0])
