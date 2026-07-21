"""Notification helpers — Product-facing re-exports of the Ports ABI.

Persistence and transport live in Runtime (``notification_bridge``);
this module keeps historical import paths for Product / API / agents.
"""

from app.core.runtime.read_ports import (
    NotificationPayload,
    create_notification,
    find_notification,
)

__all__ = [
    "NotificationPayload",
    "create_notification",
    "find_notification",
]
