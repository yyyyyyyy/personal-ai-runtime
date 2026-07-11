"""Coverage gap closure — targeted tests for modules missing 1-2 branches."""
import os

os.environ.setdefault("LLM_API_KEY", "test-key")


class TestHandlerRegistry:
    def test_registered_types_returns_sorted(self):
        from app.core.runtime.handler_registry import _registry, registered_types, subscribe

        key = f"TestType_{id(self)}"

        @subscribe(key)
        async def handle(_ctx, _evt):
            pass

        types = registered_types()
        assert key in types

        _registry.pop(key, None)

    def test_subscribe_overwrite_warns(self):
        from app.core.runtime.handler_registry import _registry, subscribe

        key = f"TestOverwrite_{id(self)}"

        @subscribe(key)
        async def handler_a(_ctx, _evt):
            pass

        @subscribe(key)
        async def handler_b(_ctx, _evt):
            pass

        assert _registry[key] is handler_b
        _registry.pop(key, None)


class TestSensitiveRouter:
    def test_is_sensitive_capability_with_local_enabled(self, monkeypatch):
        monkeypatch.setattr(
            "app.core.runtime.sensitive_router.settings.sensitive_ops_local", True
        )

        from app.core.runtime.sensitive_router import sensitive_router

        assert sensitive_router.is_sensitive_capability("write_file")
        assert sensitive_router.is_sensitive_capability("shell_exec")
        assert sensitive_router.is_sensitive_capability("read_file") is False

    def test_elevated_risk_high_when_sensitive(self, monkeypatch):
        monkeypatch.setattr(
            "app.core.runtime.sensitive_router.settings.sensitive_ops_local", True
        )

        from app.core.runtime.sensitive_router import sensitive_router

        assert sensitive_router.elevated_risk("write_file") == "high"
        assert sensitive_router.elevated_risk("read_file") == ""


class TestNotificationBridge:
    def test_push_notification_and_sync_broadcast(self, monkeypatch):
        from app.core.runtime import notification_bridge

        captured = []

        async def _fake_broadcast(event):
            captured.append(event)

        monkeypatch.setattr(notification_bridge, "_broadcast", _fake_broadcast)

        notif = notification_bridge.push_notification("test", "Title", "Body")
        assert notif["type"] == "test"
        assert notif["title"] == "Title"
        assert notif["content"] == "Body"
        # Envelope type stays "notification"; domain category is notification_type.
        assert len(captured) == 1
        assert captured[0]["type"] == "notification"
        assert captured[0]["notification_type"] == "test"
        assert captured[0]["title"] == "Title"

    def test_broadcast_event_sync_path(self, monkeypatch):
        from app.core.runtime import notification_bridge

        captured = []

        async def _fake_broadcast(event):
            captured.append(event)

        monkeypatch.setattr(notification_bridge, "_broadcast", _fake_broadcast)
        monkeypatch.setattr(
            notification_bridge.asyncio,
            "get_running_loop",
            lambda: (_ for _ in ()).throw(RuntimeError("no loop")),
        )

        notification_bridge.broadcast_event({"type": "memory_changed"})
        assert len(captured) == 1
        assert captured[0]["type"] == "memory_changed"


class TestProjectorsGovernance:
    def test_policy_updated_projector(self, isolated_kernel):
        k, _db = isolated_kernel
        k.emit_event(
            "PolicyCreated", "policy", "pol_cov",
            payload={"capability": "read_file", "risk_level": "low"},
            actor="admin",
        )
        k.emit_event(
            "PolicyUpdated", "policy", "pol_cov",
            payload={"risk_level": "high"},
            actor="admin",
        )
        rows = k.query_state("policy_events", id="pol_cov")
        assert rows[0]["risk_level"] == "high"


class TestProjectorsChat:
    def test_conversation_updated_with_summary(self, isolated_kernel):
        k, db = isolated_kernel
        k.emit_event(
            "ConversationCreated", "conversation", "conv_cov",
            payload={"title": "Test Conversation"},
            actor="user",
        )
        k.emit_event(
            "ConversationUpdated", "conversation", "conv_cov",
            payload={"title": "Updated Title", "summary": "A summary"},
            actor="user",
        )
        with db.get_db() as conn:
            row = conn.execute(
                "SELECT * FROM conversations WHERE id = ?", ("conv_cov",)
            ).fetchone()
        assert row is not None
        row_dict = dict(row)
        assert row_dict["title"] == "Updated Title"
        assert row_dict["summary"] == "A summary"

    def test_conversation_deleted_projector(self, isolated_kernel):
        k, db = isolated_kernel
        k.emit_event(
            "ConversationCreated", "conversation", "conv_del",
            payload={"title": "To Delete"},
            actor="user",
        )
        k.emit_event(
            "MessageAppended", "message", "conv_del",
            payload={"message_id": "msg_del", "role": "user", "content": "hi"},
            actor="user",
        )
        k.emit_event(
            "ConversationDeleted", "conversation", "conv_del",
            payload={}, actor="user",
        )
        with db.get_db() as conn:
            conv_row = conn.execute(
                "SELECT * FROM conversations WHERE id = ?", ("conv_del",)
            ).fetchone()
            msg_row = conn.execute(
                "SELECT * FROM messages WHERE conversation_id = ?", ("conv_del",)
            ).fetchone()
        assert conv_row is None
        assert msg_row is None


class TestProjectorsAux:
    def test_notification_read_all_projector(self, isolated_kernel):
        k, _db = isolated_kernel
        k.emit_event(
            "NotificationCreated", "notification", "n1",
            payload={"type": "test", "title": "N1", "content": "body"},
            actor="system",
        )
        k.emit_event(
            "NotificationCreated", "notification", "n2",
            payload={"type": "test", "title": "N2", "content": "body"},
            actor="system",
        )
        k.emit_event(
            "NotificationRead", "notification", "n1",
            payload={}, actor="user",
        )
        k.emit_event(
            "NotificationReadAll", "notification", "n_all",
            payload={}, actor="user",
        )
        rows = k.query_state("notifications")
        for r in rows:
            assert r["read"] == 1
