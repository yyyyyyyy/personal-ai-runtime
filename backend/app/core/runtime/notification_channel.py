"""Notification Channel — pluggable external delivery (desktop, webhook, ntfy).

In-app / WebSocket fan-out stays in ``notification_bridge`` (persist + WS).
This module is for *external* channels used by cron digests and product jobs.

Use ``NotificationRouter.notify(..., persist=True)`` when the alert should also
appear in the in-app notification center (replaces separate
``create_notification`` + ``notify`` call pairs).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.runtime.kernel import Kernel

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
    """Desktop / UI tip via the shared notification_bridge transport."""

    async def send(self, payload: NotificationPayload) -> bool:
        try:
            from app.core.runtime.notification_bridge import broadcast_event

            broadcast_event({
                "type": "desktop_notification",
                "title": payload.title,
                "content": payload.content,
                "notification_type": payload.type,
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
    """Route notification to configured channels (+ optional in-app persist)."""

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
        *,
        persist: bool = False,
        kernel: "Kernel | None" = None,
    ) -> dict:
        """Deliver to desktop/webhook/ntfy.

        When ``persist=True``, also write an in-app notification via
        ``notification_bridge.push_notification`` (and skip the extra
        desktop WS tip — the persist path already broadcasts).
        """
        payload = NotificationPayload(
            title=title, content=content, type=type_, priority=priority
        )
        results: dict[str, bool] = {}

        if persist:
            from app.core.runtime.notification_bridge import push_notification

            push_notification(type_, title, content, kernel=kernel)
            results["persisted"] = True
        else:
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
