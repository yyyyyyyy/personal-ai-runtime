"""Integration test: approval flow via Kernel."""

import os
import pytest

os.environ.setdefault("LLM_API_KEY", "test-key")

from app.core.runtime.kernel import Kernel
from app.store.database import Database


@pytest.fixture
def kernel(tmp_path):
    return Kernel(db=Database(db_path=str(tmp_path / "approval.db")))


@pytest.mark.asyncio
async def test_high_risk_capability_pending_then_approve(kernel):
    k = kernel
    cap = await k.invoke_capability("write_file", {"path": "/tmp/x", "content": "hi"}, actor="user")
    assert cap["status"] == "pending"
    approval_id = cap["approval_id"]

    cap2 = await k.invoke_capability(
        "write_file",
        {"path": "/tmp/x", "content": "hi"},
        actor="user",
        correlation_id="retry",
        pre_approved=True,
        approval_id=approval_id,
    )
    assert cap2["status"] == "success"
