"""Inbound connectors — capture Experience dimensions (CONNECTOR_RFC v0.1)."""

from app.core.connectors.browser_capture import capture_browser_activity
from app.core.connectors.calendar_capture import capture_calendar_observations
from app.core.connectors.git_capture import capture_git_activity

__all__ = ["capture_browser_activity", "capture_calendar_observations", "capture_git_activity"]
