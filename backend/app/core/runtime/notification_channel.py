"""Notification Channel — unified notification delivery for desktop, webhook, ntfy.

This module replaces the hard-coded Telegram notifier with a pluggable
notification channel abstraction. Cron job results (Belief, Morning Brief,
Goal Stuck, Inbox Digest) route through this module.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class NotificationPayload:
    title: str
    content: str
    type: str = "system"
    priority: str = "normal"  # low, normal, high


class BaseChannel:
    """Abstract notification channel."""

    async def send(self, payload: NotificationPayload) -> bool:
        raise NotImplementedError


class DesktopChannel(BaseChannel):
    """Desktop notification via WebSocket broadcast to the UI.

    The backend WebSocket endpoint broadcasts the notification to all
    connected clients. The Electron wrapper will handle native OS notifications.
    """

    async def send(self, payload: NotificationPayload) -> bool:
        try:
            from app.main import broadcast_notification

            await broadcast_notification({
                "type": "desktop_notification",
                "title": payload.title,
                "content": payload.content,
            })
            return True
        except Exception:
            logger.warning("Desktop notification failed", exc_info=True)
            return False


class WebhookChannel(BaseChannel):
    """Generic webhook notification (replaces Telegram).

    Posts JSON to a user-configured webhook URL.
    """

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    async def send(self, payload: NotificationPayload) -> bool:
        if not self.webhook_url:
            return False
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    self.webhook_url,
                    json={
                        "title": payload.title,
                        "content": payload.content,
                        "type": payload.type,
                        "source": "Personal AI Runtime",
                    },
                )
                if response.status_code >= 400:
                    logger.warning(
                        "Webhook notification failed: HTTP %d", response.status_code
                    )
                    return False
                return True
        except Exception:
            logger.warning("Webhook notification failed", exc_info=True)
            return False


class NtfyChannel(BaseChannel):
    """ntfy.sh push notification channel."""

    def __init__(self, topic: str, server: str = "https://ntfy.sh"):
        self.topic = topic
        self.server = server

    async def send(self, payload: NotificationPayload) -> bool:
        if not self.topic:
            return False
        try:
            import httpx

            url = f"{self.server}/{self.topic}"
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    url,
                    content=payload.content.encode("utf-8"),
                    headers={
                        "Title": payload.title,
                        "Priority": payload.priority,
                        "Tags": "robot",
                    },
                )
                return response.status_code < 400
        except Exception:
            logger.warning("ntfy notification failed", exc_info=True)
            return False


class NotificationRouter:
    """Route notification to all configured channels."""

    def __init__(self):
        self.desktop = DesktopChannel()
        self.webhook: WebhookChannel | None = None
        self.ntfy: NtfyChannel | None = None

    def configure(
        self,
        webhook_url: str = "",
        ntfy_topic: str = "",
        ntfy_server: str = "https://ntfy.sh",
    ):
        if webhook_url:
            self.webhook = WebhookChannel(webhook_url)
        else:
            self.webhook = None

        if ntfy_topic:
            self.ntfy = NtfyChannel(ntfy_topic, ntfy_server)
        else:
            self.ntfy = None

    async def notify(
        self,
        title: str,
        content: str,
        type_: str = "system",
        priority: str = "normal",
    ) -> dict:
        payload = NotificationPayload(
            title=title, content=content, type=type_, priority=priority
        )
        results = {}

        # Desktop always enabled
        results["desktop"] = await self.desktop.send(payload)

        if self.webhook:
            results["webhook"] = await self.webhook.send(payload)

        if self.ntfy:
            results["ntfy"] = await self.ntfy.send(payload)

        logger.info(
            "Notification sent: title=%s channels=%s",
            title,
            json.dumps(results),
        )
        return results


notification_router = NotificationRouter()
