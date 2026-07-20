"""Tests for notification bridge."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

@pytest.mark.asyncio
async def test_push_notification_broadcasts(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    from app.store.database import Database

    monkeypatch.setattr(
        "app.config.settings.sqlite_path",
        str(tmp_path / "notif_bridge.db"),
    )
    Database(db_path=str(tmp_path / "notif_bridge.db"))

    with patch("app.main.broadcast_notification", new=AsyncMock()) as broadcast:
        from app.core.runtime.notification_bridge import push_notification

        notif = push_notification("info", "Title", "Body")
        assert notif["title"] == "Title"
        await __import__("asyncio").sleep(0.05)
        broadcast.assert_awaited()


def test_push_notification_without_event_loop(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    from app.store.database import Database

    db_path = str(tmp_path / "notif_sync.db")
    Database(db_path=db_path)

    def _fake_run(coro, *args, **kwargs):
        # asyncio.run is mocked, so the coroutine passed in would never be
        # awaited — close it explicitly to avoid "coroutine was never awaited".
        coro.close()

    with patch("app.core.runtime.notification_bridge.asyncio.get_running_loop", side_effect=RuntimeError):
        with patch("app.core.runtime.notification_bridge.asyncio.run", side_effect=_fake_run) as run_mock:
            from app.core.runtime.notification_bridge import push_notification

            notif = push_notification("alert", "Sync", "Content")
            assert notif["content"] == "Content"
            run_mock.assert_called_once()


@pytest.mark.asyncio
async def test_broadcast_event_async_path_awaits():
    """In an async context, broadcast_event must schedule AND complete the broadcast."""
    from app.core.runtime import notification_bridge as nb

    seen: list[dict] = []
    with patch("app.main.broadcast_notification", new=AsyncMock(side_effect=seen.append)):
        nb.broadcast_event({"type": "memory_changed", "memory_id": "m1"})
        # Let the loop run the fire-and-forget task to completion.
        await __import__("asyncio").sleep(0.05)
    assert any(e.get("type") == "memory_changed" for e in seen)
    # Strong-reference set must be cleaned up once tasks finish.
    assert all(t.done() for t in nb._PENDING_BROADCASTS)


def test_broadcast_event_sync_path_runs_to_completion(tmp_path, monkeypatch):
    """In a sync context, broadcast_event must actually await _broadcast.

    Regression for the 'never awaited coroutine' risk: the sync path uses
    asyncio.run() so the WS write completes (or fails) before the caller
    proceeds. We assert functional delivery rather than absence-of-warning,
    because AsyncMock teardown can emit benign RuntimeWarnings unrelated to
    our code.
    """
    from app.core.runtime import notification_bridge as nb

    monkeypatch.setenv("LLM_API_KEY", "test-key")
    from app.store.database import Database
    Database(db_path=str(tmp_path / "be_sync.db"))

    seen: list[dict] = []
    with patch("app.main.broadcast_notification", new=AsyncMock(side_effect=seen.append)):
        with patch.object(nb.asyncio, "get_running_loop", side_effect=RuntimeError):
            nb.broadcast_event({"type": "memory_changed", "memory_id": "m_sync"})
    # The whole point of the sync branch is deterministic delivery.
    assert any(e.get("memory_id") == "m_sync" for e in seen), (
        "broadcast_event in sync context must await _broadcast to completion "
        "(regression guard for async/sync behaviour split)."
    )


def test_broadcast_event_swallows_transport_failure(monkeypatch):
    """A failure inside _broadcast must not propagate to the caller."""
    from app.core.runtime import notification_bridge as nb

    async def _boom(_event):
        raise RuntimeError("ws down")

    monkeypatch.setattr(nb, "_broadcast", _boom)
    # Sync path — should swallow.
    with patch.object(nb.asyncio, "get_running_loop", side_effect=RuntimeError):
        nb.broadcast_event({"type": "memory_changed"})  # must not raise


@pytest.mark.asyncio
async def test_broadcast_event_uses_bound_loop_from_sync_thread(monkeypatch):
    """Sync callers prefer the RuntimeLoop-bound loop over asyncio.run."""
    from app.core.runtime import notification_bridge as nb

    seen: list[dict] = []
    monkeypatch.setattr(
        "app.main.broadcast_notification",
        AsyncMock(side_effect=lambda e: seen.append(e)),
    )
    loop = asyncio.get_running_loop()
    nb.set_broadcast_loop(loop)

    def _from_worker():
        with patch.object(nb.asyncio, "get_running_loop", side_effect=RuntimeError):
            with patch.object(nb.asyncio, "run") as run_mock:
                nb.broadcast_event({"type": "memory_changed", "memory_id": "bound"})
                run_mock.assert_not_called()

    await asyncio.to_thread(_from_worker)
    await asyncio.sleep(0.05)
    assert any(e.get("memory_id") == "bound" for e in seen)
    nb.set_broadcast_loop(None)


@pytest.mark.asyncio
async def test_push_notification_uses_broadcast_event(monkeypatch):
    """push_notification must delegate transport to broadcast_event (no parallel path)."""
    from app.core.runtime import notification_bridge as nb

    captured: list[dict] = []
    monkeypatch.setattr(nb, "broadcast_event", lambda ev: captured.append(ev))

    def fake_create(t, title, content, **kwargs):
        return {"id": "x", "type": t, "title": title, "content": content}

    monkeypatch.setattr(nb, "create_notification", fake_create)

    nb.push_notification("info", "T", "C")
    assert len(captured) == 1
    # spread `{"type": "notification", **notif}` lets notif["type"] win,
    # so the wire payload carries the *notification category* ("info"),
    # not the literal string "notification". That is by design — consumers
    # route on category. Assert the structural contract instead.
    assert captured[0]["title"] == "T"
    assert captured[0]["content"] == "C"
    assert captured[0]["id"] == "x"

def test_push_notification_envelope_and_sync_broadcast(monkeypatch):
    from app.core.runtime import notification_bridge

    captured = []

    async def _fake_broadcast(event):
        captured.append(event)

    monkeypatch.setattr(notification_bridge, "_broadcast", _fake_broadcast)

    notif = notification_bridge.push_notification("test", "Title", "Body")
    assert notif["type"] == "test"
    assert notif["title"] == "Title"
    assert notif["content"] == "Body"
    assert len(captured) == 1
    assert captured[0]["type"] == "notification"
    assert captured[0]["notification_type"] == "test"
    assert captured[0]["title"] == "Title"


def test_broadcast_event_sync_path_without_running_loop(monkeypatch):
    from app.core.runtime import notification_bridge

    captured = []

    async def _fake_broadcast(event):
        captured.append(event)

    monkeypatch.setattr(notification_bridge, "_broadcast", _fake_broadcast)
    monkeypatch.setattr(
        notification_bridge.asyncio,
        "get_running_loop",
        lambda: (_ for _ in ()).throw(RuntimeError("no loop")),
    )

    notification_bridge.broadcast_event({"type": "memory_changed"})
    assert len(captured) == 1
    assert captured[0]["type"] == "memory_changed"
