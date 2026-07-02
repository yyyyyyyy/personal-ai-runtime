"""State Manager — unified state machine for all tasks, actions, and executions.

All modules share a single state machine. Illegal transitions raise exceptions.
"""

from enum import Enum


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    BLOCKED = "blocked"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Valid state transitions
_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.PENDING: {TaskStatus.RUNNING, TaskStatus.CANCELLED},
    TaskStatus.RUNNING: {TaskStatus.BLOCKED, TaskStatus.WAITING_APPROVAL, TaskStatus.COMPLETED, TaskStatus.FAILED},
    TaskStatus.BLOCKED: {TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.CANCELLED},
    TaskStatus.WAITING_APPROVAL: {TaskStatus.RUNNING, TaskStatus.CANCELLED},
    TaskStatus.COMPLETED: set(),  # terminal
    TaskStatus.FAILED: {TaskStatus.PENDING},  # can retry
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


from app.core.runtime.runtime_container import _LazyProxy, runtime
state_manager = _LazyProxy(lambda: runtime.state_manager)
