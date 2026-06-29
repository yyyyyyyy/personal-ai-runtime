"""Agent stale cleanup via AgentRegistry (ADR-0007 Step 10: legacy cleanup_stale_agents removed)."""

import os

os.environ.setdefault("LLM_API_KEY", "test-key")

import asyncio

import pytest

from app.core.runtime.kernel import Kernel
from app.store.database import Database


@pytest.fixture
def kernel(tmp_path):
    return Kernel(db=Database(db_path=str(tmp_path / "cleanup.db")))


def test_cleanup_stale_agents_evicts_old_entries(kernel):
    """AgentRegistry.cleanup_stale evicts instances exceeding max_age."""
    from app.core.runtime.agent_definition import AgentDefinition

    async def _run():
        registry = kernel.agent_registry
        definition = AgentDefinition(agent_id="stale_v1", stale_timeout_seconds=1, tools=[])
        await registry.spawn(definition)

        # Artificially age the instance
        for sid, inst in registry._instances.items():
            if inst.last_active_at:
                from datetime import UTC, datetime
                inst.last_active_at = datetime(2020, 1, 1, tzinfo=UTC).isoformat()

        evicted = await registry.cleanup_stale(max_age_seconds=1)
        assert len(evicted) >= 1

    asyncio.run(_run())


def test_cleanup_stale_agents_keeps_recent_entries(kernel):
    """AgentRegistry.cleanup_stale keeps recently active instances."""
    from app.core.runtime.agent_definition import AgentDefinition

    async def _run():
        registry = kernel.agent_registry
        definition = AgentDefinition(agent_id="recent_v1", stale_timeout_seconds=3600, tools=[])
        await registry.spawn(definition)

        evicted = await registry.cleanup_stale(max_age_seconds=3600)
        assert len(evicted) == 0

    asyncio.run(_run())
