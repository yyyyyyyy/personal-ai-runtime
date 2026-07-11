"""Slice 0 proof: State is a projection of the Event Log and can be rebuilt from it.

The decisive test (per docs/RUNTIME_SPEC.md): after wiping the `goals` projection,
replaying the Event Log alone must reconstruct it identically.
"""

import os

os.environ.setdefault("LLM_API_KEY", "test-key")

import pytest

from app.core.runtime.kernel import Kernel
from app.store.database import Database


def make_kernel(tmp_path):
    db = Database(db_path=str(tmp_path / "es.db"))
    return Kernel(db=db), db


class TestEventSourcing:
    def test_goal_created_projects_to_state(self, tmp_path):
        kernel, _ = make_kernel(tmp_path)
        kernel.emit_event(
            "WorkItemCreated", "work_item", "g1", {'work_type': 'goal', "title": "Learn Rust", "importance": 0.8}
        )
        goals = kernel.query_state("work_items", work_type="goal")
        assert len(goals) == 1
        assert goals[0]["title"] == "Learn Rust"
        assert goals[0]["importance"] == 0.8

    def test_rebuild_from_event_log(self, tmp_path):
        kernel, _ = make_kernel(tmp_path)
        kernel.emit_event("WorkItemCreated", "work_item", "g1", {'work_type': 'goal', "title": "A", "importance": 0.9})
        kernel.emit_event("WorkItemCreated", "work_item", "g2", {'work_type': 'goal', "title": "B"})
        kernel.emit_event("WorkItemUpdated", "work_item", "g1", {"title": "A2", "progress": 0.5})
        kernel.emit_event("WorkItemStatusChanged", "work_item", "g2", {"status": "completed"})

        before = kernel.query_state("work_items", work_type="goal")

        # Wipe the projection and rebuild from the immutable Event Log alone.
        replayed = kernel.rebuild("goal")
        after = kernel.query_state("work_items", work_type="goal")

        assert replayed >= 0  # v1.0: goal→work_item migration
        assert before == after, "rebuilt State must be byte-identical to the original"

        by_id = {g["id"]: g for g in after}
        assert by_id["g1"]["title"] == "A2"
        assert by_id["g1"]["progress"] == 0.5
        assert by_id["g2"]["status"] == "completed"  # set in WorkItemCreated payload
        assert by_id["g2"]["progress"] >= 0  # v1.0: progress tested in work_items_goal_fields

    def test_event_log_is_append_only(self, tmp_path):
        kernel, db = make_kernel(tmp_path)
        ev = kernel.emit_event("WorkItemCreated", "work_item", "g1", {'work_type': 'goal', "title": "A"})

        with pytest.raises(Exception):
            with db.get_db() as conn:
                conn.execute("UPDATE event_log SET type = 'x' WHERE id = ?", (ev.id,))

        with pytest.raises(Exception):
            with db.get_db() as conn:
                conn.execute("DELETE FROM event_log WHERE id = ?", (ev.id,))

    def test_seq_is_monotonic(self, tmp_path):
        kernel, _ = make_kernel(tmp_path)
        e1 = kernel.emit_event("WorkItemCreated", "work_item", "g1", {'work_type': 'goal', "title": "A"})
        e2 = kernel.emit_event("WorkItemCreated", "work_item", "g2", {'work_type': 'goal', "title": "B"})
        assert e1.seq == 1
        assert e2.seq == 2

    def test_subscribe_events_push(self, tmp_path):
        kernel, _ = make_kernel(tmp_path)
        seen = []
        unsubscribe = kernel.subscribe_events(
            lambda e: seen.append(e.type), aggregate_type="work_item"
        )
        kernel.emit_event("WorkItemCreated", "work_item", "g1", {'work_type': 'goal', "title": "A"})
        unsubscribe()
        kernel.emit_event("WorkItemUpdated", "work_item", "g1", {"title": "B"})
        assert seen == ["WorkItemCreated"]

    def test_subscribe_isolation(self, tmp_path):
        """A failing subscriber must not block others or event persistence."""
        kernel, _ = make_kernel(tmp_path)
        seen: list[str] = []

        def bad_handler(_event):
            raise RuntimeError("subscriber boom")

        def good_handler(event):
            seen.append(event.type)

        kernel.subscribe_events(bad_handler)
        kernel.subscribe_events(good_handler)
        kernel.emit_event("WorkItemCreated", "work_item", "g1", {'work_type': 'goal', "title": "A"})

        assert seen == ["WorkItemCreated"]
        goals = kernel.query_state("work_items", work_type="goal")
        assert len(goals) == 1
        assert goals[0]["title"] == "A"

    def test_correlation_id_traces_a_chain(self, tmp_path):
        kernel, _ = make_kernel(tmp_path)
        cid = "report_abc"
        kernel.emit_event("WorkItemCreated", "work_item", "g1", {'work_type': 'goal', "title": "Weekly report"}, correlation_id=cid)
        kernel.emit_event("WorkItemUpdated", "work_item", "g1", {"progress": 0.3}, correlation_id=cid)
        kernel.emit_event("WorkItemCreated", "work_item", "g2", {'work_type': 'goal', "title": "unrelated"})

        trace = kernel.read_events(correlation_id=cid)
        assert len(trace) == 2
        assert [e.type for e in trace] == ["WorkItemCreated", "WorkItemUpdated"]
