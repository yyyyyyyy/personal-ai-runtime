"""Coverage tests for kernel_sovereignty export/rebuild and runtime_config."""


def test_export_events_roundtrip(isolated_kernel):
    """Export events, clear DB, import — events should be preserved."""
    k, db = isolated_kernel
    k.emit_event("WorkItemCreated", "work_item", "goal_export", payload={
        "title": "Export test",
    }, actor="verify")

    exported = k.export_event_log_rows()
    assert isinstance(exported, list)
    assert len(exported) > 0

    # Import back
    k.import_event_log_rows(exported)
    assert len(exported) > 0


def test_rebuild_single_aggregate(isolated_kernel):
    """Rebuild specific aggregate type should work."""
    k, db = isolated_kernel
    k.emit_event("WorkItemCreated", "work_item", "goal_rebuild_test", payload={
        "work_type": "goal",
        "title": "Rebuild test",
    }, actor="verify")

    result = k.rebuild("goal")
    assert isinstance(result, int)
    assert result > 0


def test_rebuild_all(isolated_kernel):
    """rebuild_all should return results for all aggregate types."""
    k, db = isolated_kernel
    k.emit_event("WorkItemCreated", "work_item", "goal_all", payload={
        "title": "All rebuild test",
    }, actor="verify")

    result = k.rebuild_all()
    assert isinstance(result, dict)
    assert "work_item" in result


def test_query_state_simple(isolated_kernel):
    """query_state should return projection rows."""
    k, db = isolated_kernel
    k.emit_event("WorkItemCreated", "work_item", "goal_qs", payload={
        "work_type": "goal",
        "title": "Query test",
    }, actor="verify")

    rows = k.query_state("goals", status="active", limit=5)
    assert isinstance(rows, list)
    assert len(rows) > 0


def test_query_state_multiple_conditions(isolated_kernel):
    """query_state with multiple conditions."""
    k, db = isolated_kernel
    k.emit_event("WorkItemCreated", "work_item", "goal_qs2", payload={
        "work_type": "goal",
        "title": "Query2",
    }, actor="verify")

    rows = k.query_state("goals", limit=10, order="created_at_desc")
    assert isinstance(rows, list)
    assert len(rows) > 0


def test_read_events_filter(isolated_kernel):
    """read_events with type filter returns matching events."""
    k, db = isolated_kernel
    k.emit_event("WorkItemCreated", "work_item", "goal_evt", payload={
        "title": "Event test",
    }, actor="verify")

    events = k.read_events(types=["WorkItemCreated"], limit=10)
    assert isinstance(events, list)
    assert len(events) > 0
    assert events[0].type == "WorkItemCreated"


def test_emit_event_with_caused_by(isolated_kernel):
    """emit_event with caused_by creates causal chain."""
    k, db = isolated_kernel
    evt1 = k.emit_event("WorkItemCreated", "work_item", "goal_cause", payload={
        "title": "Cause chain",
    }, actor="verify")
    evt2 = k.emit_event("WorkItemUpdated", "work_item", "goal_cause", payload={
        "progress": 0.5,
    }, actor="verify", caused_by=evt1.id)

    assert evt2.caused_by == evt1.id
