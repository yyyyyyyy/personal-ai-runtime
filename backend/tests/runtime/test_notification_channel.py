"""Tests for notification_channel.py — initialization and configuration paths."""
import asyncio

from app.core.runtime.notification_channel import (
    DesktopChannel,
    NotificationPayload,
    NotificationRouter,
    NtfyChannel,
    WebhookChannel,
)


class TestNotificationPayload:
    def test_defaults(self):
        p = NotificationPayload(title="test", content="hello")
        assert p.title == "test"
        assert p.content == "hello"
        assert p.type == "system"
        assert p.priority == "normal"

    def test_custom(self):
        p = NotificationPayload(title="t", content="c", type="alert", priority="high")
        assert p.title == "t"
        assert p.content == "c"
        assert p.type == "alert"
        assert p.priority == "high"


class TestNotificationRouter:
    def test_init_defaults(self):
        router = NotificationRouter()
        assert isinstance(router.desktop, DesktopChannel)
        assert router.webhook is None
        assert router.ntfy is None

    def test_configure_webhook(self):
        router = NotificationRouter()
        router.configure(webhook_url="https://example.com/hook")
        assert router.webhook is not None
        assert router.ntfy is None

    def test_configure_ntfy(self):
        router = NotificationRouter()
        router.configure(ntfy_topic="test")
        assert router.ntfy is not None
        assert router.webhook is None

    def test_configure_both(self):
        router = NotificationRouter()
        router.configure(webhook_url="https://e.com/h", ntfy_topic="t")
        assert router.webhook is not None
        assert router.ntfy is not None

    def test_configure_clears(self):
        router = NotificationRouter()
        router.configure(webhook_url="https://e.com/h")
        assert router.webhook is not None
        router.configure(webhook_url="")
        assert router.webhook is None


class TestWebhookChannel:
    def test_init(self):
        ch = WebhookChannel(webhook_url="https://example.com/hook")
        assert ch.webhook_url == "https://example.com/hook"

    def test_empty_url_sends_false(self):
        ch = WebhookChannel(webhook_url="")
        payload = NotificationPayload(title="t", content="c")
        result = asyncio.run(ch.send(payload))
        assert result is False


class TestNtfyChannel:
    def test_init(self):
        ch = NtfyChannel(topic="test")
        assert ch.topic == "test"
        assert ch.server == "https://ntfy.sh"

    def test_empty_topic_sends_false(self):
        ch = NtfyChannel(topic="")
        payload = NotificationPayload(title="t", content="c")
        result = asyncio.run(ch.send(payload))
        assert result is False


class TestDesktopChannel:
    def test_init(self):
        ch = DesktopChannel()
        assert ch is not None

    def test_send_without_ws_connections(self):
        async def run():
            ch = DesktopChannel()
            payload = NotificationPayload(title="t", content="c")
            result = await ch.send(payload)
            return result
        import asyncio
        # Should not crash even if no WS connections
        result = asyncio.run(run())
        assert result is True or result is False


class TestNotificationRouterNotify:
    def test_notify_basic(self):
        async def run():
            router = NotificationRouter()
            result = await router.notify("Test Title", "Test Content")
            return result
        import asyncio
        result = asyncio.run(run())
        assert "desktop" in result

    def test_notify_with_webhook_url_only(self):
        async def run():
            router = NotificationRouter()
            router.configure(webhook_url="http://localhost:12345/nonexistent")
            result = await router.notify("Test", "Content", priority="high")
            return result
        import asyncio
        result = asyncio.run(run())
        assert "desktop" in result
        assert "webhook" in result

    def test_notify_with_ntfy_only(self):
        async def run():
            router = NotificationRouter()
            router.configure(ntfy_topic="test-topic")
            result = await router.notify("Test", "Content", type_="alert")
            return result
        import asyncio
        result = asyncio.run(run())
        assert "desktop" in result
        assert "ntfy" in result

    def test_notify_all_channels(self):
        async def run():
            router = NotificationRouter()
            router.configure(webhook_url="http://localhost:1/h", ntfy_topic="t")
            result = await router.notify("T", "C")
            return result
        import asyncio
        result = asyncio.run(run())
        assert "desktop" in result
        assert "webhook" in result
        assert "ntfy" in result
