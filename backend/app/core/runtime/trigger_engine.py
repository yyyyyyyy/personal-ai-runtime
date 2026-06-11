"""Trigger Engine — condition-based event triggers for proactive behavior.

Scans events table periodically, matches trigger conditions, generates suggestions.
"""

import json
import uuid
from datetime import UTC, datetime

from app.core.runtime.event_bus import EventType, event_bus
from app.core.runtime.kernel_instance import kernel
from app.store.database import db


class TriggerEngine:
    """Evaluates trigger conditions and generates proactive suggestions."""

    def __init__(self):
        self._builtin_triggers = [
            {
                "name": "goal_stagnant_7d",
                "trigger_type": "staleness",
                "condition_json": json.dumps({"field": "goals.last_activity_at", "operator": "older_than", "days": 7}),
                "action_type": "suggestion",
                "action_config": json.dumps({"template": "目标「{goal_title}」已停滞7天，是否需要调整或放弃？"}),
            },
            {
                "name": "email_backlog_50",
                "trigger_type": "threshold",
                "condition_json": json.dumps({"event_type": "email_received", "count": 50, "window_days": 1}),
                "action_type": "suggestion",
                "action_config": json.dumps({"template": "收件箱积压50封邮件，需要整理吗？"}),
            },
            # --- P2.2: Reflection triggers (Tension detection) ---
            {
                "name": "trajectory_inactive_14d",
                "trigger_type": "tension",
                "condition_json": json.dumps({"tension_type": "trajectory_neglect", "inactive_days": 14}),
                "action_type": "suggestion",
                "action_config": json.dumps({"template": "轨迹「{trajectory_desc}」已14天无新活动，是否需要重新评估？"}),
            },
            {
                "name": "tension_unresolved_30d",
                "trigger_type": "tension",
                "condition_json": json.dumps({"tension_type": "unresolved"}),
                "action_type": "suggestion",
                "action_config": json.dumps({"template": "你有一条已确认的张力30天未被关注：「{tension_desc}」，要重新审视吗？"}),
            },
            {
                "name": "competing_imbalance",
                "trigger_type": "tension",
                "condition_json": json.dumps({"tension_type": "competing_dominance", "ratio_threshold": 5}),
                "action_type": "suggestion",
                "action_config": json.dumps({"template": "竞争轨迹对严重失衡（{ratio}:1），弱侧轨迹是否仍具有解释价值？"}),
            },
        ]

    def seed_builtin_triggers(self):
        """Ensure built-in triggers exist in the database."""
        with db.get_db() as conn:
            for trigger in self._builtin_triggers:
                existing = conn.execute(
                    "SELECT id FROM triggers WHERE name = ?", (trigger["name"],)
                ).fetchone()
                if not existing:
                    tid = str(uuid.uuid4())
                    conn.execute(
                        """INSERT INTO triggers (id, name, trigger_type, condition_json,
                           action_type, action_config, enabled, created_at)
                           VALUES (?, ?, ?, ?, ?, ?, 1, ?)""",
                        (tid, trigger["name"], trigger["trigger_type"],
                         trigger["condition_json"], trigger["action_type"],
                         trigger["action_config"], datetime.now(UTC).isoformat()),
                    )

    def evaluate_all(self) -> list[dict]:
        """Evaluate all enabled triggers and return generated suggestions."""
        with db.get_db() as conn:
            triggers = conn.execute(
                "SELECT * FROM triggers WHERE enabled = 1"
            ).fetchall()

        suggestions = []
        for trigger in triggers:
            trigger = dict(trigger)
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
        if trigger_type == "tension":
            return self._eval_tension(trigger, condition)
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

            event_bus.publish(EventType.SUGGESTION_GENERATED, {
                "trigger": trigger["name"],
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

        with db.get_db() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as c FROM events WHERE type = ? AND timestamp >= datetime('now', ?)",
                (event_type, f"-{window_days} days"),
            ).fetchone()

        if row["c"] >= count:
            msg = template.format(count=row["c"])
            event_bus.publish(EventType.SUGGESTION_GENERATED, {
                "trigger": trigger["name"],
                "content": msg,
            })
            return [{"trigger_id": trigger["id"], "type": "suggestion", "content": msg}]

        return None

    def _eval_tension(self, trigger: dict, condition: dict) -> list[dict] | None:
        """Evaluate tension triggers using the Tension Detection module."""
        try:
            from app.core.runtime.tension.detector import run_tension_detection

            result = run_tension_detection()
        except Exception:
            return None

        suggestions = []
        action_config = json.loads(trigger.get("action_config", "{}"))
        template = action_config.get("template", "")

        tension_type = condition.get("tension_type", "")
        if tension_type == "trajectory_neglect" and result.get("trajectory_neglect", 0) > 0:
            suggestions.append({
                "trigger_id": trigger["id"],
                "type": "suggestion",
                "content": template.format(
                    trajectory_desc="某条轨迹",
                ),
            })
        elif tension_type == "unresolved":
            # Check if there are any TensionClaims that were ratified >30d ago
            try:
                claims = kernel.query_state("memories", origin="claim", limit=200)
                for c in claims:
                    p = json.loads(c.get("content", "{}") or "{}") if c.get("content") else {}
                    if isinstance(p, dict) and p.get("claim_type") == "tension":
                        if c.get("claim_status") == "ratified":
                            suggestions.append({
                                "trigger_id": trigger["id"],
                                "type": "suggestion",
                                "content": template.format(
                                    tension_desc=p.get("description", "未命名张力")[:80],
                                ),
                            })
                            break
            except Exception:
                pass
        elif tension_type == "competing_dominance" and result.get("competing_dominance", 0) > 0:
            suggestions.append({
                "trigger_id": trigger["id"],
                "type": "suggestion",
                "content": template.format(ratio="5"),
            })

        return suggestions if suggestions else None

    def create_trigger(
        self,
        name: str,
        trigger_type: str,
        condition: dict,
        action_type: str,
        action_config: dict | None = None,
    ) -> dict | None:
        tid = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        with db.get_db() as conn:
            conn.execute(
                """INSERT INTO triggers (id, name, trigger_type, condition_json, action_type, action_config, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (tid, name, trigger_type, json.dumps(condition), action_type,
                 json.dumps(action_config) if action_config else None, now),
            )
        return self.get_trigger(tid)

    def get_trigger(self, tid: str) -> dict | None:
        with db.get_db() as conn:
            row = conn.execute("SELECT * FROM triggers WHERE id = ?", (tid,)).fetchone()
        return dict(row) if row else None

    def list_triggers(self) -> list[dict]:
        with db.get_db() as conn:
            rows = conn.execute("SELECT * FROM triggers ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

    def delete_trigger(self, tid: str):
        with db.get_db() as conn:
            conn.execute("DELETE FROM triggers WHERE id = ?", (tid,))


trigger_engine = TriggerEngine()
