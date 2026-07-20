"""Global pytest configuration."""

import os
from typing import Any, AsyncIterator

import pytest

os.environ.setdefault("LLM_API_KEY", "test-key")
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
os.environ.setdefault("CHROMA_TELEMETRY_IMPL", "none")
os.environ.setdefault("CHROMA_TELEMETRY_ENABLED", "false")
os.environ.setdefault("MCP_EXTERNAL_ENABLED", "false")

# Re-read settings after env defaults so tests see MCP_EXTERNAL_ENABLED=false.
from app.config import reset_settings

reset_settings()


# ── FakeBrain ──────────────────────────────────────────────────────────
_fake_brain_script: list[dict[str, Any]] = []


class FakeBrain:
    """Drop-in replacement for Brain that replays a scripted event stream."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def chat_stream(
        self,
        conversation: Any,
        user_message: str,
        *,
        system_prompt: str = "",
        execution_id: str = "",
        correlation_id: str = "",
    ) -> AsyncIterator[dict[str, Any]]:
        for event in list(_fake_brain_script):
            yield event

    async def continue_after_tool_result(self, *args: Any, **kwargs: Any) -> str:
        return ""


@pytest.fixture
def fake_brain(monkeypatch):
    """Patch Brain + ensure_scheduler/send_message so the chat handler runs
    synchronously after emit_event(``ChatRequested``) but before the SSE
    StreamingResponse body is iterated.

    Without this, the Kernel's ``_dispatch`` → ``create_task`` chain never
    interleaves with ``StreamingResponse`` body iteration under
    httpx.ASGITransport on Windows ProactorEventLoop, causing infinite
    blocking in the SSE stream.
    """
    _fake_brain_script.clear()
    monkeypatch.setattr("app.core.agents.brain.Brain", FakeBrain)

    # —— Patch send_message to run the ChatRequested handler inline ——
    async def _wrapped_send_message(conv_id, body):
        """Like the original send_message, but directly invokes the
        ChatRequested handler after the event is emitted so that the
        SSE queue is populated before StreamingResponse begins."""
        import asyncio as _asyncio2
        import json as _json2
        import uuid as _uuid2

        from app.api.chat import ConversationAPI

        conv = ConversationAPI.get(conv_id)
        if not conv:
            from fastapi.exceptions import HTTPException
            raise HTTPException(status_code=404, detail="Conversation not found")
        content = body.content
        if not content.strip():
            from fastapi.exceptions import HTTPException
            raise HTTPException(status_code=400, detail="Message content is required")

        correlation_id = f"chat_{_uuid2.uuid4().hex[:12]}"

        from app.core.runtime.kernel_instance import kernel as _k
        from app.core.runtime.notification_bridge import register, unregister
        sse_queue = register(correlation_id)

        _k.emit_event(
            "ChatRequested", "chat", conv_id,
            payload={"user_message": content, "conversation_id": conv_id},
            actor="user", correlation_id=correlation_id,
        )

        # —— INLINE HANDLER EXECUTION ——
        from app.core.runtime.execution import ExecutionContext, execution_scope, identity_resolver
        from app.core.runtime.handler_registry import get_handlers

        handlers = get_handlers("ChatRequested")
        handler = handlers[0] if handlers else None
        if handler is not None:
            principal = identity_resolver.resolve("agent:primary", _k)
            ctx = ExecutionContext(
                instance_id="agent:primary",
                actor="agent:primary",
                correlation_id=correlation_id,
                _kernel=_k,
                principal=principal,
                execution_id=f"exec_{correlation_id[:8]}",
            )
            with execution_scope(ctx.execution_id):
                events = _k.read_events(
                    correlation_id=correlation_id, type="ChatRequested", limit=1,
                )
                if events:
                    await handler(ctx, events[0])

        # —— SSE stream (same as original) ——
        from app.config import settings

        async def sse_stream():
            try:
                loop = _asyncio2.get_running_loop()
                deadline = loop.time() + settings.total_tool_loop_timeout + 10.0
                last_ping = loop.time()
                while loop.time() < deadline:
                    try:
                        data = await _asyncio2.wait_for(sse_queue.get(), timeout=0.1)
                        yield f"data: {_json2.dumps(data)}\n\n"
                        last_ping = loop.time()
                        if data.get("type") in ("done", "error"):
                            break
                    except _asyncio2.TimeoutError:
                        if loop.time() - last_ping > settings.total_tool_loop_timeout:
                            yield (
                                "data: "
                                + _json2.dumps({"type": "error", "content": "timed out"})
                                + "\n\n"
                            )
                            break
                        done_events = _k.read_events(
                            type="ChatDone", correlation_id=correlation_id, limit=1,
                        )
                        if done_events:
                            yield f"data: {_json2.dumps({'type': 'done'})}\n\n"
                            break
            finally:
                unregister(correlation_id)

        from starlette.responses import StreamingResponse
        return StreamingResponse(
            sse_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    monkeypatch.setattr("app.api.chat.send_message", _wrapped_send_message)

    class _Setter:
        @staticmethod
        def set_script(events: list[dict[str, Any]]) -> None:
            _fake_brain_script.clear()
            _fake_brain_script.extend(events)

    yield _Setter
    _fake_brain_script.clear()


@pytest.fixture(autouse=True)
def _reset_runtime():
    """Reset Runtime subsystems between tests for isolation.

    Without this, global singletons (capability_policy,
    taint_registry, source_registry) can leak state between tests.

    Also restores ``kernel_instance.kernel`` to the canonical LazyProxy when a
    test assigned a concrete Kernel without monkeypatch cleanup. Otherwise
    ``task_engine`` (holds the proxy) and ``read_ports`` (re-imports
    ``ki.kernel``) can point at different Kernel/DB instances.
    """
    import app.core.runtime.kernel_instance as ki
    from app.core.runtime.runtime_container import _LazyProxy, runtime

    runtime.reset()
    if not isinstance(ki.kernel, _LazyProxy):
        ki.kernel = _LazyProxy(lambda: runtime.kernel)
    yield


def _build_test_app(tmp_path, monkeypatch, *, auth_token: str = ""):
    """Fresh FastAPI app bound to an isolated tmp SQLite + data dirs."""
    import importlib

    import app.api.system
    import app.config
    import app.main
    from app.core.startup_health import enrich_with_mcp_status, run_startup_checks

    db_path = str(tmp_path / "e2e_test.db")
    monkeypatch.setenv("SQLITE_PATH", db_path)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("VECTOR_DIR", str(tmp_path / "vectors"))
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MCP_EXTERNAL_ENABLED", "false")
    # Explicit value overrides AUTH_TOKEN from .env on disk.
    monkeypatch.setenv("AUTH_TOKEN", auth_token)

    async def _noop_start_mcp_mesh() -> int:
        return 0

    async def _noop_stop_mcp_mesh() -> None:
        return None

    monkeypatch.setattr(
        "app.core.harness.mcp_lifecycle.start_mcp_mesh",
        _noop_start_mcp_mesh,
    )
    monkeypatch.setattr(
        "app.core.harness.mcp_lifecycle.stop_mcp_mesh",
        _noop_stop_mcp_mesh,
    )

    app.config.reset_settings()
    importlib.reload(app.api.system)
    # Re-register @subscribe handlers after reset_handlers() cleared them.
    # importlib.reload alone isn't enough because sub-module decorators
    # executed at first import and Python caches them.  Reload the leaf
    # modules that carry @subscribe to force re-registration.
    import app.core.agents.handlers.chat_completed_handlers as _cch
    import app.core.agents.handlers.chat_handler as _ch
    import app.core.agents.handlers.timer_trigger_handler as _th
    import app.core.runtime.handlers.approve_handlers as _ap
    import app.core.runtime.handlers.background_task_handlers as _bg
    import app.core.runtime.handlers.execute_handlers as _ex
    import app.core.runtime.handlers.inbox_poll_handlers as _inbox

    for _mod in (_ch, _cch, _ap, _ex, _bg, _inbox, _th):
        importlib.reload(_mod)
    import app.core.agents.handlers as _handlers
    import app.core.runtime.handlers as _rt_handlers
    importlib.reload(_rt_handlers)
    importlib.reload(_handlers)
    importlib.reload(app.core.runtime.agent_scheduler)
    importlib.reload(app.main)

    a = app.main.app
    a.state.startup_health = enrich_with_mcp_status(run_startup_checks())
    return a


@pytest.fixture
def app(tmp_path, monkeypatch):
    """Return the FastAPI ASGI app (no AUTH_TOKEN) for HTTP / SSE tests."""
    return _build_test_app(tmp_path, monkeypatch, auth_token="")


@pytest.fixture
def authed_app(tmp_path, monkeypatch):
    """Same as ``app`` but with AUTH_TOKEN=test-secret for auth middleware tests."""
    return _build_test_app(tmp_path, monkeypatch, auth_token="test-secret")


@pytest.fixture
def client(app):
    """Sync TestClient for route tests (api + integration).

    Does **not** enter the ASGI lifespan context: ``app`` already attaches
    startup_health, and per-test RuntimeLoop start/stop via lifespan is
    unnecessary overhead for most HTTP contract/smoke tests.
    """
    from fastapi.testclient import TestClient

    from app.core.rate_limit import reset_rate_limits

    reset_rate_limits()
    return TestClient(app)


@pytest.fixture
def authed_client(authed_app):
    """Sync TestClient with AUTH_TOKEN enabled (Bearer test-secret)."""
    from fastapi.testclient import TestClient

    from app.core.rate_limit import reset_rate_limits

    reset_rate_limits()
    return TestClient(authed_app)


@pytest.fixture
def isolated_kernel(tmp_path, monkeypatch):
    """Fresh Kernel + Database fully isolated from the global runtime."""
    from app.core.runtime.kernel.kernel import Kernel
    from app.core.runtime.runtime_container import runtime
    from app.store.database import Database

    db_path = str(tmp_path / "test.db")
    db = Database(db_path=db_path)
    k = Kernel(db=db)

    monkeypatch.setattr(runtime, "_db", db)
    monkeypatch.setattr(runtime, "_kernel", k)
    monkeypatch.setattr("app.core.runtime.kernel_instance.kernel", k)
    monkeypatch.setattr("app.store.database.db", db)
    return k, db
