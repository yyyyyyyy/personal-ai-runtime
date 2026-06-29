"""Task Engine — unified task model: Goal -> Project -> Task -> Execution.

All agents share this model. Task projection writes go through the Kernel.
"""

import json
import uuid

from app.core.runtime.kernel_instance import kernel
from app.core.runtime.state_manager import TaskStatus, state_manager


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

        import json
        deps_json = json.dumps(dependencies) if dependencies else None
        kernel.emit_event(
            type="TaskCreated",
            aggregate_type="task",
            aggregate_id=task_id,
            payload={
                "name": name,
                "description": description or "",
                "parent_goal_id": parent_goal_id,
                "parent_task_id": parent_task_id,
                "priority": priority,
                "dependencies_json": deps_json,
            },
            actor="user",
        )

        task = self.get_task(task_id)
        if task is None:
            raise RuntimeError(f"Task {task_id} not found after creation")
        return task

    def get_task(self, task_id: str) -> dict | None:
        rows = kernel.query_state("tasks", id=task_id)
        return rows[0] if rows else None

    def get_subtasks(self, parent_task_id: str) -> list[dict]:
        return kernel.query_state(
            "tasks",
            parent_task_id=parent_task_id,
            order="priority_desc",
        )

    def get_tasks_for_goal(self, goal_id: str) -> list[dict]:
        return kernel.query_state(
            "tasks",
            parent_goal_id=goal_id,
            root_only=True,
            order="priority_desc",
        )

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

        kernel.emit_event(
            type="TaskStatusChanged",
            aggregate_type="task",
            aggregate_id=task_id,
            payload={"status": new_status},
            actor="user",
        )

        return self.get_task(task_id)

    def list_tasks(self, status: str | None = None, limit: int = 50) -> list[dict]:
        filters: dict[str, object] = {"limit": limit}
        if status:
            filters["status"] = status
            filters["order"] = "priority_desc_created_desc"
        else:
            filters["order"] = "created_at_desc"
        return kernel.query_state("tasks", **filters)

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
