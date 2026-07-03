"""Test agent_bootstrap — ensure_agent covers the cache path and instance tracking."""
import pytest


@pytest.mark.asyncio
async def test_ensure_agent_creates_and_caches(monkeypatch, tmp_path):
    """Calling ensure_agent twice only spawns once (covers _spawned guard and instance_id)."""
    from app.core.runtime.kernel import Kernel
    from app.store.database import Database

    k = Kernel(db=Database(db_path=str(tmp_path / "boot.db")))
    monkeypatch.setattr("app.core.runtime.kernel_instance.kernel", k)

    # Reset global state
    import app.core.runtime.agent_bootstrap as boot
    boot._spawned = False
    boot._SINGLETON_INSTANCE_ID = None

    await boot.ensure_agent(k)
    assert boot._spawned is True
    assert boot._SINGLETON_INSTANCE_ID is not None
    first_id = boot._SINGLETON_INSTANCE_ID

    # Second call: covers the cached return path (line 26)
    await boot.ensure_agent(k)
    assert boot._SINGLETON_INSTANCE_ID == first_id

    assert boot.get_singleton_instance_id() == first_id


@pytest.mark.asyncio
async def test_ensure_agent_registers_async_dispatcher(monkeypatch, tmp_path):
    """ensure_agent should register a dispatcher with the kernel."""
    from app.core.runtime.kernel import Kernel
    from app.store.database import Database

    k = Kernel(db=Database(db_path=str(tmp_path / "boot2.db")))
    monkeypatch.setattr("app.core.runtime.kernel_instance.kernel", k)

    import app.core.runtime.agent_bootstrap as boot
    boot._spawned = False
    boot._SINGLETON_INSTANCE_ID = None

    # Before ensure_agent, no dispatchers
    assert len(k._async_dispatchers) == 0

    await boot.ensure_agent(k)

    # After ensure_agent, one dispatcher registered
    assert len(k._async_dispatchers) == 1
    assert callable(k._async_dispatchers[0])
