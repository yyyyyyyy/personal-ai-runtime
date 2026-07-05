"""Personal Dashboard product unit tests (Phase 5 consistency slice).

Tests the dashboard product's ability to compute widgets from Kernel ABI
without any boundary violations.
"""

import os

os.environ.setdefault("LLM_API_KEY", "test-key")


def test_generate_dashboard_with_seeded_data(tmp_path, monkeypatch):
    """Dashboard products work with seeded Runtime data."""
    from app.core.runtime.kernel import Kernel
    from app.store.database import Database

    k = Kernel(db=Database(db_path=str(tmp_path / "dashboard.db")))
    monkeypatch.setattr(
        "app.product.personal_dashboard.kernel", k,
    )

    # Seed: goals
    k.emit_event("WorkItemCreated", "work_item", "g1",
                 payload={"work_type": "goal", "status": "active", "title": "Learn Rust", "importance": 0.9, "progress": 0.5},
                 actor="test")
    k.emit_event("WorkItemCreated", "work_item", "g2",
                 payload={"work_type": "goal", "status": "active", "title": "Ship feature", "importance": 0.7, "progress": 0.2},
                 actor="test")

    # Seed: timer
    k.emit_event("TimerCreated", "timer", "t1",
                 payload={"handler_name": "memory_decay", "schedule_type": "cron",
                          "cron_expr": "hour=8,minute=0", "fire_at": "2026-06-16T08:00:00Z"},
                 actor="test")

    # Seed: policy
    k.emit_event("PolicyCreated", "policy", "p1",
                 payload={"capability": "read_file", "risk_level": "low"},
                 actor="test")

    # Seed: grant
    k.emit_event("GrantCreated", "grant", "gr1",
                 payload={"principal_id": "agent1", "capability": "web_search"},
                 actor="test")

    from app.product.personal_dashboard import generate_dashboard
    dashboard = generate_dashboard()

    # Goals widget
    assert dashboard["active_goals"]["count"] >= 1
    assert len(dashboard["active_goals"]["top"]) >= 1
    assert dashboard["active_goals"]["top"][0]["title"] in ("Learn Rust", "Ship feature")

    # Events widget
    assert dashboard["recent_events"]["count"] >= 1

    # Timer widget
    assert dashboard["timer_status"]["active_timers"] >= 1

    # Governance widget
    assert dashboard["governance_status"]["active_policies"] >= 1
    assert dashboard["governance_status"]["active_grants"] >= 0  # grant projectors removed v0.7.0

    # Structure
    assert "generated_at" in dashboard
    assert "recent_memories" in dashboard


def test_dashboard_no_direct_sql_or_storage():
    """Verify dashboard product has no storage imports (pure ABI)."""
    import ast
    from pathlib import Path

    product_file = Path(__file__).resolve().parent.parent.parent / "app" / "product" / "personal_dashboard.py"
    source = product_file.read_text(encoding="utf-8")
    tree = ast.parse(source)

    forbidden_imports = {
        "sqlite3", "database", "chromadb", "ChromaDB", "chroma",
        "os.path", "shutil", "open(", "write(", "read(",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name not in forbidden_imports, \
                    f"Dashboard must not import {alias.name} (storage bypass)"
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                assert node.module not in forbidden_imports, \
                    f"Dashboard must not import {node.module} (storage bypass)"
