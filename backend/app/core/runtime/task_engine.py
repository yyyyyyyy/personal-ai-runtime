"""WorkItem CRUD service — thin emit/query helpers over the Kernel ABI.

v0.3.0: the ``TaskEngine`` class and module-level singleton were removed.
The methods are now module-level functions. This eliminates a God-Object-lite
wrapper (closes ARCHITECTURE_SURVIVAL_REVIEW Medium #11) without changing
any caller's business logic: import sites shift from
``from ... import task_engine`` to ``from ... import create_work_item, ...``
and calls drop the ``task_engine.`` prefix.

The functions remain thin wrappers over ``kernel.emit_event`` +
``read_ports`` queries plus three pieces of real business logic that were
always worth keeping: status-machine validation (StateManager), dependency
checks, and recursive tree assembly.
"""
import json
import uuid
from enum import Enum
from typing import TYPE_CHECKING

from app.core.runtime import read_ports
from app.core.runtime.kernel_instance import kernel
from app.core.runtime.runtime_container import _LazyProxy, runtime


# ── State Manager (folded from state_manager.py) ─────────────────────────

class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    BLOCKED = "blocked"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"


# Valid state transitions
_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.PENDING: {TaskStatus.RUNNING, TaskStatus.CANCELLED},
    TaskStatus.RUNNING: {
        TaskStatus.BLOCKED, TaskStatus.WAITING_APPROVAL,
        TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.RETRYING,
    },
    TaskStatus.BLOCKED: {TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.CANCELLED},
    TaskStatus.WAITING_APPROVAL: {TaskStatus.RUNNING, TaskStatus.CANCELLED},
    TaskStatus.RETRYING: {TaskStatus.PENDING, TaskStatus.FAILED},
    TaskStatus.COMPLETED: set(),  # terminal
    TaskStatus.FAILED: {TaskStatus.PENDING, TaskStatus.RETRYING},  # can retry
    TaskStatus.CANCELLED: set(),  # terminal
}


class StateManager:
    """Validates and performs state transitions."""

    def validate_transition(self, from_status: TaskStatus, to_status: TaskStatus) -> bool:
        """Check if a transition is allowed."""
        if to_status not in _TRANSITIONS.get(from_status, set()):
            raise ValueError(
                f"Illegal state transition: {from_status.value} -> {to_status.value}. "
                f"Allowed: {[s.value for s in _TRANSITIONS.get(from_status, set())]}"
            )
        return True

    def transition(self, entity_id: str, entity_type: str, from_status: TaskStatus, to_status: TaskStatus) -> TaskStatus:
        """Perform a validated state transition."""
        self.validate_transition(from_status, to_status)
        return to_status

    @staticmethod
    def is_terminal(status: TaskStatus) -> bool:
        return status in (TaskStatus.COMPLETED, TaskStatus.CANCELLED)

    @staticmethod
    def is_active(status: TaskStatus) -> bool:
        return status in (TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.BLOCKED, TaskStatus.WAITING_APPROVAL)


if TYPE_CHECKING:
    state_manager: StateManager
else:
    state_manager = _LazyProxy(lambda: runtime.state_manager)


def create_work_item(
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

    item = read_ports.query_work_item(item_id)
    if not item:
        raise RuntimeError(f"WorkItem {item_id} not found after creation")
    return item


def update_work_item_fields(
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
    if not get_work_item(item_id):
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
        return get_work_item(item_id)

    kernel.emit_event(
        type="WorkItemUpdated",
        aggregate_type="work_item",
        aggregate_id=item_id,
        payload=payload,
        actor="user",
    )
    return get_work_item(item_id)


def get_work_item(item_id: str) -> dict | None:
    return read_ports.query_work_item(item_id)


def get_sub_work_items(parent_work_id: str) -> list[dict]:
    return read_ports.query_work_items(
        parent_work_id=parent_work_id, order="priority_desc",
    )


def get_work_items_for_goal(goal_id: str, *, work_type: str | None = None) -> list[dict]:
    filters: dict = {"parent_goal_id": goal_id, "order": "priority_desc"}
    if work_type:
        filters["work_type"] = work_type
    return read_ports.query_work_items(**filters)


def get_work_item_tree(goal_id: str) -> list[dict]:
    """Get the full work item tree for a goal, with nested sub-items."""
    root_items = get_work_items_for_goal(goal_id)
    for item in root_items:
        item["sub_items"] = _get_subtree(item["id"])
    return root_items


def _get_subtree(item_id: str) -> list[dict]:
    sub_items = get_sub_work_items(item_id)
    for item in sub_items:
        item["sub_items"] = _get_subtree(item["id"])
    return sub_items


def update_work_item_status(item_id: str, new_status: str) -> dict | None:
    item = get_work_item(item_id)
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
    return get_work_item(item_id)


def list_work_items(
    status: str | None = None,
    work_type: str | None = None,
    limit: int = 50,
) -> list[dict]:
    filters: dict = {"limit": limit}
    if status:
        filters["status"] = status
        filters["order"] = "priority_desc"
    else:
        filters["order"] = "created_at_desc"
    if work_type:
        filters["work_type"] = work_type
    return read_ports.query_work_items(**filters)


def are_dependencies_met(item_id: str) -> bool:
    item = get_work_item(item_id)
    if not item or not item.get("dependencies_json"):
        return True
    dependencies = json.loads(item["dependencies_json"])
    for dep_id in dependencies:
        dep = get_work_item(dep_id)
        if not dep or dep["status"] != TaskStatus.COMPLETED.value:
            return False
    return True


def delete_work_item(item_id: str) -> None:
    kernel.emit_event("WorkItemDeleted", "work_item", item_id, actor="user")


# ── Backward-compat aliases ───────────────────────────────────────────────
# Kept for tests and any external caller that still uses the Task vocabulary.
# Prefer the work_item_* names for new code.

def create_task(name, description="", parent_goal_id=None, parent_task_id=None,
                priority=0, dependencies=None):
    return create_work_item(
        title=name, description=description, work_type="task",
        parent_goal_id=parent_goal_id, parent_work_id=parent_task_id,
        priority=priority, dependencies=dependencies)

def get_task(item_id: str) -> dict | None:
    return get_work_item(item_id)

def get_subtasks(parent_work_id: str) -> list[dict]:
    return get_sub_work_items(parent_work_id)

def get_tasks_for_goal(goal_id: str, *, work_type: str | None = None) -> list[dict]:
    return get_work_items_for_goal(goal_id, work_type=work_type)

def get_task_tree(goal_id: str) -> list[dict]:
    return get_work_item_tree(goal_id)

def update_task_status(item_id: str, new_status: str) -> dict | None:
    return update_work_item_status(item_id, new_status)

def list_tasks(status: str | None = None, work_type: str | None = None,
               limit: int = 50) -> list[dict]:
    return list_work_items(status=status, work_type=work_type, limit=limit)
