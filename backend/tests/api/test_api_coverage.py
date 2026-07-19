"""API smoke tests for high-gap endpoints.

Targets the endpoints that contributed most to the <50% API coverage gate.
Uses TestClient with a fresh isolated DB so no real LLM / external services
are needed.
"""

import importlib

import pytest
from fastapi.testclient import TestClient


async def _noop_start() -> int:
    return 0


async def _noop_stop() -> None:
    return None


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "api.db"))
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("VECTOR_DIR", str(tmp_path / "vectors"))
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MCP_EXTERNAL_ENABLED", "false")
    monkeypatch.setenv("AUTH_TOKEN", "")

    monkeypatch.setattr("app.core.harness.mcp_lifecycle.start_mcp_mesh", _noop_start)
    monkeypatch.setattr("app.core.harness.mcp_lifecycle.stop_mcp_mesh", _noop_stop)

    import app.api.system
    import app.config
    import app.main
    app.config.reset_settings()
    importlib.reload(app.api.system)
    importlib.reload(app.main)

    yield TestClient(app.main.app)


# ── Memory API ────────────────────────────────────────────────────────────


class TestMemoryAPI:
    def test_list_returns_list(self, client):
        resp = client.get("/api/memory/memories")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_create_and_list(self, client):
        resp = client.post("/api/memory/memories", json={"content": "likes python", "category": "fact"})
        assert resp.status_code == 200
        mid = resp.json()["id"]

        resp = client.get("/api/memory/memories")
        assert any(m["id"] == mid for m in resp.json())

    def test_create_empty_rejected(self, client):
        resp = client.post("/api/memory/memories", json={"content": ""})
        assert resp.status_code == 400

    def test_delete_not_found(self, client):
        resp = client.delete("/api/memory/memories/nonexistent")
        assert resp.status_code == 404

    def test_update_not_found(self, client):
        resp = client.put("/api/memory/memories/nonexistent", json={"content": "x"})
        assert resp.status_code == 404

    def test_ratify_not_found(self, client):
        resp = client.post("/api/memory/memories/nonexistent/ratify")
        assert resp.status_code == 404

    def test_reject_not_found(self, client):
        resp = client.post("/api/memory/memories/nonexistent/reject")
        assert resp.status_code == 404

    def test_contest_not_found(self, client):
        resp = client.post("/api/memory/memories/nonexistent/contest")
        assert resp.status_code == 404

    def test_search_empty_query_rejected(self, client):
        resp = client.get("/api/memory/memories/search?q=")
        assert resp.status_code == 400

    def test_portrait_returns_structure(self, client):
        resp = client.get("/api/memory/portrait")
        assert resp.status_code == 200
        data = resp.json()
        assert "profile" in data
        assert "habits" in data
        assert "goals" in data

    def test_graph_returns_structure(self, client):
        resp = client.get("/api/memory/graph")
        assert resp.status_code == 200
        data = resp.json()
        assert "nodes" in data and "edges" in data

    def test_memories_grouped(self, client):
        resp = client.get("/api/memory/memories/grouped")
        assert resp.status_code == 200
        assert "memories" in resp.json()


# ── Goals API ─────────────────────────────────────────────────────────────


