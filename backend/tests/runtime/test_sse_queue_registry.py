"""Coverage tests for sse_queue_registry."""

import asyncio

import pytest


def test_register_creates_and_returns_queue():
    """register() creates a new queue and returns it."""
    from app.core.runtime.notification_bridge import _registry, register, unregister

    cid = "test_register"
    q = register(cid)
    assert isinstance(q, asyncio.Queue)
    assert _registry.get(cid) is q

    unregister(cid)
    assert cid not in _registry


def test_unregister_removes_queue():
    """unregister() removes the queue from the registry."""
    from app.core.runtime.notification_bridge import _registry, register, unregister

    cid = "test_unregister"
    register(cid)
    unregister(cid)
    assert cid not in _registry


def test_unregister_missing_key_is_noop():
    """unregister() on a missing key does not raise."""
    from app.core.runtime.notification_bridge import unregister

    unregister("nonexistent")


@pytest.mark.asyncio
async def test_push_to_registered_queue():
    """push() delivers payload to the registered asyncio.Queue."""
    from app.core.runtime.notification_bridge import push, register, unregister

    cid = "test_push"
    q = register(cid)

    payload = {"type": "text_delta", "content": "hello"}
    await push(cid, payload)

    item = q.get_nowait()
    assert item == payload

    unregister(cid)


@pytest.mark.asyncio
async def test_push_to_missing_queue_silently_drops():
    """push() silently drops when no queue is registered for the given id."""
    from app.core.runtime.notification_bridge import push

    # Should not raise
    await push("missing_queue", {"type": "text_delta", "content": "dropped"})


@pytest.mark.asyncio
async def test_push_to_full_queue_handles_gracefully():
    """push() logs a warning and drops when the queue is full."""
    from app.core.runtime.notification_bridge import _registry, push

    cid = "test_full"
    # Manually insert a bounded queue to force QueueFull
    q = asyncio.Queue[dict](maxsize=1)
    q.put_nowait({"type": "text_delta", "content": "fills it"})
    _registry[cid] = q

    await push(cid, {"type": "text_delta", "content": "overflow"})

    # Queue still has only one item
    assert q.qsize() == 1
    assert q.get_nowait() == {"type": "text_delta", "content": "fills it"}

    _registry.pop(cid, None)
