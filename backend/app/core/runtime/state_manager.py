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
    """Validates and performs state transitions. Publishes events on transition."""

    def __init__(self, event_bus=None):
        self._event_bus = event_bus

    def validate_transition(self, from_status: TaskStatus, to_status: TaskStatus) -> bool:
        """Check if a transition is allowed."""
        if to_status not in _TRANSITIONS.get(from_status, set()):
            raise ValueError(
                f"Illegal state transition: {from_status.value} -> {to_status.value}. "
                f"Allowed: {[s.value for s in _TRANSITIONS.get(from_status, set())]}"
            )
        return True

    def transition(self, entity_id: str, entity_type: str, from_status: TaskStatus, to_status: TaskStatus) -> TaskStatus:
        """Perform a validated state transition and publish event."""
        self.validate_transition(from_status, to_status)

        if self._event_bus:
            self._event_bus.publish(
                "StateTransition",
                {
                    "entity_id": entity_id,
                    "entity_type": entity_type,
                    "from": from_status.value,
                    "to": to_status.value,
                },
            )

        return to_status

    @staticmethod
    def is_terminal(status: TaskStatus) -> bool:
        return status in (TaskStatus.COMPLETED, TaskStatus.CANCELLED)

    @staticmethod
    def is_active(status: TaskStatus) -> bool:
        return status in (TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.BLOCKED, TaskStatus.WAITING_APPROVAL)


# Global singleton
state_manager = StateManager()
