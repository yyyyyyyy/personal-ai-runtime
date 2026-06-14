"""Tests for experimental modules migrated to Kernel Event Log."""

import os

import pytest

os.environ.setdefault("LLM_API_KEY", "test-key")

from app.core.runtime.kernel import Kernel
from app.store.database import Database
from app.experimental.agent_gateway import AgentGateway
from app.experimental.self_improver import SelfImprover


@pytest.fixture
def exp_kernel(tmp_path):
    db = Database(db_path=str(tmp_path / "exp.db"))
    return Kernel(db=db)


def test_self_improver_logs_feedback_via_kernel(exp_kernel):
    improver = SelfImprover(kernel=exp_kernel)
    fid = improver.log_feedback("prompt-v1", "output text", True, reason="ok")
    events = exp_kernel.read_events(type="FeedbackLogged")
    assert len(events) == 1
    assert events[0].aggregate_id == fid
    assert events[0].payload["accepted"] is True


def test_self_improver_accept_rate(exp_kernel):
    improver = SelfImprover(kernel=exp_kernel)
    improver.log_feedback("prompt-v2", "a", True)
    improver.log_feedback("prompt-v2", "b", False)
    rate = improver.get_accept_rate("prompt-v2", days=7)
    assert rate == 0.5


def test_agent_gateway_send_receive(exp_kernel):
    gw = AgentGateway(kernel=exp_kernel)
    sent = gw.send("planner", "share_info", {"topic": "goals"})
    assert sent["intent"] == "share_info"
    assert sent["message_id"]

    result = gw.receive(sent)
    assert result["status"] == "received"

    sent_events = exp_kernel.read_events(type="AgentMessageSent")
    recv_events = exp_kernel.read_events(type="AgentMessageReceived")
    assert len(sent_events) == 1
    assert len(recv_events) == 1


def test_agent_gateway_rejects_unknown_intent(exp_kernel):
    gw = AgentGateway(kernel=exp_kernel)
    result = gw.receive({"intent": "unknown_intent", "from_agent": "x"})
    assert result and "error" in result
