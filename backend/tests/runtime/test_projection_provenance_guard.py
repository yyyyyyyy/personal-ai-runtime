"""Tests for scripts/check_projection_provenance.py (Strategy A join guard)."""

import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
SCRIPT = BACKEND / "scripts" / "check_projection_provenance.py"


def run_check(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "scripts.check_projection_provenance", *args],
        cwd=str(BACKEND),
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def provenance_db(tmp_path):
    from app.core.runtime.kernel import Kernel
    from app.store.database import Database

    db = Database(db_path=str(tmp_path / "provenance.db"))
    kernel = Kernel(db=db)
    sys.path.insert(0, str(BACKEND))
    try:
        from scripts.check_projection_provenance import bootstrap_sample_scenario

        bootstrap_sample_scenario(kernel)
    finally:
        sys.path.pop(0)
    return db


class TestProjectionProvenanceGuard:
    def test_bootstrap_scenario_passes_subprocess(self):
        result = run_check()
        assert result.returncode == 0, result.stderr or result.stdout
        assert "PROJECTION PROVENANCE OK" in result.stdout

    def test_bootstrap_scenario_passes_scan(self, provenance_db):
        sys.path.insert(0, str(BACKEND))
        try:
            from scripts.check_projection_provenance import check_provenance

            with provenance_db.get_db() as conn:
                assert check_provenance(conn) == []
        finally:
            sys.path.pop(0)

    def test_orphan_goal_not_scanned_by_provenance(self, provenance_db):
        """work_items goal orphans are out of scope for check_provenance.

        Orphan detection for goal rows lives in verify_work_items_goal_rebuild;
        this test pins that check_provenance does not claim them.
        """
        sys.path.insert(0, str(BACKEND))
        try:
            from scripts.check_projection_provenance import check_provenance

            with provenance_db.get_db() as conn:
                conn.execute(
                    """INSERT INTO work_items
                       (id, title, description, work_type, status, progress, importance, urgency,
                        deadline, parent_work_id, created_at, updated_at, last_activity_at)
                       VALUES ('orphan_goal', 'x', '', 'goal', 'active', 0, 0.5, 0.5,
                               NULL, NULL, '2026-01-01', '2026-01-01', '2026-01-01')"""
                )
                violations = check_provenance(conn)
            assert not any(
                v[0] == "work_items" and v[1] == "orphan_goal" for v in violations
            )
        finally:
            sys.path.pop(0)

    def test_orphan_approval_fails(self, provenance_db):
        sys.path.insert(0, str(BACKEND))
        try:
            from scripts.check_projection_provenance import check_provenance

            with provenance_db.get_db() as conn:
                conn.execute(
                    """INSERT INTO approvals
                       (id, task_id, action, params, proposed_by, status, created_at)
                       VALUES ('orphan_apr', NULL, 'read_file', '{}', 'user', 'pending', '2026-01-01')"""
                )
                violations = check_provenance(conn)
            assert any(v[0] == "approvals" and v[1] == "orphan_apr" for v in violations)
        finally:
            sys.path.pop(0)

    def test_orphan_handler_execution_fails(self, provenance_db):
        sys.path.insert(0, str(BACKEND))
        try:
            from scripts.check_projection_provenance import check_provenance

            with provenance_db.get_db() as conn:
                conn.execute(
                    """INSERT INTO handler_executions
                       (id, event_seq, event_id, event_type, handler_name, instance_id,
                        status, retry_count, policy_json, correlation_id,
                        created_at, started_at, completed_at, error)
                       VALUES ('orphan_exec', 1, 'evt_fake', 'TaskCreated', 'on_x', 'inst',
                               'pending', 0, '{}', '', '2026-01-01', '', '', '')"""
                )
                violations = check_provenance(conn)
            assert any(
                v[0] == "handler_executions" and v[1] == "orphan_exec" for v in violations
            )
        finally:
            sys.path.pop(0)

    def test_handler_execution_bad_trigger_fails(self, provenance_db):
        sys.path.insert(0, str(BACKEND))
        try:
            from app.core.runtime.kernel import Kernel
            from app.core.runtime.kernel.constants import (
                AGGREGATE_EXECUTION,
                EVENT_EXECUTION_REQUESTED,
            )
            from scripts.check_projection_provenance import check_provenance

            k = Kernel(db=provenance_db)
            k.emit_event(
                EVENT_EXECUTION_REQUESTED,
                AGGREGATE_EXECUTION,
                "bad_trigger_exec",
                payload={
                    "execution_id": "bad_trigger_exec",
                    "handler_name": "on_bad",
                    "trigger_event_id": "evt_nonexistent",
                    "trigger_event_seq": 9999,
                    "trigger_event_type": "TaskCreated",
                    "instance_id": "inst",
                    "policy": {},
                    "event_seq": 9999,
                },
                actor="scheduler",
            )
            with provenance_db.get_db() as conn:
                violations = check_provenance(conn)
            assert any(
                v[0] == "handler_executions"
                and v[1] == "bad_trigger_exec"
                and "trigger event" in v[2]
                for v in violations
            )
        finally:
            sys.path.pop(0)
