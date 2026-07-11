"""Tests for capability_policy.json seed reconcile behaviour.

P1 fix: builtin tools that were tightened in capability_policy.json (e.g.
computer_screenshot / computer_move / computer_scroll moved from auto_allow to
needs_user) must take effect on already-initialised databases, not only on a
fresh DB. ``_ensure_policy`` therefore emits PolicyUpdated when the seed JSON
risk tier disagrees with the existing policy_events row.
"""

import json
from pathlib import Path

import pytest

from app.core.runtime.capability_governance import capability_governance
from app.core.runtime.kernel import Kernel
from app.store.database import Database

POLICY_PATH = Path(__file__).resolve().parents[2] / "capability_policy.json"


@pytest.fixture
def kernel(tmp_path):
    db = Database(db_path=str(tmp_path / "policy_reconcile.db"))
    k = Kernel(db=db)
    return k


def _read_policy_json() -> dict:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def test_computer_screenshot_is_needs_user_in_seed():
    """Contract: computer_screenshot/move/scroll must be needs_user after P1."""
    policy = _read_policy_json()
    assert "computer_screenshot" in policy["needs_user"]
    assert "computer_move" in policy["needs_user"]
    assert "computer_scroll" in policy["needs_user"]
    assert "computer_screenshot" not in policy["auto_allow"]
    assert "computer_move" not in policy["auto_allow"]
    assert "computer_scroll" not in policy["auto_allow"]
    # computer_screen_size stays auto_allow (no privacy risk).
    assert "computer_screen_size" in policy["auto_allow"]


def test_seed_marks_computer_screenshot_high(kernel):
    """Fresh seed → risk_for(computer_screenshot) == 'high'."""
    capability_governance.seed_from_json(kernel)
    assert capability_governance.risk_for("computer_screenshot", kernel=kernel) == "high"
    assert capability_governance.risk_for("computer_move", kernel=kernel) == "high"
    assert capability_governance.risk_for("computer_scroll", kernel=kernel) == "high"
    assert capability_governance.risk_for("computer_screen_size", kernel=kernel) == "low"


def test_seed_reconciles_stale_low_risk(kernel):
    """Already-initialised DB with stale low-risk row → seed emits PolicyUpdated."""
    # Simulate a pre-P1 database: computer_screenshot was auto_allow (low).
    capability_governance._ensure_policy(kernel, "computer_screenshot", "low")
    rows = kernel.query_state("policy_events", capability="computer_screenshot", limit=1)
    assert rows[0]["risk_level"] == "low"

    events_before = kernel.read_events(aggregate_type="policy")

    # Re-seed from the (tightened) JSON.
    capability_governance.seed_from_json(kernel)

    # A PolicyUpdated event must have been emitted for the reconciled tool.
    updates = [
        e for e in kernel.read_events(aggregate_type="policy")
        if e.type == "PolicyUpdated"
        and e.payload.get("capability") == "computer_screenshot"
    ]
    assert len(updates) == 1, f"expected one PolicyUpdated, got {len(updates)}"
    assert updates[0].payload["risk_level"] == "high"

    # Projection now reflects the tightened risk.
    rows = kernel.query_state("policy_events", capability="computer_screenshot", limit=1)
    assert rows[0]["risk_level"] == "high"
    assert capability_governance.risk_for("computer_screenshot", kernel=kernel) == "high"

    # No duplicate PolicyUpdated on a second seed (risk already matches).
    count_before = len(kernel.read_events(aggregate_type="policy"))
    capability_governance.seed_from_json(kernel)
    count_after = len(kernel.read_events(aggregate_type="policy"))
    assert count_after == count_before, "second seed should not emit new events"
