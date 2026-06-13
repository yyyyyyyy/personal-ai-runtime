"""Tests for dogfood friction log."""

import pytest

from app.core.runtime.kernel import Kernel
from app.product import friction_log
from app.store.database import Database


def _make_kernel(tmp_path):
    db = Database(db_path=str(tmp_path / "friction.db"))
    return Kernel(db=db)


@pytest.fixture
def kernel(tmp_path, monkeypatch):
    k = _make_kernel(tmp_path)
    monkeypatch.setattr(friction_log, "kernel", k)
    return k


def test_log_list_resolve(kernel):
    entry = friction_log.log_friction(
        "审批弹窗文案看不懂",
        area="tools",
        severity="high",
    )
    assert entry["status"] == "open"
    assert entry["area"] == "tools"

    items = friction_log.list_friction()
    assert len(items) == 1
    assert items[0]["note"] == "审批弹窗文案看不懂"

    resolved = friction_log.resolve_friction(entry["id"])
    assert resolved is not None
    assert resolved["status"] == "resolved"
    assert resolved["resolved_at"]

    assert friction_log.list_friction(status="open") == []
    assert len(friction_log.list_friction(status="resolved")) == 1


def test_log_rejects_empty_note(kernel):
    with pytest.raises(ValueError, match="note"):
        friction_log.log_friction("   ")


def test_log_rejects_invalid_area(kernel):
    with pytest.raises(ValueError, match="area"):
        friction_log.log_friction("x", area="invalid")


def test_friction_stats(kernel):
    friction_log.log_friction("inbox slow", area="inbox", severity="medium")
    friction_log.log_friction("chat lag", area="chat", severity="low")

    stats = friction_log.friction_stats(since_days=7)
    assert stats["logged_7d"] == 2
    assert stats["open_total"] == 2
    assert stats["by_area_7d"]["inbox"] == 1
    assert stats["by_area_7d"]["chat"] == 1
