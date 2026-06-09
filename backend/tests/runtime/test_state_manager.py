"""Tests for State Manager."""
import pytest

from app.core.runtime.state_manager import TaskStatus, state_manager


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
