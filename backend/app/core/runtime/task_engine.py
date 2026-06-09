"""Task Engine — unified task model: Goal -> Project -> Task -> Execution.

All agents share this model. Task projection writes go through the Kernel.
"""

import json
import uuid

from app.core.runtime.event_bus import EventType, event_bus
from app.core.runtime.kernel_instance import kernel
from app.core.runtime.state_manager import TaskStatus, state_manager
from app.store.database import db


class TaskEngine:
    """CRUD operations for the unified task model, with state management and event publishing."""

    def create_task(
        self,
        name: str,
        description: str = "",
        parent_goal_id: str | None = None,
        parent_task_id: str | None = None,
        priority: int = 0,
        dependencies: list[str] | None = None,
    ) -> dict:
        task_id = str(uuid.uuid4())

        kernel.create_task(
            name=name,
            plan={"summary": description, "priority": priority},
            parent_goal_id=parent_goal_id,
            parent_task_id=parent_task_id,
            priority=priority,
            dependencies=dependencies,
            actor="user",
            task_id=task_id,
        )

        event_bus.publish(
            EventType.TASK_CREATED,
            {
                "task_id": task_id,
                "name": name,
                "parent_goal_id": parent_goal_id,
                "parent_task_id": parent_task_id,
            },
        )

        task = self.get_task(task_id)
        if task is None:
            raise RuntimeError(f"Task {task_id} not found after creation")
        return task

    def get_task(self, task_id: str) -> dict | None:
        with db.get_db() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return dict(row) if row else None

    def get_subtasks(self, parent_task_id: str) -> list[dict]:
        with db.get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE parent_task_id = ? ORDER BY priority DESC, created_at ASC",
                (parent_task_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_tasks_for_goal(self, goal_id: str) -> list[dict]:
        with db.get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE parent_goal_id = ? AND parent_task_id IS NULL ORDER BY priority DESC",
                (goal_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_task_tree(self, goal_id: str) -> list[dict]:
        """Get the full task tree for a goal, with nested subtasks."""
        root_tasks = self.get_tasks_for_goal(goal_id)
        result = []
        for task in root_tasks:
            task_dict = dict(task)
            task_dict["subtasks"] = self._get_subtree(task["id"])
            result.append(task_dict)
        return result

    def _get_subtree(self, task_id: str) -> list[dict]:
        subtasks = self.get_subtasks(task_id)
        result = []
        for task in subtasks:
            task_dict = dict(task)
            task_dict["subtasks"] = self._get_subtree(task["id"])
            result.append(task_dict)
        return result

    def update_task_status(self, task_id: str, new_status: str) -> dict | None:
        task = self.get_task(task_id)
        if not task:
            return None

        from_status = TaskStatus(task["status"])
        to_status = TaskStatus(new_status)

        state_manager.transition(task_id, "task", from_status, to_status)

        kernel.change_task_status(task_id, new_status, actor="user")

        if to_status == TaskStatus.COMPLETED:
            event_bus.publish(EventType.TASK_COMPLETED, {"task_id": task_id, "name": task["name"]})
        elif to_status == TaskStatus.FAILED:
            event_bus.publish(EventType.TASK_FAILED, {"task_id": task_id, "name": task["name"]})

        return self.get_task(task_id)

    def list_tasks(self, status: str | None = None, limit: int = 50) -> list[dict]:
        with db.get_db() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM tasks WHERE status = ? ORDER BY priority DESC, created_at DESC LIMIT ?",
                    (status, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,)
                ).fetchall()
        return [dict(r) for r in rows]

    def are_dependencies_met(self, task_id: str) -> bool:
        """Check if all dependencies of this task are completed."""
        task = self.get_task(task_id)
        if not task or not task.get("dependencies_json"):
            return True

        dependencies = json.loads(task["dependencies_json"])
        for dep_id in dependencies:
            dep = self.get_task(dep_id)
            if not dep or dep["status"] != TaskStatus.COMPLETED.value:
                return False
        return True


# Global singleton
task_engine = TaskEngine()
