"""Agent Gateway — inter-agent messaging via Kernel Event Log.

Status: EXPERIMENTAL — not wired into production Brain/Planner yet.
"""

from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING, Any

from app.core.runtime.kernel.constants import (
    AGGREGATE_FRICTION,
    EVENT_AGENT_MESSAGE_RECEIVED,
    EVENT_AGENT_MESSAGE_SENT,
)

if TYPE_CHECKING:
    from app.core.runtime.kernel import Kernel


class PersonalAgentProtocol:
    """Message protocol for agent-to-agent communication."""

    @staticmethod
    def format_message(from_agent: str, to_agent: str, intent: str, payload: dict) -> dict:
        return {
            "protocol": "personal-agent-v1",
            "from_agent": from_agent,
            "to_agent": to_agent,
            "intent": intent,
            "payload": payload,
        }

    @staticmethod
    def parse_message(raw: str | dict) -> dict[str, Any]:
        if isinstance(raw, str):
            return json.loads(raw)
        return raw

    @staticmethod
    def get_intent(msg: dict) -> str:
        return msg.get("intent", "")


class AgentGateway:
    """Routes agent messages through Kernel ABI (emit_event)."""

    SUPPORTED_INTENTS = ["schedule_meeting", "share_info", "request_status", "offer_help"]

    def __init__(self, kernel: Kernel | None = None):
        from app.core.runtime.kernel_instance import kernel as default_kernel

        self._kernel = kernel or default_kernel

    def receive(self, message: dict) -> dict | None:
        """Validate and record an incoming agent message."""
        intent = PersonalAgentProtocol.get_intent(message)
        if intent not in self.SUPPORTED_INTENTS:
            return {"error": f"Unsupported intent: {intent}"}

        msg_id = str(uuid.uuid4())
        self._kernel.emit_event(
            EVENT_AGENT_MESSAGE_RECEIVED,
            AGGREGATE_FRICTION,
            msg_id,
            payload=message,
            actor=message.get("from_agent", "external"),
        )
        return {"status": "received", "intent": intent, "message_id": msg_id}

    def send(self, to_agent: str, intent: str, payload: dict, *, from_agent: str = "personal-ai-runtime") -> dict:
        """Create and record an outgoing agent message."""
        message = PersonalAgentProtocol.format_message(from_agent, to_agent, intent, payload)
        msg_id = str(uuid.uuid4())
        self._kernel.emit_event(
            EVENT_AGENT_MESSAGE_SENT,
            AGGREGATE_FRICTION,
            msg_id,
            payload=message,
            actor=from_agent,
        )
        return {**message, "message_id": msg_id}


agent_gateway = AgentGateway()
