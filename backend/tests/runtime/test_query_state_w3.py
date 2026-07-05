"""W3 tests for kernel.query_state selectors + governance/kernel coverage gaps.

Targets uncovered branches in kernel_query_state.py, kernel_governance.py,
and kernel.py to close the CI coverage gap from 82% to 84%.
"""

import os

os.environ["LLM_API_KEY"] = "test-key"

import asyncio
from datetime import datetime, timezone

from app.core.runtime.kernel import Kernel
from app.store.database import Database


def _kernel(tmp_path, name="w3"):
    path = str(tmp_path / f"query_state_{name}.db")
    return Kernel(db=Database(db_path=path))


class TestQueryStateW3:

    def test_memories_by_claim_status(self, tmp_path):
        k = _kernel(tmp_path)
        k.emit_event("MemoryDerived", "memory", "m-claim", payload={
            "category": "test", "content": "Claimed", "source": "chat",
            "confidence": 0.7, "origin": "claim", "claim_status": "proposed",
        })
        results = k.query_state("memories", claim_status="proposed")
        assert any(r["id"] == "m-claim" for r in results)
        results2 = k.query_state("memories", claim_status="ratified")
        assert not any(r["id"] == "m-claim" for r in results2)

    def test_goals_has_deadline(self, tmp_path):
        k = _kernel(tmp_path)
        k.emit_event("GoalCreated", "goal", "g-dl", payload={
            "title": "Deadline", "deadline": "2099-01-01T00:00:00",
        })
        k.emit_event("GoalCreated", "goal", "g-nd", payload={
            "title": "No deadline",
        })
        results = k.query_state("goals", has_deadline=True)
        ids = {r["id"] for r in results}
        assert "g-dl" in ids
        assert "g-nd" not in ids

    def test_approvals_by_status(self, tmp_path):
        k = _kernel(tmp_path)
        k.emit_event("GoalCreated", "goal", "ga", payload={
            "title": "A", "status": "active",
        })
        k.emit_event("ApprovalRequested", "approval", "app-pending", payload={
            "task_id": "ga", "action": "shell_exec", "params": {},
            "proposed_by": "agent:test",
        })
        k.emit_event("ApprovalRequested", "approval", "app-approved", payload={
            "task_id": "ga", "action": "write_file", "params": {},
            "proposed_by": "agent:test",
        })
        k.grant_approval("app-approved", actor="user")

        pending = k.query_state("approvals", status="pending")
        assert len(pending) == 1 and pending[0]["id"] == "app-pending"
        approved = k.query_state("approvals", status="approved")
        assert len(approved) == 1 and approved[0]["id"] == "app-approved"

    def test_messages_by_conversation_and_order(self, tmp_path):
        k = _kernel(tmp_path)
        k.emit_event("ConversationCreated", "conversation", "cv", payload={
            "title": "C",
        })
        k.emit_event("MessageAppended", "conversation", "cv", payload={
            "role": "user", "content": "hi",
        })
        k.emit_event("MessageAppended", "conversation", "cv", payload={
            "role": "assistant", "content": "hey",
        })
        msgs = k.query_state("messages", conversation_id="cv",
                             order="created_at_asc")
        assert len(msgs) == 2
        assert msgs[0]["content"] == "hi"
        assert msgs[1]["content"] == "hey"
        # No conversation_id returns empty list
        assert k.query_state("messages") == []

    def test_notifications_unread_filter(self, tmp_path):
        k = _kernel(tmp_path)
        k.emit_event("NotificationCreated", "notification", "n-u", payload={
            "type": "goal_stagnant", "title": "Stale", "content": "...",
        })
        k.emit_event("NotificationCreated", "notification", "n-r", payload={
            "type": "info", "title": "Read", "content": "...",
        })
        k.emit_event("NotificationRead", "notification", "n-r", payload={})
        unread = k.query_state("notifications", unread_only=True)
        assert len(unread) == 1 and unread[0]["id"] == "n-u"

    def test_notifications_by_created_date(self, tmp_path):
        k = _kernel(tmp_path)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        k.emit_event("NotificationCreated", "notification", "n-d", payload={
            "type": "info", "title": "Dated", "content": "...",
        })
        results = k.query_state("notifications", created_on_date=today)
        assert any(r["id"] == "n-d" for r in results)

    def test_tasks_by_parent_task_id(self, tmp_path):
        k = _kernel(tmp_path)
        k.emit_event("GoalCreated", "goal", "gp", payload={"title": "Parent"})
        k.emit_event("GoalCreated", "goal", "t-p", payload={
            "title": "Parent", "parent_goal_id": "gp",
        })
        k.emit_event("GoalCreated", "goal", "t-c", payload={
            "title": "Child", "parent_goal_id": "gp",
            "parent_work_id": "t-p", "priority": 1,
        })
        subs = k.query_state("work_items", parent_work_id="t-p")
        assert len(subs) == 1 and subs[0]["id"] == "t-c"

    def test_tasks_by_status_with_order(self, tmp_path):
        k = _kernel(tmp_path)
        for i in range(3):
            k.emit_event("GoalCreated", "goal", f"t{i}", payload={
                "title": f"T{i}", "priority": i,
            })
        k.emit_event("WorkItemStatusChanged", "work_item", "t1", payload={
            "status": "completed",
        }, actor="user")
        pending = k.query_state("work_items", status="pending", limit=2,
                                order="priority_desc_created_desc")
        assert len(pending) == 2
        for t in pending:
            assert t["status"] == "pending"


