"""Regression test: memory projection changes must trigger WS broadcast.

Covers Bug 1 from the self-review — ``MemoryDeleted`` originally returned
early before ``_notify_memory_changed`` was reached, so frontends never
learned about deletions. We patch ``broadcast_event`` and assert it is
called for every memory index event type, including delete.
"""
from __future__ import annotations

import os

os.environ.setdefault("LLM_API_KEY", "test-key")

from unittest.mock import patch


def test_memory_derived_triggers_broadcast(isolated_kernel):
    k, _db = isolated_kernel
    with patch(
        "app.core.runtime.notification_bridge.broadcast_event"
    ) as broadcast:
        k.emit_event(
            type="MemoryDerived",
            aggregate_type="memory",
            aggregate_id="mem_b1_derive",
            payload={"category": "fact", "content": "user likes tea", "source": "t"},
            actor="test",
        )
    types = [call.args[0].get("event_type") for call in broadcast.call_args_list]
    assert "MemoryDerived" in types


def test_memory_deleted_triggers_broadcast(isolated_kernel):
    """The original Bug 1 — deletion path must also broadcast."""
    k, _db = isolated_kernel
    # First create so delete has something to remove from the index.
    k.emit_event(
        type="MemoryDerived",
        aggregate_type="memory",
        aggregate_id="mem_b1_del",
        payload={"category": "fact", "content": "tmp", "source": "t"},
        actor="test",
    )
    with patch(
        "app.core.runtime.notification_bridge.broadcast_event"
    ) as broadcast:
        k.emit_event(
            type="MemoryDeleted",
            aggregate_type="memory",
            aggregate_id="mem_b1_del",
            actor="test",
        )
    types = [call.args[0].get("event_type") for call in broadcast.call_args_list]
    assert "MemoryDeleted" in types, (
        "MemoryDeleted must trigger memory_changed broadcast so frontends "
        "can invalidate their cache on deletion (regression for Bug 1)."
    )


def test_non_memory_event_does_not_broadcast(isolated_kernel):
    """Unrelated events must not spuriously fire memory_changed."""
    k, _db = isolated_kernel
    with patch(
        "app.core.runtime.notification_bridge.broadcast_event"
    ) as broadcast:
        k.emit_event(
            type="WorkItemCreated",
            aggregate_type="goal",
            aggregate_id="goal_no_broadcast",
            payload={"title": "x"},
            actor="test",
        )
    broadcast.assert_not_called()
