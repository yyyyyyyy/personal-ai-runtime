"""Goals MCP Server — let AI manage user goals within conversations.

Bridges the gap between conversation and goal management: AI can create goals,
update progress, and mark goals complete without the user switching to the Goals page.
"""

import json
import uuid


class GoalsServer:
    """Goal management tools for AI-driven goal operations."""

    def create_goal(self, title: str, description: str = "", importance: float = 0.5,
                    deadline: str = "") -> str:
        """Create a new goal via Kernel event log."""
        from app.core.runtime.kernel_instance import kernel

        goal_id = str(uuid.uuid4())
        payload = {
            "title": title,
            "importance": importance,
        }
        if description:
            payload["description"] = description
        if deadline:
            payload["deadline"] = deadline

        kernel.emit_event(
            "GoalCreated",
            "goal",
            goal_id,
            payload=payload,
            actor="user",
        )

        return json.dumps({
            "goal_id": goal_id,
            "title": title,
            "status": "created",
            "message": f"已创建目标「{title}」",
        }, ensure_ascii=False)

    def update_progress(self, goal_id: str, progress: float, note: str = "") -> str:
        """Update a goal's progress (0.0 to 1.0)."""
        from app.core.runtime.kernel_instance import kernel

        progress = max(0.0, min(1.0, progress))

        kernel.emit_event(
            "GoalUpdated",
            "goal",
            goal_id,
            payload={"progress": progress},
            actor="user",
        )

        msg = f"目标进度已更新为 {progress * 100:.0f}%"
        if note:
            msg += f"（{note}）"

        return json.dumps({
            "goal_id": goal_id,
            "progress": progress,
            "status": "updated",
            "message": msg,
        }, ensure_ascii=False)

    def complete_goal(self, goal_id: str, reflection: str = "") -> str:
        """Mark a goal as completed, optionally with a reflection."""
        from app.core.runtime.kernel_instance import kernel

        kernel.emit_event(
            "GoalCompleted",
            "goal",
            goal_id,
            payload={},
            actor="user",
        )

        # 如果有反思，存入记忆
        if reflection:
            from app.core.agents.memory_engine import memory_engine
            memory_engine.store_memory(
                category="event",
                content=f"完成目标：{reflection}",
                source=f"goal:{goal_id}",
                actor="user",
            )

        return json.dumps({
            "goal_id": goal_id,
            "status": "completed",
            "message": "目标已完成！干得漂亮。" + (f" 已记录你的心得：{reflection}" if reflection else ""),
        }, ensure_ascii=False)

    def list_active_goals(self) -> str:
        """List the user's active goals."""
        from app.core.runtime.kernel_instance import kernel

        goals = kernel.query_state("goals", status="active", limit=20, order="importance_desc")
        return json.dumps({
            "count": len(goals),
            "goals": [{"id": g["id"], "title": g["title"], "progress": g.get("progress", 0),
                        "importance": g.get("importance", 0.5)} for g in goals],
        }, ensure_ascii=False)


goals_server = GoalsServer()
