"""Tests for State Manager."""
import pytest

from app.core.runtime.task_engine import TaskStatus, state_manager


class TestStateManager:
    def test_valid_transitions(self):
        assert state_manager.validate_transition(TaskStatus.PENDING, TaskStatus.RUNNING)
        assert state_manager.validate_transition(TaskStatus.RUNNING, TaskStatus.COMPLETED)
        assert state_manager.validate_transition(TaskStatus.RUNNING, TaskStatus.BLOCKED)
        assert state_manager.validate_transition(TaskStatus.RUNNING, TaskStatus.WAITING_APPROVAL)
        assert state_manager.validate_transition(TaskStatus.RUNNING, TaskStatus.FAILED)
        assert state_manager.validate_transition(TaskStatus.BLOCKED, TaskStatus.PENDING)
        assert state_manager.validate_transition(TaskStatus.BLOCKED, TaskStatus.CANCELLED)
        assert state_manager.validate_transition(TaskStatus.FAILED, TaskStatus.PENDING)
        assert state_manager.validate_transition(TaskStatus.PENDING, TaskStatus.CANCELLED)

    def test_invalid_transitions(self):
        with pytest.raises(ValueError):
            state_manager.validate_transition(TaskStatus.COMPLETED, TaskStatus.RUNNING)
        with pytest.raises(ValueError):
            state_manager.validate_transition(TaskStatus.CANCELLED, TaskStatus.RUNNING)
        with pytest.raises(ValueError):
            state_manager.validate_transition(TaskStatus.COMPLETED, TaskStatus.PENDING)

    def test_terminal_states(self):
        assert state_manager.is_terminal(TaskStatus.COMPLETED)
        assert state_manager.is_terminal(TaskStatus.CANCELLED)
        assert not state_manager.is_terminal(TaskStatus.RUNNING)
        assert not state_manager.is_terminal(TaskStatus.PENDING)

    def test_active_states(self):
        assert state_manager.is_active(TaskStatus.PENDING)
        assert state_manager.is_active(TaskStatus.RUNNING)
        assert state_manager.is_active(TaskStatus.BLOCKED)
        assert state_manager.is_active(TaskStatus.WAITING_APPROVAL)
        assert not state_manager.is_active(TaskStatus.COMPLETED)

    def test_transition_with_event_bus(self):
        entity_id = "test-task-1"
        result = state_manager.transition(entity_id, "task", TaskStatus.PENDING, TaskStatus.RUNNING)
        assert result == TaskStatus.RUNNING

    def test_retrying_transitions(self):
        """RETRYING must be reachable from RUNNING/FAILED and resolve to PENDING/FAILED."""
        assert state_manager.validate_transition(TaskStatus.RUNNING, TaskStatus.RETRYING)
        assert state_manager.validate_transition(TaskStatus.FAILED, TaskStatus.RETRYING)
        assert state_manager.validate_transition(TaskStatus.RETRYING, TaskStatus.PENDING)
        assert state_manager.validate_transition(TaskStatus.RETRYING, TaskStatus.FAILED)
        with pytest.raises(ValueError):
            state_manager.validate_transition(TaskStatus.RETRYING, TaskStatus.COMPLETED)
        with pytest.raises(ValueError):
            state_manager.validate_transition(TaskStatus.PENDING, TaskStatus.RETRYING)


class TestScheduledExecutionTransitionValidation:
    """ScheduledExecution.transition_to uses the Lane A FSM (not domain TaskStatus)."""

    def test_valid_transition_succeeds(self):
        from app.core.runtime.scheduled_execution import ScheduledExecution
        item = ScheduledExecution(event_type="X")
        item.transition_to("running")
        assert item.status == "running"
        assert item.started_at is not None

    def test_invalid_transition_raises(self):
        from app.core.runtime.scheduled_execution import ScheduledExecution
        item = ScheduledExecution(event_type="X", status="completed")
        with pytest.raises(ValueError):
            item.transition_to("running")

    def test_running_to_retrying_succeeds(self):
        from app.core.runtime.scheduled_execution import ScheduledExecution
        item = ScheduledExecution(event_type="X", status="running")
        item.transition_to("retrying")
        assert item.status == "retrying"
        # retrying → pending is the recovery path used by Scheduler._recover
        item.transition_to("pending")
        assert item.status == "pending"

    def test_domain_only_status_rejected(self):
        from app.core.runtime.scheduled_execution import ScheduledExecution
        item = ScheduledExecution(event_type="X", status="running")
        with pytest.raises(ValueError):
            item.transition_to("waiting_approval")  # type: ignore[arg-type]
