"""Event payload schema_version stamping + CI contract."""

from __future__ import annotations

import json

import pytest

from app.core.runtime.kernel.constants import (
    EVENT_SCHEMA_VERSION_DEFAULT,
    EVENT_WORK_ITEM_CREATED,
    PAYLOAD_SCHEMA_VERSION_KEY,
    declared_event_types,
    event_schema_version,
    stamp_event_payload,
)
from app.core.runtime.kernel.kernel import Kernel
from app.store.database import Database


def test_declared_event_types_match_constants_count():
    types = declared_event_types()
    assert len(types) == 46
    assert EVENT_WORK_ITEM_CREATED in types
    assert "schema_version" not in types


def test_declared_event_types_match_ci_parser():
    """Runtime globals scan and CI regex must stay in lockstep."""
    from scripts import check_event_schema as mod

    assert declared_event_types() == frozenset(mod.parse_declared_event_types())


def test_stamp_event_payload_sets_version():
    stamped = stamp_event_payload(EVENT_WORK_ITEM_CREATED, {"title": "x"})
    assert stamped["title"] == "x"
    assert stamped[PAYLOAD_SCHEMA_VERSION_KEY] == EVENT_SCHEMA_VERSION_DEFAULT
    assert event_schema_version(EVENT_WORK_ITEM_CREATED) == 1


def test_emit_event_stamps_schema_version(tmp_path):
    k = Kernel(db=Database(str(tmp_path / "sv.db")))
    ev = k.emit_event(
        EVENT_WORK_ITEM_CREATED,
        "work_item",
        "wi_sv_1",
        payload={"title": "stamp-me", "work_type": "task", "status": "pending"},
        actor="test",
    )
    assert ev.payload[PAYLOAD_SCHEMA_VERSION_KEY] == 1
    rows = k.read_events(id=ev.id, limit=1)
    assert rows[0].payload[PAYLOAD_SCHEMA_VERSION_KEY] == 1


def test_check_event_schema_script_passes(tmp_path, monkeypatch):
    from scripts import check_event_schema as mod

    # Ensure baseline exists (recorded for this repo).
    assert mod.BASELINE_PATH.exists()
    assert mod.check(verbose=False) == 0


def test_check_event_schema_detects_drift(monkeypatch):
    from scripts import check_event_schema as mod

    monkeypatch.setattr(
        mod,
        "compute_versions",
        lambda: {"WorkItemCreated": 1, "OnlyInCurrent": 1},
    )
    monkeypatch.setattr(
        mod,
        "load_baseline",
        lambda: {
            "versions": {"WorkItemCreated": 1, "OnlyInBaseline": 1},
        },
    )
    assert mod.check(verbose=False) == 1


def test_record_rejects_downgrade(monkeypatch, tmp_path):
    from scripts import check_event_schema as mod

    baseline_file = tmp_path / "event_schema_versions.json"
    monkeypatch.setattr(mod, "BASELINE_PATH", baseline_file)
    monkeypatch.setattr(
        mod,
        "load_baseline",
        lambda: {"versions": {"WorkItemCreated": 2}},
    )
    monkeypatch.setattr(
        mod,
        "compute_versions",
        lambda: {"WorkItemCreated": 1},
    )
    assert mod.record_baseline({"WorkItemCreated": 1}, verbose=False) == 1
    assert not baseline_file.exists()


def test_record_allow_downgrade(monkeypatch, tmp_path):
    from scripts import check_event_schema as mod

    baseline_file = tmp_path / "event_schema_versions.json"
    monkeypatch.setattr(mod, "BASELINE_PATH", baseline_file)
    monkeypatch.setattr(
        mod,
        "load_baseline",
        lambda: {"versions": {"WorkItemCreated": 2}},
    )
    assert (
        mod.record_baseline(
            {"WorkItemCreated": 1},
            allow_downgrade=True,
            verbose=False,
        )
        == 0
    )
    saved = json.loads(baseline_file.read_text(encoding="utf-8"))
    assert saved["versions"]["WorkItemCreated"] == 1
