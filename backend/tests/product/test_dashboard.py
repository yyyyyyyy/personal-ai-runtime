"""Personal Dashboard product unit tests — widgets from Kernel ABI."""


def test_generate_dashboard_with_seeded_data(product_kernel):
    """Dashboard widgets reflect seeded Runtime data."""
    k = product_kernel

    k.emit_event(
        "WorkItemCreated",
        "work_item",
        "g1",
        payload={
            "work_type": "goal",
            "status": "active",
            "title": "Learn Rust",
            "importance": 0.9,
            "progress": 0.5,
        },
        actor="test",
    )
    k.emit_event(
        "WorkItemCreated",
        "work_item",
        "g2",
        payload={
            "work_type": "goal",
            "status": "active",
            "title": "Ship feature",
            "importance": 0.7,
            "progress": 0.2,
        },
        actor="test",
    )
    k.emit_event(
        "TimerCreated",
        "timer",
        "t1",
        payload={
            "handler_name": "memory_decay",
            "schedule_type": "cron",
            "cron_expr": "hour=8,minute=0",
            "fire_at": "2026-06-16T08:00:00Z",
        },
        actor="test",
    )
    k.emit_event(
        "PolicyCreated",
        "policy",
        "p1",
        payload={"capability": "read_file", "risk_level": "low"},
        actor="test",
    )

    from app.product.personal_dashboard import generate_dashboard

    dashboard = generate_dashboard()

    assert dashboard["active_goals"]["count"] == 2
    top_titles = [g["title"] for g in dashboard["active_goals"]["top"]]
    assert top_titles[0] == "Learn Rust"
    assert "Ship feature" in top_titles

    assert dashboard["recent_events"]["count"] >= 1
    assert dashboard["timer_status"]["active_timers"] >= 1
    assert dashboard["governance_status"]["active_policies"] >= 1
    assert isinstance(dashboard["governance_status"]["active_grants"], int)
    assert "generated_at" in dashboard
    assert "recent_memories" in dashboard

    sovereignty = dashboard["data_sovereignty"]
    for key in (
        "total_events",
        "total_memories",
        "memories_self_report",
        "memories_claim",
        "total_goals",
        "goals_active",
        "goals_completed",
        "total_conversations",
        "total_messages",
        "data_location",
        "last_belief_reflection",
        "export_supported",
    ):
        assert key in sovereignty
    for key in (
        "total_events",
        "total_memories",
        "total_goals",
        "total_conversations",
        "total_messages",
    ):
        assert isinstance(sovereignty[key], int)
        assert sovereignty[key] >= 0
    assert sovereignty["export_supported"] is True
    assert "本地" in sovereignty["data_location"]
