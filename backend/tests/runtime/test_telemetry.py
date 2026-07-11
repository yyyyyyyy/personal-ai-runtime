"""Telemetry unit tests."""

from datetime import UTC, datetime, timedelta

from app.core.telemetry.telemetry import telemetry


def test_get_memory_stats_compares_naive_and_aware_created_at(monkeypatch):
    recent_naive = (datetime.now(UTC) - timedelta(days=1)).replace(tzinfo=None).isoformat()
    recent_aware = datetime.now(UTC).isoformat()
    old_naive = (datetime.now(UTC) - timedelta(days=10)).replace(tzinfo=None).isoformat()

    monkeypatch.setattr(
        "app.core.telemetry.telemetry.read_ports.query_memories",
        lambda **kwargs: [
            {"created_at": recent_naive, "category": "fact"},
            {"created_at": recent_aware, "category": "preference"},
            {"created_at": old_naive, "category": "fact"},
            {"category": "unknown"},
        ],
    )

    stats = telemetry.get_memory_stats()

    assert stats["total_memories"] == 4
    assert stats["recent_7d"] == 2
    assert stats["categories"]["fact"] == 2


def test_llm_summary_by_model_aggregates_via_query_state(monkeypatch):
    monkeypatch.setattr(
        "app.core.telemetry.telemetry.read_ports.query_llm_calls",
        lambda **kwargs: [
            {
                "provider": "openai",
                "model": "gpt-4o",
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "cost": 0.01,
                "latency_ms": 100,
                "success": 1,
            },
            {
                "provider": "openai",
                "model": "gpt-4o",
                "prompt_tokens": 20,
                "completion_tokens": 10,
                "cost": 0.02,
                "latency_ms": 200,
                "success": 0,
            },
            {
                "provider": "deepseek",
                "model": "chat",
                "prompt_tokens": 5,
                "completion_tokens": 5,
                "cost": 0.001,
                "latency_ms": 50,
                "success": 1,
            },
        ],
    )
    rows = telemetry.get_llm_summary_by_model(days=7)
    assert len(rows) == 2
    top = rows[0]
    assert top["provider"] == "openai"
    assert top["total_calls"] == 2
    assert top["total_tokens"] == 45
    assert top["failed_calls"] == 1
    assert top["avg_latency_ms"] == 150


def test_tool_summary_aggregates_via_query_state(monkeypatch):
    monkeypatch.setattr(
        "app.core.telemetry.telemetry.read_ports.query_tool_calls",
        lambda **kwargs: [
            {"tool_name": "web_search", "success": 1, "latency_ms": 100},
            {"tool_name": "web_search", "success": 0, "latency_ms": 200},
            {"tool_name": "read_file", "success": 1, "latency_ms": 50},
        ],
    )
    rows = telemetry.get_tool_summary(days=7)
    by_name = {r["tool_name"]: r for r in rows}
    assert by_name["web_search"]["total_calls"] == 2
    assert by_name["web_search"]["failed_calls"] == 1
    assert by_name["web_search"]["avg_latency_ms"] == 150
    assert by_name["read_file"]["total_calls"] == 1
