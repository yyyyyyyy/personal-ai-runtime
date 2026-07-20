"""Tests for notification related-id handling and event-sourced writes."""

from app.product.notifications import create_notification


def test_create_notification_stores_related_id_in_column(product_kernel):
    k = product_kernel

    first = create_notification("alert", "提醒 A", "old content", kernel=k)
    assert first["content"] == "old content"
    assert first.get("related_id") is None

    second = create_notification(
        "alert",
        "提醒 A",
        "new content",
        related_id="entity-001",
        related_type="goal",
        kernel=k,
    )
    assert second["id"] == first["id"]
    assert second["content"] == "old content"
    assert second["related_id"] == "entity-001"

    rows = k.query_state("notifications", related_id="entity-001")
    assert len(rows) == 1
    assert rows[0]["related_id"] == "entity-001"
    assert not rows[0]["content"].startswith("@related:")


def test_create_notification_related_id_on_create(product_kernel):
    k = product_kernel
    n = create_notification(
        "goal_stagnant",
        "目标停滞: X",
        "目标已 3 天未更新",
        related_id="goal-1",
        related_type="goal",
        kernel=k,
    )
    assert n["content"] == "目标已 3 天未更新"
    rows = k.query_state("notifications", related_id="goal-1")
    assert len(rows) == 1
    assert rows[0]["related_id"] == "goal-1"


def test_notification_rebuild(product_kernel):
    k = product_kernel
    create_notification("alert", "Test alert", "Body", related_id="r1", kernel=k)
    before = k.query_state("notifications")
    k.rebuild("notification")
    after = k.query_state("notifications")
    assert before == after
    assert len(after) == 1
    assert after[0]["read"] == 0
    assert after[0]["related_id"] == "r1"

    k.emit_event("NotificationRead", "notification", after[0]["id"], payload={}, actor="test")
    k.rebuild("notification")
    read_rows = k.query_state("notifications")
    assert read_rows[0]["read"] == 1