class TestKernelGovernanceCoverage:

    def test_expire_stale_approvals(self, tmp_path):
        k = _kernel(tmp_path, "gov")
        k.emit_event("GoalCreated", "goal", "ge", payload={"title": "Expiry"})
        k.emit_event("ApprovalRequested", "approval", "app-x", payload={
            "task_id": "ge", "action": "shell_exec", "params": {},
            "proposed_by": "agent:test",
        })
        with k._db.get_db() as conn:
            conn.execute(
                "UPDATE approvals SET expires_at = '2020-01-01T00:00:00' "
                "WHERE id = 'app-x'"
            )
        count = k.expire_stale_approvals()
        assert count == 1
        assert k.query_state("approvals", id="app-x")[0]["status"] == "expired"


class TestKernelEdgePaths:

    def test_read_events_with_limit(self, tmp_path):
        k = _kernel(tmp_path, "re")
        k.emit_event("GoalCreated", "goal", "g1", payload={"title": "One"})
        k.emit_event("GoalCreated", "goal", "g2", payload={"title": "Two"})
        assert len(k.read_events(limit=1)) == 1
        assert len(k.read_events()) >= 2

    def test_submit_command_completion(self, tmp_path):
        k = _kernel(tmp_path, "sc")

        async def _run():
            async def _emit_later():
                await asyncio.sleep(0.05)
                k.emit_event(
                    "WorkItemCompleted", "work_item", "ts",
                    payload={"status": "completed"},
                    correlation_id="corr-sc",
                )
            task = asyncio.create_task(_emit_later())
            result = await k.submit_command(
                type="WorkItemRequested",
                aggregate_type="work_item",
                aggregate_id="ts",
                payload={"title": "Test"},
                actor="user",
                correlation_id="corr-sc",
                completion_type="WorkItemCompleted",
                timeout=2.0,
            )
            await task
            return result

        result = asyncio.run(_run())
        assert result.get("status") == "completed"


