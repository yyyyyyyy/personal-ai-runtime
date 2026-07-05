"""Tests for backfill_goals_to_work_items script."""

import os
import sys
from pathlib import Path

os.environ.setdefault("LLM_API_KEY", "test-key")

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND_ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT / "backend"))

import pytest


@pytest.fixture
def kernel_with_legacy_goals(tmp_path):
    """Build a Kernel with goals rows that need backfilling to work_items."""
    from app.core.runtime.kernel import Kernel
    from app.store.database import Database

    db_path = str(tmp_path / "backfill.db")
    db = Database(db_path=db_path)
    kernel = Kernel(db=db)

    # Seed two legacy goals via the existing goal projector.
    kernel.emit_event(
        "GoalCreated", "goal", "g_backfill_1",
        payload={
            "title": "Legacy goal 1",
            "description": "From the goals table",
            "status": "active",
            "progress": 0.4,
            "importance": 0.8,
            "urgency": 0.3,
            "deadline": "2026-12-01T00:00:00Z",
            "parent_id": None,
        },
        actor="test",
    )
    kernel.emit_event(
        "GoalCreated", "goal", "g_backfill_2",
        payload={
            "title": "Legacy goal 2",
            "status": "active",
            "progress": 1.0,
            "importance": 0.5,
            "urgency": 0.5,
            "parent_id": "g_backfill_1",
        },
        actor="test",
    )

    return kernel, db_path


def test_backfill_emits_work_items_for_each_goal(kernel_with_legacy_goals):
    """Backfill converts every goals row into a work_type='goal' work_item."""
    from scripts.backfill_goals_to_work_items import backfill

    kernel, db_path = kernel_with_legacy_goals

    summary = backfill(db_path)
    assert summary["total"] == 2
    assert summary["emitted"] == 2
    assert summary["skipped"] == 0
    assert summary["errors"] == 0

    rows = kernel.query_state("work_items", work_type="goal")
    assert len(rows) == 2
    by_id = {r["id"]: r for r in rows}
    assert "g_backfill_1" in by_id
    assert "g_backfill_2" in by_id

    # Spot-check field migration for goal 1
    g1 = by_id["g_backfill_1"]
    assert g1["title"] == "Legacy goal 1"
    assert g1["work_type"] == "goal"
    assert g1["progress"] == 0.4
    assert g1["importance"] == 0.8
    assert g1["urgency"] == 0.3
    assert g1["deadline"] == "2026-12-01T00:00:00Z"


def test_backfill_maps_parent_id_to_parent_work_id(kernel_with_legacy_goals):
    """goal.parent_id (self-FK in goals tree) maps to work_items.parent_work_id."""
    from scripts.backfill_goals_to_work_items import backfill

    kernel, db_path = kernel_with_legacy_goals
    backfill(db_path)

    g2 = kernel.query_state("work_items", id="g_backfill_2")[0]
    assert g2["parent_work_id"] == "g_backfill_1"


def test_backfill_is_idempotent(kernel_with_legacy_goals):
    """Running backfill twice emits nothing on the second run."""
    from scripts.backfill_goals_to_work_items import backfill

    kernel, db_path = kernel_with_legacy_goals

    first = backfill(db_path)
    assert first["emitted"] == 2

    second = backfill(db_path)
    assert second["emitted"] == 0
    assert second["skipped"] == 2


def test_backfill_dry_run_does_not_emit(kernel_with_legacy_goals):
    """--dry-run prints actions but emits no events."""
    from scripts.backfill_goals_to_work_items import backfill

    kernel, db_path = kernel_with_legacy_goals

    summary = backfill(db_path, dry_run=True)
    assert summary["emitted"] == 2

    # No work_items rows should exist
    rows = kernel.query_state("work_items", work_type="goal")
    assert len(rows) == 0


def test_backfill_empty_goals_table_no_op(tmp_path):
    """Backfill on a DB with no goals is a clean no-op."""
    from scripts.backfill_goals_to_work_items import backfill
    from app.core.runtime.kernel import Kernel
    from app.store.database import Database

    db_path = str(tmp_path / "empty.db")
    db = Database(db_path=db_path)
    Kernel(db=db)  # initialise schema

    summary = backfill(db_path)
    assert summary == {"total": 0, "skipped": 0, "emitted": 0, "errors": 0}
