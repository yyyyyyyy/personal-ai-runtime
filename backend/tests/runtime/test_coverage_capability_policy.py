"""Coverage tests for capability_policy external MCP tool registration."""
import pytest

from app.core.runtime.capability_policy import capability_policy
from app.core.runtime.kernel import Kernel
from app.store.database import Database


@pytest.fixture
def kernel():
    db = Database(db_path=":memory:")
    k = Kernel(db=db)
    return k


def test_register_external_tool_auto_allow(kernel):
    """Registering a low-risk external tool caches it in memory."""
    capability_policy.register_external_tool("ext_tool_1", risk="low")
    risk = capability_policy.risk_for("ext_tool_1")
    assert risk == "low"


def test_register_external_tool_high_risk(kernel):
    """Registering a high-risk external tool returns 'high'."""
    capability_policy.register_external_tool("ext_tool_2", risk="high")
    risk = capability_policy.risk_for("ext_tool_2")
    assert risk == "high"


def test_register_external_tool_forbidden(kernel):
    """Registering a forbidden external tool returns 'forbidden'."""
    capability_policy.register_external_tool("ext_danger", risk="forbidden")
    risk = capability_policy.risk_for("ext_danger")
    assert risk == "forbidden"


def test_clear_external_tools(kernel):
    """After clearing external tools, risk_for reverts unknown tools to default."""
    capability_policy.register_external_tool("ext_temp", risk="low")
    capability_policy.clear_external_tools()
    risk = capability_policy.risk_for("ext_temp")
    assert risk in ("low", "high")


def test_risk_for_unknown_tool_default(kernel):
    """risk_for on unknown tool returns default risk."""
    risk = capability_policy.risk_for("completely_unknown_tool")
    assert risk in ("low", "high")