class TestUncoveredSelectors:

    def test_query_inbox_emails(self, tmp_path):
        k = _kernel(tmp_path, "ie")
        with k._db.get_db() as conn:
            conn.execute(
                """INSERT INTO inbox_emails
                   (id, subject, sender, preview, status, received_at, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                ("ie1", "Hello", "a@b.com", "preview", "unread", "2024-01-01", "2024-01-01"),
            )
        results = k.query_state("inbox_emails", limit=5)
        assert len(results) >= 1

    def test_policy_events_by_capability(self, tmp_path):
        k = _kernel(tmp_path, "pol")
        k.emit_event("PolicyCreated", "policy", "p1", payload={
            "capability": "shell_exec", "risk_level": "high",
        })
        k.emit_event("PolicyCreated", "policy", "p2", payload={
            "capability": "web_search", "risk_level": "low",
        })
        results = k.query_state("policy_events", capability="shell_exec")
        assert len(results) == 1 and results[0]["capability"] == "shell_exec"
        all_pols = k.query_state("policy_events", limit=5)
        assert len(all_pols) == 2

    def test_goals_updated_since(self, tmp_path):
        k = _kernel(tmp_path, "us")
        k.emit_event("GoalCreated", "goal", "g-upd", payload={
            "title": "Updated", "status": "active",
        })
        k.emit_event("GoalUpdated", "goal", "g-upd", payload={
            "title": "Updated Now",
        })
        results = k.query_state("goals", updated_since="2020-01-01", limit=10)
        ids = {r["id"] for r in results}
        assert "g-upd" in ids

    def test_deny_approval(self, tmp_path):
        k = _kernel(tmp_path, "dny")
        k.emit_event("GoalCreated", "goal", "gd", payload={"title": "Deny"})
        k.emit_event("ApprovalRequested", "approval", "app-d", payload={
            "task_id": "gd", "action": "shell_exec", "params": {},
            "proposed_by": "agent:test",
        })
        k.deny_approval("app-d", actor="user")
        rec = k.query_state("approvals", id="app-d")[0]
        assert rec["status"] == "denied"

    def test_recall_memory(self, tmp_path):
        """Test recall_memory semantic search - ensures ChromaDB path covered."""
        k = _kernel(tmp_path, "rm")
        results = k.recall_memory("hello", k=2)
        assert isinstance(results, list)


class TestSovereigntyGaps:

    def test_count_events(self, tmp_path):
        k = _kernel(tmp_path, "ce")
        k.emit_event("GoalCreated", "goal", "g-ce", payload={"title": "C"})
        k.emit_event("GoalCreated", "goal", "g-ce2", payload={"title": "D"})
        assert k.count_events("goal") == 2
        assert k.count_events("nonexistent") == 0

    def test_bootstrap_chat_from_snapshot(self, tmp_path):
        k = _kernel(tmp_path, "bs")
        convs = [{"id": "c1", "title": "Chat"}]
        msgs = [{"id": "m1", "role": "user", "content": "hi",
                 "conversation_id": "c1", "created_at": "2024-01-01"}]
        result = k.bootstrap_chat_from_snapshot(convs, msgs, [])
        assert result["conversations"] == 1
        assert result["messages"] == 1


class TestKernelReadEvents:

    def test_read_events_by_id(self, tmp_path):
        k = _kernel(tmp_path, "rid")
        k.emit_event("GoalCreated", "goal", "g-id", payload={"title": "X"})
        events = k.read_events()
        results = k.read_events(id=events[0].id)
        assert len(results) == 1 and results[0].id == events[0].id

    def test_read_events_by_aggregate_type(self, tmp_path):
        k = _kernel(tmp_path, "rat")
        k.emit_event("GoalCreated", "goal", "g-at", payload={"title": "T"})
        results = k.read_events(aggregate_type="goal")
        assert all(e.aggregate_type == "goal" for e in results)
        assert len(results) >= 1

    def test_read_events_by_types(self, tmp_path):
        k = _kernel(tmp_path, "rty")
        k.emit_event("GoalCreated", "goal", "g-ty", payload={"title": "T"})
        k.emit_event("GoalCompleted", "goal", "g-ty", payload={})
        results = k.read_events(types=["GoalCreated"])
        assert all(e.type == "GoalCreated" for e in results)

    def test_read_events_by_seqs(self, tmp_path):
        k = _kernel(tmp_path, "rseq")
        k.emit_event("GoalCreated", "goal", "g-s1", payload={"title": "S1"})
        k.emit_event("GoalCreated", "goal", "g-s2", payload={"title": "S2"})
        seqs = [e.seq for e in k.read_events()[:2]]
        if len(seqs) >= 2:
            results = k.read_events_by_seqs(seqs)
            assert len(results) == 2
        # Empty should return []
        assert k.read_events_by_seqs([]) == []

    def test_submit_command_timeout(self, tmp_path):
        k = _kernel(tmp_path, "to")

        async def _run():
            result = await k.submit_command(
                type="WorkItemRequested", aggregate_type="work_item",
                aggregate_id="to", payload={}, actor="user",
                correlation_id="no-one-completes", timeout=0.1,
            )
            return result

        result = asyncio.run(_run())
        assert result["error"] == "timeout"


class TestQueryGapFill:

    def test_inbox_emails_by_id(self, tmp_path):
        k = _kernel(tmp_path, "ieid")
        with k._db.get_db() as conn:
            conn.execute(
                """INSERT INTO inbox_emails (id, created_at)
                   VALUES (?, ?)""",
                ("ie-x", "2024-01-01"),
            )
        results = k.query_state("inbox_emails", id="ie-x")
        assert len(results) == 1 and results[0]["id"] == "ie-x"

    def test_memories_by_id(self, tmp_path):
        k = _kernel(tmp_path, "mid")
        k.emit_event("MemoryDerived", "memory", "m-id", payload={
            "category": "test", "content": "By ID", "source": "test",
            "confidence": 0.5, "origin": "self_report",
        })
        results = k.query_state("memories", id="m-id")
        assert len(results) == 1 and results[0]["id"] == "m-id"

    def test_notifications_by_type_and_title(self, tmp_path):
        k = _kernel(tmp_path, "ntt")
        k.emit_event("NotificationCreated", "notification", "nt-x", payload={
            "type": "goal_stagnant", "title": "Special", "content": "...",
        })
        results = k.query_state("notifications", type="goal_stagnant", title="Special")
        assert len(results) == 1 and results[0]["id"] == "nt-x"
