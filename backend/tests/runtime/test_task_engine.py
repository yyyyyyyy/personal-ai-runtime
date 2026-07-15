"""Tests for WorkItem engine (uses work_items)."""
import os

os.environ["LLM_API_KEY"] = "test-key"

from app.core.runtime.task_engine import (
    create_task,
    get_subtasks,
    get_task,
    list_tasks,
)


class TestTaskEngine:
    def test_create_and_get_task(self):
        task = create_task(name="Test Task", description="A test task")
        assert task["title"] == "Test Task"
        assert task["status"] == "pending"
        assert task["description"] == "A test task"

        retrieved = get_task(task["id"])
        assert retrieved is not None
        assert retrieved["title"] == "Test Task"

    def test_create_subtask(self):
        parent = create_task(name="Parent Task")
        child = create_task(
            name="Child Task",
            parent_task_id=parent["id"],
            priority=5,
        )
        assert child["parent_work_id"] == parent["id"]
        assert child["priority"] == 5

        subtasks = get_subtasks(parent["id"])
        assert len(subtasks) == 1
        assert subtasks[0]["title"] == "Child Task"

    def test_task_for_goal(self):
        task = create_task(name="Standalone Task")
        assert task["parent_goal_id"] is None

        tasks = list_tasks()
        assert any(t["id"] == task["id"] for t in tasks)

    def test_update_status(self):
        from app.core.runtime.task_engine import update_task_status
        task = create_task(name="Status Test")
        updated = update_task_status(task["id"], "running")
        assert updated["status"] == "running"

        completed = update_task_status(task["id"], "completed")
        assert completed["status"] == "completed"

    def test_dependencies_met(self):
        from app.core.runtime.task_engine import are_dependencies_met, update_task_status
        dep = create_task(name="Dependency Task")
        update_task_status(dep["id"], "running")
        update_task_status(dep["id"], "completed")

        main_task = create_task(
            name="Main Task",
            dependencies=[dep["id"]],
        )
        assert are_dependencies_met(main_task["id"])

    def test_list_tasks(self):
        tasks = list_tasks(limit=10)
        assert isinstance(tasks, list)
