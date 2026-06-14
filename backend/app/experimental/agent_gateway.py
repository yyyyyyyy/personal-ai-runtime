"""Agent Gateway — enables inter-agent communication via PersonalAgentProtocol.

Defines the message format for agent-to-agent interactions (schedule meetings, share info, etc.)
"""

import json
from typing import Any


class PersonalAgentProtocol:
    """Message protocol for agent-to-agent communication."""

    @staticmethod
    def format_message(from_agent: str, to_agent: str, intent: str, payload: dict) -> dict:
        """Format a message according to the Personal Agent Protocol."""
        return {
            "protocol": "personal-agent-v1",
            "from_agent": from_agent,
            "to_agent": to_agent,
            "intent": intent,
            "payload": payload,
        }

    @staticmethod
    def parse_message(raw: str | dict) -> dict[str, Any]:
        """Parse an incoming agent message."""
        if isinstance(raw, str):
            return json.loads(raw)
        return raw

    @staticmethod
    def get_intent(msg: dict) -> str:
        return msg.get("intent", "")


class AgentGateway:
    """Receives and routes messages between Personal AI Runtime agents."""

    SUPPORTED_INTENTS = ["schedule_meeting", "share_info", "request_status", "offer_help"]

    def __init__(self):
        self.received_messages: list[dict] = []

    def receive(self, message: dict) -> dict | None:
        """Receive and validate an incoming agent message."""
        intent = PersonalAgentProtocol.get_intent(message)
        if intent not in self.SUPPORTED_INTENTS:
            return {"error": f"Unsupported intent: {intent}"}
        self.received_messages.append(message)
        return {"status": "received", "intent": intent}

    def send(self, to_agent: str, intent: str, payload: dict) -> dict:
        """Create an outgoing message."""
        return PersonalAgentProtocol.format_message(
            from_agent="personal-ai-runtime",
            to_agent=to_agent,
            intent=intent,
            payload=payload,
        )


agent_gateway = AgentGateway()
