"""API smoke tests for high-gap endpoints.

Targets the endpoints that contributed most to the <50% API coverage gate.
Uses the shared ``client`` fixture (fresh isolated DB, no real LLM).

Deep work-item contract tests live in ``test_work_items_api.py``; this file
only keeps a thin smoke surface for coverage.
"""


# ── Memory API ────────────────────────────────────────────────────────────


class TestMemoryAPI:
    def test_list_returns_list(self, client):
        resp = client.get("/api/memory/memories")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_create_and_list(self, client):
        resp = client.post("/api/memory/memories", json={"content": "likes python", "category": "fact"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        mid = body["id"]
        assert isinstance(mid, str) and mid

        resp = client.get("/api/memory/memories")
        assert resp.status_code == 200
        match = next(m for m in resp.json() if m["id"] == mid)
        assert match["content"] == "likes python"
        assert match.get("category", "fact") == "fact"

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


# ── Work Items smoke (deep coverage in test_work_items_api.py) ────────────


class TestWorkItemsSmokeAPI:
    def test_list_goals(self, client):
        resp = client.get("/api/work-items/?work_type=goal")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_list_tasks(self, client):
        resp = client.get("/api/work-items/?work_type=task")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_create_goal_minimal(self, client):
        resp = client.post("/api/work-items/", json={"title": "Learn Rust", "work_type": "goal"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "active"
        assert data["work_type"] == "goal"

    def test_create_task_via_name_alias(self, client):
        """Legacy ``name`` field still maps to title (not covered in deep suite)."""
        resp = client.post("/api/work-items/", json={"name": "Deploy app", "priority": 2})
        assert resp.status_code == 200
        assert resp.json()["title"] == "Deploy app"

    def test_create_empty_title(self, client):
        resp = client.post("/api/work-items/", json={"title": "", "work_type": "goal"})
        assert resp.status_code == 400

    def test_get_not_found(self, client):
        resp = client.get("/api/work-items/nonexistent")
        assert resp.status_code == 404

    def test_delete_not_found(self, client):
        resp = client.delete("/api/work-items/nonexistent")
        assert resp.status_code == 404

    def test_patch_validation_errors(self, client):
        resp = client.post("/api/work-items/", json={"title": "G", "work_type": "goal"})
        gid = resp.json()["id"]
        assert client.patch(f"/api/work-items/{gid}", json={}).status_code == 400
        assert client.patch(f"/api/work-items/{gid}", json={"status": "invalid"}).status_code == 400
        assert client.patch(f"/api/work-items/{gid}", json={"importance": 1.5}).status_code == 400

    def test_create_action_goal_not_found(self, client):
        resp = client.post("/api/work-items/", json={
            "title": "Step", "work_type": "action", "parent_goal_id": "missing",
        })
        assert resp.status_code == 404

    def test_update_status_missing_field(self, client):
        resp = client.post("/api/work-items/", json={"name": "Any"})
        tid = resp.json()["id"]
        resp = client.post(f"/api/work-items/{tid}/status", json={})
        assert resp.status_code == 400


# ── Approvals API ─────────────────────────────────────────────────────────


class TestApprovalsAPI:
    def test_list_returns_data(self, client):
        resp = client.get("/api/approvals/")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_list_pending_only(self, client):
        resp = client.get("/api/approvals/?pending_only=true")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_list_enriched(self, client):
        resp = client.get("/api/approvals/?pending_only=true&enriched=true")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

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
        assert "conversations" in data
        assert "memories" in data

    def test_llm_providers(self, client):
        resp = client.get("/api/system/llm-providers")
        assert resp.status_code == 200
        data = resp.json()
        assert "providers" in data
        assert "default" in data


# ── Triggers API ──────────────────────────────────────────────────────────


class TestTriggersAPI:
    def test_list(self, client):
        resp = client.get("/api/triggers/")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

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
        body = resp.json()
        assert body["status"] == "registered"
        assert body["name"] == "stale goal alert"

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
        body = resp.json()
        assert body["status"] == "registered"
        assert body["name"] == "inbox backlog"

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
        assert isinstance(resp.json(), list)

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
        data = resp.json()
        assert data["status"] in ("ok", "error")
        assert "new_count" in data


# ── Notifications API ─────────────────────────────────────────────────────


class TestNotificationsAPI:
    def test_list(self, client):
        resp = client.get("/api/notifications/")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_list_unread_only(self, client):
        resp = client.get("/api/notifications/?unread_only=true")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_unread_count(self, client):
        resp = client.get("/api/notifications/unread-count")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data.get("count", data.get("unread")), int)

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
        assert "generated_at" in data
        assert "active_goals" in data
        assert "recent_events" in data


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
        assert "items" in resp.json()

    def test_events_by_date_range(self, client):
        resp = client.get("/api/timeline/events?date_from=2026-01-01&date_to=2026-12-31")
        assert resp.status_code == 200
        assert "items" in resp.json()


# ── Telemetry API ─────────────────────────────────────────────────────────


class TestTelemetryAPI:
    def test_cost_summary(self, client):
        resp = client.get("/api/telemetry/cost/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_calls" in data
        assert "total_cost" in data

    def test_cost_by_model(self, client):
        resp = client.get("/api/telemetry/cost/by-model")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_llm_calls(self, client):
        resp = client.get("/api/telemetry/llm-calls")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_tool_calls(self, client):
        resp = client.get("/api/telemetry/tool-calls")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_tool_summary(self, client):
        resp = client.get("/api/telemetry/tool-summary")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_memory_stats(self, client):
        resp = client.get("/api/telemetry/memory/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_memories" in data

    def test_health(self, client):
        resp = client.get("/api/telemetry/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "active_work_items" in data or "task_queue_length" in data
        assert "llm_failure_rate_24h" in data


# ── Settings API ──────────────────────────────────────────────────────────


class TestSettingsAPI:
    def test_get_llm_config(self, client):
        resp = client.get("/api/settings/llm")
        assert resp.status_code == 200
        data = resp.json()
        assert "config" in data
        assert "providers_status" in data
        assert "default_model" in data

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
        assert "config" in data
        assert data["config"].get("default_provider") == "deepseek"

    def test_get_email_config(self, client):
        resp = client.get("/api/settings/email")
        assert resp.status_code == 200
        data = resp.json()
        assert "config" in data
        assert data.get("provider") == "gmail"

    def test_get_prompt_config(self, client):
        resp = client.get("/api/settings/prompt")
        assert resp.status_code == 200
        data = resp.json()
        assert "identity" in data
        assert "coding_rules" in data

    def test_get_notification_config(self, client):
        resp = client.get("/api/settings/notifications")
        assert resp.status_code == 200
        data = resp.json()
        assert "ntfy_server" in data or "webhook_url" in data


# ── System API (extended) ─────────────────────────────────────────────────


class TestSystemAPIExtended:
    def test_get_runtime_mode(self, client):
        resp = client.get("/api/system/runtime-mode")
        assert resp.status_code in (200, 404)
