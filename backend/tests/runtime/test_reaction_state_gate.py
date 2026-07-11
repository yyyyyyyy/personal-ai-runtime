"""Tests for ReactionWhen state gating in evaluate_cycle (v0.12)."""

import os
import sys
from pathlib import Path

os.environ.setdefault("LLM_API_KEY", "test-key")

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND_ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT / "backend"))

import pytest

from app.core.runtime.kernel.kernel import Kernel
from app.core.runtime.reaction_registry import (
    Reaction,
    ReactionWhen,
    get_reaction_registry,
    reset_reactions,
)
from app.store.database import Database


@pytest.fixture
def kernel(tmp_path, monkeypatch):
    db = Database(db_path=str(tmp_path / "gate.db"))
    k = Kernel(db=db)
    monkeypatch.setattr("app.core.runtime.kernel_instance.kernel", k)
    monkeypatch.setattr("app.store.database.db", db)
    reset_reactions()
    yield k
    reset_reactions()


def test_state_gate_skips_handler_below_threshold(kernel):
    """Handler must not run when state_selector count is below count_gte."""
    calls: list[str] = []

    def handler(kern=None):
        calls.append("ran")

    get_reaction_registry().register(Reaction(
        name="gated",
        when=ReactionWhen(
            every_cycle=True,
            state_selector="inbox_emails",
            state_filters={"status": "pending"},
            count_gte=3,
        ),
        handler=handler,
    ))

    # Seed only 2 pending emails
    for i in range(2):
        kernel.emit_event(
            "InboxEmailRecorded", "inbox_email", f"m_{i}",
            payload={"sender": f"s{i}@x", "subject": f"s{i}"},
            actor="inbox",
        )

    fired = get_reaction_registry().evaluate_cycle(kernel)
    assert fired == 0
    assert calls == []


def test_state_gate_invokes_handler_at_threshold(kernel):
    calls: list[str] = []

    def handler(kern=None):
        calls.append("ran")

    get_reaction_registry().register(Reaction(
        name="gated_ok",
        when=ReactionWhen(
            every_cycle=True,
            state_selector="inbox_emails",
            state_filters={"status": "pending"},
            count_gte=2,
        ),
        handler=handler,
    ))

    for i in range(2):
        kernel.emit_event(
            "InboxEmailRecorded", "inbox_email", f"n_{i}",
            payload={"sender": f"s{i}@x", "subject": f"s{i}"},
            actor="inbox",
        )

    fired = get_reaction_registry().evaluate_cycle(kernel)
    assert fired == 1
    assert calls == ["ran"]


def test_every_cycle_without_state_gate_always_invokes(kernel):
    calls: list[str] = []

    def handler(kern=None):
        calls.append("ran")

    get_reaction_registry().register(Reaction(
        name="always",
        when=ReactionWhen(every_cycle=True),
        handler=handler,
    ))

    fired = get_reaction_registry().evaluate_cycle(kernel)
    assert fired == 1
    assert calls == ["ran"]


def test_list_reactions_exposes_gated_by(kernel):
    get_reaction_registry().register(Reaction(
        name="meta",
        when=ReactionWhen(
            every_cycle=True,
            state_selector="inbox_emails",
            count_gte=10,
        ),
        handler=lambda kern=None: None,
    ))
    rows = get_reaction_registry().list_reactions()
    meta = next(r for r in rows if r["name"] == "meta")
    assert meta["gated_by"] == "state"
    assert meta["state_selector"] == "inbox_emails"
    assert meta["every_cycle"] is True