class TestGoalsViaWorkItemsAPI:
    def test_list_empty(self, client):
        resp = client.get("/api/work-items/?work_type=goal")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_create_goal_minimal(self, client):
        resp = client.post("/api/work-items/", json={"title": "Learn Rust", "work_type": "goal"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "active"
        assert data["work_type"] == "goal"

    def test_create_goal_with_all_fields(self, client):
        resp = client.post("/api/work-items/", json={
            "title": "Learn Go",
            "work_type": "goal",
            "description": "Master Go",
            "importance": 0.8,
            "urgency": 0.6,
            "deadline": "2026-12-31",
        })
        assert resp.status_code == 200
        assert resp.json()["title"] == "Learn Go"

    def test_create_empty_title(self, client):
        resp = client.post("/api/work-items/", json={"title": "", "work_type": "goal"})
        assert resp.status_code == 400

    def test_get_not_found(self, client):
        resp = client.get("/api/work-items/nonexistent")
        assert resp.status_code == 404

    def test_get_goal_with_actions(self, client):
        resp = client.post("/api/work-items/", json={"title": "G", "work_type": "goal"})
        gid = resp.json()["id"]
        client.post("/api/work-items/", json={
            "title": "Step 1", "work_type": "action", "parent_goal_id": gid,
        })
        resp = client.get(f"/api/work-items/{gid}?include=actions,events")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["actions"]) == 1
        assert "events" in body

    def test_delete_not_found(self, client):
        resp = client.delete("/api/work-items/nonexistent")
        assert resp.status_code == 404

    def test_delete_goal_with_items(self, client):
        resp = client.post("/api/work-items/", json={"title": "G", "work_type": "goal"})
        gid = resp.json()["id"]
        client.post("/api/work-items/", json={
            "title": "Step 1", "work_type": "action", "parent_goal_id": gid,
        })
        resp = client.delete(f"/api/work-items/{gid}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        assert client.get(f"/api/work-items/{gid}").status_code == 404

    def test_update_goal_fields(self, client):
        resp = client.post("/api/work-items/", json={"title": "Update test", "work_type": "goal"})
        gid = resp.json()["id"]
        resp = client.patch(f"/api/work-items/{gid}", json={
            "title": "Updated title",
            "importance": 0.9,
            "status": "active",
        })
        assert resp.status_code == 200
        assert resp.json()["title"] == "Updated title"

    def test_update_goal_no_changes(self, client):
        resp = client.post("/api/work-items/", json={"title": "NoOp", "work_type": "goal"})
        gid = resp.json()["id"]
        resp = client.patch(f"/api/work-items/{gid}", json={})
        assert resp.status_code == 400

    def test_update_goal_invalid_status(self, client):
        resp = client.post("/api/work-items/", json={"title": "G", "work_type": "goal"})
        gid = resp.json()["id"]
        resp = client.patch(f"/api/work-items/{gid}", json={"status": "invalid"})
        assert resp.status_code == 400

    def test_update_goal_invalid_importance(self, client):
        resp = client.post("/api/work-items/", json={"title": "G", "work_type": "goal"})
        gid = resp.json()["id"]
        resp = client.patch(f"/api/work-items/{gid}", json={"importance": 1.5})
        assert resp.status_code == 400

    def test_mark_goal_completed(self, client):
        resp = client.post("/api/work-items/", json={"title": "Complete me", "work_type": "goal"})
        gid = resp.json()["id"]
        resp = client.patch(f"/api/work-items/{gid}", json={"status": "completed"})
        assert resp.status_code == 200

    def test_create_action(self, client):
        resp = client.post("/api/work-items/", json={"title": "G", "work_type": "goal"})
        gid = resp.json()["id"]
        resp = client.post("/api/work-items/", json={
            "title": "Do thing", "work_type": "action", "parent_goal_id": gid,
        })
        assert resp.status_code == 200
        assert resp.json()["title"] == "Do thing"
        assert resp.json()["parent_goal_id"] == gid

    def test_create_action_empty_title(self, client):
        resp = client.post("/api/work-items/", json={"title": "G", "work_type": "goal"})
        gid = resp.json()["id"]
        resp = client.post("/api/work-items/", json={
            "title": "", "work_type": "action", "parent_goal_id": gid,
        })
        assert resp.status_code == 400

    def test_create_action_goal_not_found(self, client):
        resp = client.post("/api/work-items/", json={
            "title": "Step", "work_type": "action", "parent_goal_id": "missing",
        })
        assert resp.status_code == 404

    def test_update_action_status(self, client):
        resp = client.post("/api/work-items/", json={"title": "G", "work_type": "goal"})
        gid = resp.json()["id"]
        resp = client.post("/api/work-items/", json={
            "title": "Step", "work_type": "action", "parent_goal_id": gid,
        })
        aid = resp.json()["id"]
        resp = client.patch(f"/api/work-items/{aid}", json={"status": "completed"})
        assert resp.status_code == 200

    def test_update_action_not_found(self, client):
        resp = client.patch("/api/work-items/nonexistent", json={"status": "completed"})
        assert resp.status_code == 404

    def test_delete_action(self, client):
        resp = client.post("/api/work-items/", json={"title": "G", "work_type": "goal"})
        gid = resp.json()["id"]
        resp = client.post("/api/work-items/", json={
            "title": "Del me", "work_type": "action", "parent_goal_id": gid,
        })
        aid = resp.json()["id"]
        resp = client.delete(f"/api/work-items/{aid}")
        assert resp.status_code == 200

    def test_delete_action_not_found(self, client):
        resp = client.delete("/api/work-items/nonexistent")
        assert resp.status_code == 404


# ── Approvals API ─────────────────────────────────────────────────────────


class TestApprovalsAPI:
    def test_list_returns_data(self, client):
        resp = client.get("/api/approvals/")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_list_pending_only(self, client):
        resp = client.get("/api/approvals/?pending_only=true")
        assert resp.status_code == 200

    def test_list_enriched(self, client):
        resp = client.get("/api/approvals/?pending_only=true&enriched=true")
        assert resp.status_code == 200

    def test_get_approval_not_found(self, client):
        resp = client.get("/api/approvals/nonexistent")
        assert resp.status_code == 404

    def test_approve_not_found(self, client):
        resp = client.post("/api/approvals/nonexistent/approve")
        assert resp.status_code == 404

    def test_reject_not_found(self, client):
        resp = client.post("/api/approvals/nonexistent/reject")
        assert resp.status_code == 404


# ── System API ────────────────────────────────────────────────────────────


class TestSystemAPI:
    def test_health(self, client):
        resp = client.get("/api/system/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_live(self, client):
        resp = client.get("/api/system/live")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data

    def test_root(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "running" in resp.json()["message"].lower()

    def test_info(self, client):
        resp = client.get("/api/system/info")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)

    def test_llm_providers(self, client):
        resp = client.get("/api/system/llm-providers")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, (list, dict))


# ── Tasks API ─────────────────────────────────────────────────────────────


class TestTasksViaWorkItemsAPI:
    def test_list(self, client):
        resp = client.get("/api/work-items/?work_type=task")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_create_task_valid(self, client):
        resp = client.post("/api/work-items/", json={"name": "Deploy app", "priority": 2})
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Deploy app"
        assert "id" in data

    def test_create_task_empty_name(self, client):
        resp = client.post("/api/work-items/", json={"name": ""})
        assert resp.status_code == 400

    def test_create_task_uses_title_fallback(self, client):
        resp = client.post("/api/work-items/", json={"title": "Via Title"})
        assert resp.status_code == 200
        assert resp.json()["title"] == "Via Title"

    def test_get_task_not_found(self, client):
        resp = client.get("/api/work-items/nonexistent")
        assert resp.status_code == 404

    def test_get_task_found(self, client):
        resp = client.post("/api/work-items/", json={"name": "For get"})
        tid = resp.json()["id"]
        resp = client.get(f"/api/work-items/{tid}")
        assert resp.status_code == 200
        assert resp.json()["title"] == "For get"

    def test_get_subtasks_not_found(self, client):
        resp = client.get("/api/work-items/nonexistent/children")
        assert resp.status_code == 404

    def test_delete_task_not_found(self, client):
        resp = client.delete("/api/work-items/nonexistent")
        assert resp.status_code == 404

    def test_delete_task_ok(self, client):
        resp = client.post("/api/work-items/", json={"name": "To delete"})
        tid = resp.json()["id"]
        resp = client.delete(f"/api/work-items/{tid}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_update_status_not_found(self, client):
        resp = client.post("/api/work-items/nonexistent/status", json={"status": "running"})
        assert resp.status_code == 404

    def test_update_status_missing_field(self, client):
        resp = client.post("/api/work-items/", json={"name": "Any"})
        tid = resp.json()["id"]
        resp = client.post(f"/api/work-items/{tid}/status", json={})
        assert resp.status_code == 400

    def test_update_status_ok(self, client):
        resp = client.post("/api/work-items/", json={"name": "Status test"})
        tid = resp.json()["id"]
        resp = client.post(f"/api/work-items/{tid}/status", json={"status": "running"})
        assert resp.status_code == 200

    def test_goal_task_create(self, client):
        resp = client.post("/api/work-items/", json={"title": "Goal for task", "work_type": "goal"})
        gid = resp.json()["id"]
        resp = client.post("/api/work-items/", json={
            "name": "Sub task", "work_type": "task", "parent_goal_id": gid,
        })
        assert resp.status_code == 200
        assert resp.json()["parent_goal_id"] == gid

    def test_goal_task_create_empty_title(self, client):
        resp = client.post("/api/work-items/", json={"title": "G", "work_type": "goal"})
        gid = resp.json()["id"]
        resp = client.post("/api/work-items/", json={
            "name": "", "work_type": "task", "parent_goal_id": gid,
        })
        assert resp.status_code == 400

    def test_goal_task_list(self, client):
        resp = client.post("/api/work-items/", json={"title": "G", "work_type": "goal"})
        gid = resp.json()["id"]
        client.post("/api/work-items/", json={
            "title": "Child", "work_type": "task", "parent_goal_id": gid,
        })
        resp = client.get(f"/api/work-items/{gid}?include=tree")
        assert resp.status_code == 200
        body = resp.json()
        assert "tree" in body
        assert isinstance(body["tree"], list)


# ── Triggers API ──────────────────────────────────────────────────────────


class TestTriggersAPI:
    def test_list(self, client):
        resp = client.get("/api/triggers/")
        assert resp.status_code == 200
        assert isinstance(resp.json(), (list, dict))

    def test_create_trigger_missing_field(self, client):
        resp = client.post("/api/triggers/", json={"name": "t1"})
        assert resp.status_code in (400, 422)

    def test_create_trigger_valid(self, client):
        resp = client.post("/api/triggers/", json={
            "name": "stale goal alert",
            "trigger_type": "event_count",
            "condition": {"event_type": "WorkItemCreated", "count": 3, "window_days": 7},
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "registered"

    def test_create_trigger_rejects_unsupported_count_selector(self, client):
        resp = client.post("/api/triggers/", json={
            "name": "bad selector",
            "trigger_type": "state_count",
            "condition": {
                "state_selector": "conversations",
                "count": 2,
            },
        })
        assert resp.status_code == 400
        assert "conversations" in resp.json()["detail"]

    def test_create_trigger_accepts_count_selector(self, client):
        resp = client.post("/api/triggers/", json={
            "name": "inbox backlog",
            "trigger_type": "state_count",
            "condition": {
                "state_selector": "inbox_emails",
                "state_filters": {"status": "pending"},
                "count": 50,
            },
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "registered"

    def test_delete_trigger_not_found(self, client):
        resp = client.delete("/api/triggers/nonexistent")
        assert resp.status_code == 404


# ── Inbox API ──────────────────────────────────────────────────────────────


class TestInboxAPI:
    def test_list_default(self, client):
        resp = client.get("/api/inbox/")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_list_status_all(self, client):
        resp = client.get("/api/inbox/?status=all")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_list_with_category(self, client):
        resp = client.get("/api/inbox/?category=important&limit=10")
        assert resp.status_code == 200

    def test_digest_empty(self, client):
        resp = client.get("/api/inbox/digest")
        assert resp.status_code == 200
        assert "message" in resp.json()

    def test_patch_status_not_found(self, client):
        resp = client.patch("/api/inbox/nonexistent/status", json={"status": "read"})
        assert resp.status_code == 404

    def test_poll(self, client):
        resp = client.post("/api/inbox/poll?limit=5")
        assert resp.status_code == 200


# ── Notifications API ─────────────────────────────────────────────────────


class TestNotificationsAPI:
    def test_list(self, client):
        resp = client.get("/api/notifications/")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_list_unread_only(self, client):
        resp = client.get("/api/notifications/?unread_only=true")
        assert resp.status_code == 200

    def test_unread_count(self, client):
        resp = client.get("/api/notifications/unread-count")
        assert resp.status_code == 200
        data = resp.json()
        assert "count" in data or "unread" in data

    def test_mark_read_not_found(self, client):
        resp = client.put("/api/notifications/nonexistent/read")
        assert resp.status_code == 404

    def test_mark_all_read(self, client):
        resp = client.put("/api/notifications/read-all")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ── Dashboard API ─────────────────────────────────────────────────────────


class TestDashboardAPI:
    def test_dashboard(self, client):
        resp = client.get("/api/dashboard/")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)


# ── Timeline API ──────────────────────────────────────────────────────────


class TestTimelineAPI:
    def test_events(self, client):
        resp = client.get("/api/timeline/events")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)
        assert "items" in data

    def test_events_with_pagination(self, client):
        resp = client.get("/api/timeline/events?page=1&page_size=10")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "page" in data and "has_more" in data

    def test_events_by_type(self, client):
        resp = client.get("/api/timeline/events?event_type=GoalCreated")
        assert resp.status_code == 200

    def test_events_by_date_range(self, client):
        resp = client.get("/api/timeline/events?date_from=2026-01-01&date_to=2026-12-31")
        assert resp.status_code == 200


# ── Telemetry API ─────────────────────────────────────────────────────────


class TestTelemetryAPI:
    def test_cost_summary(self, client):
        resp = client.get("/api/telemetry/cost/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)

    def test_cost_by_model(self, client):
        resp = client.get("/api/telemetry/cost/by-model")
        assert resp.status_code == 200
        assert isinstance(resp.json(), (list, dict))

    def test_llm_calls(self, client):
        resp = client.get("/api/telemetry/llm-calls")
        assert resp.status_code == 200
        assert isinstance(resp.json(), (list, dict))

    def test_tool_calls(self, client):
        resp = client.get("/api/telemetry/tool-calls")
        assert resp.status_code == 200
        assert isinstance(resp.json(), (list, dict))

    def test_tool_summary(self, client):
        resp = client.get("/api/telemetry/tool-summary")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, (list, dict))

    def test_memory_stats(self, client):
        resp = client.get("/api/telemetry/memory/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_memories" in data

    def test_health(self, client):
        resp = client.get("/api/telemetry/health")
        assert resp.status_code == 200
        assert isinstance(resp.json(), dict)


# ── Settings API ──────────────────────────────────────────────────────────


class TestSettingsAPI:
    def test_get_llm_config(self, client):
        resp = client.get("/api/settings/llm")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)
        assert "config" in data or "providers" in data or "default_provider" in data

    def test_update_llm_config(self, client):
        resp = client.put("/api/settings/llm", json={
            "default_provider": "deepseek",
            "providers": [
                {
                    "id": "deepseek",
                    "name": "DeepSeek",
                    "type": "openai_compatible",
                    "base_url": "https://api.deepseek.com/v1",
                    "model": "deepseek-chat",
                    "api_key": "test-key",
                    "enabled": True,
                },
            ],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)

    def test_get_email_config(self, client):
        resp = client.get("/api/settings/email")
        assert resp.status_code == 200
        assert isinstance(resp.json(), dict)

    def test_get_prompt_config(self, client):
        resp = client.get("/api/settings/prompt")
        assert resp.status_code == 200
        assert isinstance(resp.json(), dict)

    def test_get_notification_config(self, client):
        resp = client.get("/api/settings/notifications")
        assert resp.status_code == 200
        assert isinstance(resp.json(), dict)


# ── System API (extended) ─────────────────────────────────────────────────


class TestSystemAPIExtended:
    def test_get_runtime_mode(self, client):
        resp = client.get("/api/system/runtime-mode")
        assert resp.status_code in (200, 404)
