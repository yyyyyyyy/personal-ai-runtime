"""Task Engine — unified work item model (v0.5.0: Task + Action → WorkItem).

All agents share this model. WorkItem projection writes go through the Kernel.
"""
import json
import uuid

from app.core.runtime.kernel_instance import kernel
from app.core.runtime.state_manager import TaskStatus, state_manager


class TaskEngine:
    """CRUD operations for the unified WorkItem model."""

    def create_work_item(
        self,
        title: str,
        *,
        description: str = "",
        work_type: str = "task",
        parent_goal_id: str | None = None,
        parent_work_id: str | None = None,
        priority: int = 0,
        dependencies: list[str] | None = None,
        executable_plan: str | None = None,
        # v1.0 Phase 3a: goal-unification fields. Populated when work_type='goal';
        # ignored (fall back to schema defaults) for other work_types.
        progress: float | None = None,
        importance: float | None = None,
        urgency: float | None = None,
        deadline: str | None = None,
        last_activity_at: str | None = None,
        status: str = "pending",
    ) -> dict:
        item_id = str(uuid.uuid4())
        deps_json = json.dumps(dependencies) if dependencies else None

        payload: dict = {
            "title": title,
            "description": description,
            "work_type": work_type,
            "parent_goal_id": parent_goal_id,
            "parent_work_id": parent_work_id,
            "priority": priority,
            "dependencies_json": deps_json,
            "executable_plan": executable_plan,
            "status": status,
        }
        # v1.0 goal fields — only attach to payload when explicitly provided
        # so the projector's .get(field, default) falls through to schema
        # defaults for non-goal work_types. This keeps rebuild byte-identical
        # for legacy callers.
        if progress is not None:
            payload["progress"] = progress
        if importance is not None:
            payload["importance"] = importance
        if urgency is not None:
            payload["urgency"] = urgency
        if deadline is not None:
            payload["deadline"] = deadline
        if last_activity_at is not None:
            payload["last_activity_at"] = last_activity_at

        kernel.emit_event(
            type="WorkItemCreated",
            aggregate_type="work_item",
            aggregate_id=item_id,
            payload=payload,
            actor="user",
        )

        rows = kernel.query_state("work_items", id=item_id)
        if not rows:
            raise RuntimeError(f"WorkItem {item_id} not found after creation")
        return rows[0]

    def update_work_item_fields(
        self,
        item_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        status: str | None = None,
        priority: int | None = None,
        progress: float | None = None,
        importance: float | None = None,
        urgency: float | None = None,
        deadline: str | None = None,
        last_activity_at: str | None = None,
        parent_work_id: str | None = None,
    ) -> dict | None:
        """Update arbitrary fields on a work_item via WorkItemUpdated event.

        v1.0 Phase 3a: supports the goal-unification fields so /api/work-items
        can update progress/deadline/etc. Status transitions still go through
        update_work_item_status (which validates the state machine).
        """
        if not self.get_work_item(item_id):
            return None

        payload: dict = {}
        if title is not None:
            payload["title"] = title
        if description is not None:
            payload["description"] = description
        if status is not None:
            payload["status"] = status
        if priority is not None:
            payload["priority"] = priority
        if progress is not None:
            payload["progress"] = progress
        if importance is not None:
            payload["importance"] = importance
        if urgency is not None:
            payload["urgency"] = urgency
        if deadline is not None:
            payload["deadline"] = deadline
        if last_activity_at is not None:
            payload["last_activity_at"] = last_activity_at
        if parent_work_id is not None:
            payload["parent_work_id"] = parent_work_id

        if not payload:
            return self.get_work_item(item_id)

        kernel.emit_event(
            type="WorkItemUpdated",
            aggregate_type="work_item",
            aggregate_id=item_id,
            payload=payload,
            actor="user",
        )
        return self.get_work_item(item_id)

    # Backward-compat aliases
    def create_task(self, name, description="", parent_goal_id=None, parent_task_id=None,
                    priority=0, dependencies=None):
        return self.create_work_item(
            title=name, description=description, work_type="task",
            parent_goal_id=parent_goal_id, parent_work_id=parent_task_id,
            priority=priority, dependencies=dependencies)

    def get_work_item(self, item_id: str) -> dict | None:
        rows = kernel.query_state("work_items", id=item_id)
        return rows[0] if rows else None

    get_task = get_work_item  # backward compat

    def get_sub_work_items(self, parent_work_id: str) -> list[dict]:
        return kernel.query_state("work_items", parent_work_id=parent_work_id,
                                  order="priority_desc")

    get_subtasks = get_sub_work_items  # backward compat

    def get_work_items_for_goal(self, goal_id: str, *, work_type: str | None = None) -> list[dict]:
        filters: dict = {"parent_goal_id": goal_id, "order": "priority_desc"}
        if work_type:
            filters["work_type"] = work_type
        return kernel.query_state("work_items", **filters)

    get_tasks_for_goal = get_work_items_for_goal  # backward compat

    def get_work_item_tree(self, goal_id: str) -> list[dict]:
        """Get the full work item tree for a goal, with nested sub-items."""
        root_items = self.get_work_items_for_goal(goal_id)
        for item in root_items:
            item["sub_items"] = self._get_subtree(item["id"])
        return root_items

    get_task_tree = get_work_item_tree  # backward compat

    def _get_subtree(self, item_id: str) -> list[dict]:
        sub_items = self.get_sub_work_items(item_id)
        for item in sub_items:
            item["sub_items"] = self._get_subtree(item["id"])
        return sub_items

    def update_work_item_status(self, item_id: str, new_status: str) -> dict | None:
        item = self.get_work_item(item_id)
        if not item:
            return None

        from_status = TaskStatus(item.get("status", "pending"))
        to_status = TaskStatus(new_status)
        state_manager.transition(item_id, "work_item", from_status, to_status)

        kernel.emit_event(
            type="WorkItemStatusChanged",
            aggregate_type="work_item",
            aggregate_id=item_id,
            payload={"status": new_status},
            actor="user",
        )
        return self.get_work_item(item_id)

    update_task_status = update_work_item_status  # backward compat

    def list_work_items(self, status: str | None = None, work_type: str | None = None,
                        limit: int = 50) -> list[dict]:
        filters: dict = {"limit": limit}
        if status:
            filters["status"] = status
            filters["order"] = "priority_desc"
        else:
            filters["order"] = "created_at_desc"
        if work_type:
            filters["work_type"] = work_type
        return kernel.query_state("work_items", **filters)

    list_tasks = list_work_items  # backward compat

    def are_dependencies_met(self, item_id: str) -> bool:
        item = self.get_work_item(item_id)
        if not item or not item.get("dependencies_json"):
            return True
        dependencies = json.loads(item["dependencies_json"])
        for dep_id in dependencies:
            dep = self.get_work_item(dep_id)
            if not dep or dep["status"] != TaskStatus.COMPLETED.value:
                return False
        return True

    def delete_work_item(self, item_id: str) -> None:
        kernel.emit_event("WorkItemDeleted", "work_item", item_id, actor="user")


task_engine = TaskEngine()
