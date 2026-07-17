"""Telemetry unit tests."""

from datetime import UTC, datetime, timedelta

from app.core.telemetry.telemetry import Telemetry
from app.core.runtime.kernel.kernel import Kernel
from app.store.database import Database


def test_get_memory_stats_via_sql_aggregate(tmp_path, monkeypatch):
    db = Database(db_path=str(tmp_path / "mem_stats.db"))
    k = Kernel(db=db)
    monkeypatch.setattr("app.core.runtime.kernel_instance.kernel", k)

    now = datetime.now(UTC)
    recent = (now - timedelta(days=1)).isoformat()
    old = (now - timedelta(days=10)).isoformat()
    with db.get_db() as conn:
        for i, (cat, created) in enumerate(
            [
                ("fact", recent),
                ("preference", recent),
                ("fact", old),
                ("unknown", recent),
            ]
        ):
            conn.execute(
                "INSERT INTO memories (id, content, category, confidence, created_at) "
                "VALUES (?, ?, ?, 0.9, ?)",
                (f"m{i}", f"c{i}", cat, created),
            )

    stats = Telemetry().get_memory_stats()
    assert stats["total_memories"] == 4
    assert stats["recent_7d"] == 3
    assert stats["categories"]["fact"] == 2
    assert stats["categories"]["preference"] == 1
    assert stats["categories"]["unknown"] == 1
    assert stats["capped"] is False


def test_llm_summary_by_model_aggregates_via_sql(tmp_path, monkeypatch):
    db = Database(db_path=str(tmp_path / "llm_agg.db"))
    k = Kernel(db=db)
    monkeypatch.setattr("app.core.runtime.kernel_instance.kernel", k)

    for i, payload in enumerate(
        [
            {
                "provider": "openai",
                "model": "gpt-4o",
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "cost": 0.01,
                "latency_ms": 100,
                "success": True,
            },
            {
                "provider": "openai",
                "model": "gpt-4o",
                "prompt_tokens": 20,
                "completion_tokens": 10,
                "cost": 0.02,
                "latency_ms": 200,
                "success": False,
            },
            {
                "provider": "deepseek",
                "model": "chat",
                "prompt_tokens": 5,
                "completion_tokens": 5,
                "cost": 0.001,
                "latency_ms": 50,
                "success": True,
            },
        ]
    ):
        k.emit_event(
            "LLMCallRecorded",
            "llm_call",
            f"llm_{i}",
            payload=payload,
            actor="test",
        )

    rows = Telemetry().get_llm_summary_by_model(days=7)
    assert len(rows) == 2
    top = rows[0]
    assert top["provider"] == "openai"
    assert top["total_calls"] == 2
    assert top["total_tokens"] == 45
    assert top["failed_calls"] == 1
    assert top["avg_latency_ms"] == 150
    assert top["capped"] is False

    summary = Telemetry().get_llm_summary(days=7)
    assert summary["total_calls"] == 3
    assert summary["failed_calls"] == 1
    assert summary["capped"] is False
    assert summary["sample_size"] == 3


def test_tool_summary_aggregates_via_sql(tmp_path, monkeypatch):
    db = Database(db_path=str(tmp_path / "tool_agg.db"))
    k = Kernel(db=db)
    monkeypatch.setattr("app.core.runtime.kernel_instance.kernel", k)

    k.emit_event(
        "CapabilityInvoked",
        "capability",
        "cap_1",
        payload={"name": "web_search", "success": True, "latency_ms": 100},
        actor="test",
    )
    k.emit_event(
        "CapabilityFailed",
        "capability",
        "cap_2",
        payload={"name": "web_search", "success": False, "latency_ms": 200, "error": "x"},
        actor="test",
    )
    k.emit_event(
        "CapabilityInvoked",
        "capability",
        "cap_3",
        payload={"name": "read_file", "success": True, "latency_ms": 50},
        actor="test",
    )

    rows = Telemetry().get_tool_summary(days=7)
    by_name = {r["tool_name"]: r for r in rows}
    assert by_name["web_search"]["total_calls"] == 2
    assert by_name["web_search"]["failed_calls"] == 1
    assert by_name["web_search"]["avg_latency_ms"] == 150
    assert by_name["read_file"]["total_calls"] == 1
    assert rows[0]["tool_name"] == "web_search"  # sorted by total_calls desc


def test_health_uses_counts_and_active_work_items(tmp_path, monkeypatch):
    db = Database(db_path=str(tmp_path / "health.db"))
    k = Kernel(db=db)
    monkeypatch.setattr("app.core.runtime.kernel_instance.kernel", k)
    monkeypatch.setattr("app.core.telemetry.telemetry.db", db)

    k.emit_event(
        "LLMCallRecorded",
        "llm_call",
        "llm_ok",
        payload={
            "provider": "t",
            "model": "m",
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "cost": 0,
            "latency_ms": 1,
            "success": True,
        },
        actor="test",
    )
    k.emit_event(
        "LLMCallRecorded",
        "llm_call",
        "llm_bad",
        payload={
            "provider": "t",
            "model": "m",
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "cost": 0,
            "latency_ms": 1,
            "success": False,
        },
        actor="test",
    )

    health = Telemetry().get_health()
    assert health["llm_failure_rate_24h"] == 0.5
    assert health["sample_size_llm_24h"] == 2
    assert health["capped"] is False
    assert "active_work_items" in health
    assert health["task_queue_length"] == health["active_work_items"]


def test_iso_created_at_window_excludes_same_day_morning(tmp_path, monkeypatch):
    """ISO T/+00:00 timestamps must not beat SQLite datetime() via string compare."""
    from app.store.telemetry_queries import select_telemetry_rows

    db = Database(db_path=str(tmp_path / "iso_window.db"))
    k = Kernel(db=db)
    monkeypatch.setattr("app.core.runtime.kernel_instance.kernel", k)

    # Same calendar day, morning — should be excluded from a "since 12 hours ago"
    # style window when cutoff is later today. Use since_days=0 with a patched
    # predicate by inserting an old ISO morning vs recent afternoon via SQL.
    with db.get_db() as conn:
        now = datetime.now(UTC)
        morning = now.replace(hour=1, minute=0, second=0, microsecond=0).isoformat()
        afternoon = now.replace(hour=18, minute=0, second=0, microsecond=0).isoformat()
        # Force "now" window of 1 day; morning today is inside, 10 days ago outside.
        old = (now - timedelta(days=10)).isoformat()
        for i, created in enumerate([morning, afternoon, old]):
            conn.execute(
                "INSERT INTO llm_calls "
                "(id, provider, model, prompt_tokens, completion_tokens, "
                "latency_ms, cost, success, created_at) "
                "VALUES (?, 'p', 'm', 1, 1, 1, 0, 1, ?)",
                (f"iso_{i}", created),
            )

    rows = select_telemetry_rows(db, "llm_calls", {"since_days": 7, "limit": 50})
    ids = {r["id"] for r in rows}
    assert "iso_0" in ids  # morning today still within 7d
    assert "iso_1" in ids
    assert "iso_2" not in ids

    # Same-day ordering sanity: normalize must not rank morning after afternoon
    # purely because 'T' > ' ' against datetime('now').
    from app.store.telemetry_queries import created_at_since_sql

    pred, params = created_at_since_sql(0)
    assert pred is not None
    assert "replace(substr(created_at, 1, 19), 'T', ' ')" in pred
    assert params == ["-0 days"]
