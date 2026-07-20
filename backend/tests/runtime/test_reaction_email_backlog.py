"""Tests for the email_backlog_50 Reaction.

Previously the handler unconditionally called ``push_notification`` on every
``evaluate_cycle`` (~10s), producing a spurious "收件箱整理建议" notification
right after startup regardless of inbox size, plus a redundant WebSocket
broadcast every cycle. These tests pin the corrected contract:

  1. < 50 pending emails → no notification.
  2. >= 50 pending emails → exactly one notification.
  3. Repeated evaluate_cycle does not create a duplicate nor re-broadcast.
"""

import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND_ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT / "backend"))

import pytest

from app.core.runtime.kernel.kernel import Kernel
from app.store.database import Database

_THRESHOLD = 50


def _seed_pending_emails(kernel: Kernel, n: int) -> None:
    for i in range(n):
        kernel.emit_event(
            "InboxEmailRecorded", "inbox_email", f"m_{i:04d}",
            payload={"sender": f"s{i}@x", "subject": f"s{i}"},
            actor="inbox",
        )


def _suggestion_rows(kernel: Kernel) -> list[dict]:
    return kernel.query_state(
        "notifications",
        type="suggestion", title="收件箱整理建议", limit=10,
    )


@pytest.fixture
def kernel_with_reaction(tmp_path, monkeypatch):
    """Isolated kernel with builtin_reactions registered."""
    db = Database(db_path=str(tmp_path / "react.db"))
    k = Kernel(db=db)

    monkeypatch.setattr("app.core.runtime.kernel_instance.kernel", k)
    monkeypatch.setattr("app.store.database.db", db)

    from app.core.runtime.reaction_registry import reset_reactions
    reset_reactions()
    # builtin_reactions registers @reaction decorators at import time, so a
    # plain re-import is a no-op after the first test. Reload to re-run the
    # module body and re-register handlers against the freshly-reset registry.
    import importlib

    import app.core.runtime.builtin_reactions as _br
    importlib.reload(_br)

    yield k
    reset_reactions()


def test_below_threshold_no_notification(kernel_with_reaction):
    """< 50 pending emails → evaluate_cycle produces no suggestion notification."""
    k = kernel_with_reaction
    _seed_pending_emails(k, _THRESHOLD - 1)

    from app.core.runtime.reaction_registry import get_reaction_registry
    get_reaction_registry().evaluate_cycle(k)

    assert _suggestion_rows(k) == [], "expected no notification below threshold"


def test_at_threshold_single_notification(kernel_with_reaction):
    """>= 50 pending emails → evaluate_cycle produces exactly one notification."""
    k = kernel_with_reaction
    _seed_pending_emails(k, _THRESHOLD)

    from app.core.runtime.reaction_registry import get_reaction_registry
    get_reaction_registry().evaluate_cycle(k)

    rows = _suggestion_rows(k)
    assert len(rows) == 1, f"expected exactly one notification, got {len(rows)}"
    assert "50" in rows[0].get("content", "")


def test_repeated_cycle_does_not_duplicate(kernel_with_reaction):
    """Running evaluate_cycle twice must not create a second notification."""
    k = kernel_with_reaction
    _seed_pending_emails(k, _THRESHOLD + 5)

    from app.core.runtime.reaction_registry import get_reaction_registry
    reg = get_reaction_registry()
    reg.evaluate_cycle(k)
    reg.evaluate_cycle(k)

    rows = _suggestion_rows(k)
    assert len(rows) == 1, f"expected no duplicate on repeat, got {len(rows)}"
