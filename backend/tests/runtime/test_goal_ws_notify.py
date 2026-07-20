"""Regression: work_item (goal/action) emits must broadcast goal_changed."""

from __future__ import annotations

from unittest.mock import patch

def test_work_item_created_triggers_goal_changed(isolated_kernel):
    k, _db = isolated_kernel
    with patch("app.core.runtime.notification_bridge.broadcast_event") as broadcast:
        k.emit_event(
            type="WorkItemCreated",
            aggregate_type="work_item",
            aggregate_id="goal_ws_1",
            payload={"work_type": "goal", "title": "Learn Rust", "status": "active"},
            actor="test",
        )
    payloads = [call.args[0] for call in broadcast.call_args_list]
    types = [p.get("type") for p in payloads]
    assert "goal_changed" in types
    goal_evt = next(p for p in payloads if p.get("type") == "goal_changed")
    assert goal_evt["event_type"] == "WorkItemCreated"
    assert goal_evt["work_item_id"] == "goal_ws_1"
    assert goal_evt["work_type"] == "goal"


def test_non_work_item_does_not_broadcast_goal_changed(isolated_kernel):
    k, _db = isolated_kernel
    with patch("app.core.runtime.notification_bridge.broadcast_event") as broadcast:
        k.emit_event(
            type="ConversationCreated",
            aggregate_type="conversation",
            aggregate_id="conv_no_goal",
            payload={"title": "hi"},
            actor="test",
        )
    types = [call.args[0].get("type") for call in broadcast.call_args_list]
    assert "goal_changed" not in types
