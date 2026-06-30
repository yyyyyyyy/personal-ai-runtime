"""Trigger Engine — condition-based event triggers for proactive behavior.

Scans event_log periodically, matches trigger conditions, generates suggestions.

v0.2.1: All writes go through Kernel events + projectors.
Reads go through kernel.query_state.
"""

import json
import uuid
from datetime import UTC, datetime, timedelta

from app.core.runtime.kernel_instance import kernel


class TriggerEngine:
    """Evaluates trigger conditions and generates proactive suggestions."""

    def __init__(self):
        self._builtin_triggers = [
            {
                "name": "email_backlog_50",
                "trigger_type": "threshold",
                "condition_json": json.dumps({"event_type": "InboxEmailRecorded", "count": 50, "window_days": 1}),
                "action_type": "suggestion",
                "action_config": json.dumps({"template": "收件箱积压50封邮件，需要整理吗？"}),
            },
        ]

    def seed_builtin_triggers(self):
        """Ensure built-in triggers exist via Kernel events."""
        for trigger in self._builtin_triggers:
            existing = kernel.query_state("triggers", name=trigger["name"])
            if not existing:
                tid = trigger.get("id") or str(uuid.uuid4())
                kernel.emit_event(
                    "TriggerCreated",
                    "trigger",
                    tid,
                    payload={
                        "name": trigger["name"],
                        "trigger_type": trigger["trigger_type"],
                        "condition": json.loads(trigger.get("condition_json", "{}")),
                        "action_type": trigger["action_type"],
                        "action_config": json.loads(trigger.get("action_config", "{}")),
                    },
                    actor="system",
                )

    def evaluate_all(self) -> list[dict]:
        """Evaluate all enabled triggers and return generated suggestions."""
        triggers = kernel.query_state("triggers", enabled=True)

        suggestions = []
        for trigger in triggers:
            result = self._evaluate_trigger(trigger)
            if result:
                suggestions.extend(result)
        return suggestions

    def evaluate_and_notify(self) -> list[dict]:
        """Evaluate triggers, persist notifications, and push via WebSocket."""
        from app.core.runtime.notification_bridge import push_notification

        suggestions = self.evaluate_all()
        notified = []
        for s in suggestions:
            content = s.get("content", "")
            if not content:
                continue
            title = f"主动建议 · {s.get('trigger_id', 'trigger')[:8]}"
            push_notification("suggestion", title, content)
            notified.append(s)
        return notified

    def _evaluate_trigger(self, trigger: dict) -> list[dict] | None:
        trigger_type = trigger["trigger_type"]
        condition = json.loads(trigger["condition_json"])

        if trigger_type == "staleness":
            return self._eval_staleness(trigger, condition)
        if trigger_type == "threshold":
            return self._eval_threshold(trigger, condition)
        return None

    def _eval_staleness(self, trigger: dict, condition: dict) -> list[dict] | None:
        days = condition.get("days", 7)
        action_config = json.loads(trigger.get("action_config", "{}"))
        template = action_config.get("template", "")

        suggestions = []
        rows = kernel.query_state(
            "goals",
            status="active",
            last_activity_older_than_days=days,
            limit=100,
        )

        for goal in rows:
            msg = template.replace("{goal_title}", goal.get("title", ""))
            suggestions.append({
                "trigger_id": trigger["id"],
                "type": "suggestion",
                "content": msg,
                "goal_id": goal.get("id"),
            })

        return suggestions if suggestions else None

    def _eval_threshold(self, trigger: dict, condition: dict) -> list[dict] | None:
        event_type = condition.get("event_type", "")
        count = condition.get("count", 50)
        window_days = condition.get("window_days", 1)
        action_config = json.loads(trigger.get("action_config", "{}"))
        template = action_config.get("template", "")

        since_ts = (datetime.now(UTC) - timedelta(days=window_days)).isoformat()

        matched = kernel.read_events(
            types=[event_type],
            since_ts=since_ts,
            limit=count + 1,
        )

        actual_count = len(matched)
        if actual_count >= count:
            msg = template.format(count=actual_count)
            return [{"trigger_id": trigger["id"], "type": "suggestion", "content": msg}]

        return None

    def create_trigger(
        self,
        name: str,
        trigger_type: str,
        condition: dict,
        action_type: str,
        action_config: dict | None = None,
    ) -> dict | None:
        tid = str(uuid.uuid4())
        kernel.emit_event(
            "TriggerCreated",
            "trigger",
            tid,
            payload={
                "name": name,
                "trigger_type": trigger_type,
                "condition": condition,
                "action_type": action_type,
                "action_config": action_config or {},
            },
            actor="system",
        )
        return self.get_trigger(tid)

    def get_trigger(self, tid: str) -> dict | None:
        rows = kernel.query_state("triggers", id=tid)
        return rows[0] if rows else None

    def list_triggers(self) -> list[dict]:
        return kernel.query_state("triggers", limit=500)

    def delete_trigger(self, tid: str):
        existing = self.get_trigger(tid)
        if existing:
            kernel.emit_event(
                "TriggerDeleted",
                "trigger",
                tid,
                payload={
                    "name": existing.get("name", ""),
                    "trigger_type": existing.get("trigger_type", ""),
                },
                actor="system",
            )


trigger_engine = TriggerEngine()
# registered in RuntimeContainer.inventory()
