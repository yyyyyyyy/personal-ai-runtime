"""Tests for untrusted-source taint escalation."""

import pytest

from app.core.runtime.kernel import Kernel
from app.core.runtime.taint import taint_registry
from app.store.database import Database


@pytest.fixture
def kernel(tmp_path):
    db = Database(db_path=str(tmp_path / "taint.db"))
    return Kernel(db=db)


@pytest.mark.asyncio
async def test_tainted_write_forces_high_risk(kernel):
    corr = "corr-taint-test"
    taint_registry.mark(corr, source="external_ingestion", reason="check_inbox")

    result = await kernel.invoke_capability(
        name="write_file",
        args={"path": "/tmp/x", "content": "injected"},
        actor="user",
        correlation_id=corr,
        pre_approved=False,
    )

    assert result["status"] == "pending"
    assert "approval_id" in result

    taint_registry.clear(corr)
