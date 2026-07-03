"""Additional scheduler handler coverage via timer_trigger_handler."""

import os
from unittest.mock import patch

import pytest

os.environ.setdefault("LLM_API_KEY", "test-key")


@pytest.mark.asyncio
@patch("app.core.runtime.memory_decay.run_memory_decay")
async def test_run_memory_decay(mock_decay):
    from app.core.agents.mvp.timer_trigger_handler import _call_product

    await _call_product("memory_decay")
    mock_decay.assert_called_once()


@pytest.mark.asyncio
@patch("app.core.agents.world_model.world_model.refresh_snapshot")
async def test_run_world_model_snapshot(mock_refresh):
    from app.core.agents.mvp.timer_trigger_handler import _call_product

    await _call_product("world_model_snapshot")
    mock_refresh.assert_called_once()


@pytest.mark.asyncio
@patch("app.product.inbox.generate_inbox_digest")
async def test_run_inbox_digest(mock_digest):
    from app.core.agents.mvp.timer_trigger_handler import _call_product

    await _call_product("inbox_digest")
    mock_digest.assert_called_once()


@pytest.mark.asyncio
@patch("app.core.runtime.kernel_instance.kernel.save_projection_snapshots")
async def test_run_projection_snapshots(mock_save):
    mock_save.return_value = [{"aggregate_type": "goal"}]

    from app.core.agents.mvp.timer_trigger_handler import _call_product

    await _call_product("projection_snapshots")
    mock_save.assert_called_once()


@pytest.mark.asyncio
@patch("app.core.runtime.kernel_instance.kernel.query_state")
async def test_run_deadline_alert_creates_notifications(mock_query):
    from datetime import UTC, datetime, timedelta

    deadline = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    mock_query.return_value = [{"id": "g1", "title": "Due Soon", "deadline": deadline}]

    with patch("app.product.notifications.create_notification") as create:
        from app.core.agents.mvp.timer_trigger_handler import _call_product

        await _call_product("deadline_alert")
        create.assert_called_once()


@pytest.mark.asyncio
async def test_call_product_unknown_handler():
    from app.core.agents.mvp.timer_trigger_handler import _call_product

    await _call_product("nonexistent_handler")
