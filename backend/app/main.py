"""Personal AI Runtime — FastAPI Application Entry Point."""

import asyncio
import json
import logging
import secrets
import uuid
from asyncio import Lock
from collections.abc import MutableMapping
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from app.api import (
    approvals,
    background_tasks,
    chat,
    connectors,
    dashboard,
    goals,
    inbox,
    knowledge,
    memory,
    notifications,
    settings_api,
    system,
    tasks,
    telemetry_api,
    timeline,
    triggers,
    work_items,
)
from app.config import settings
from app.core.logging_config import configure_logging
from app.core.runtime.cron_registry import init_scheduler
from app.core.runtime.runtime_loop import runtime_loop
from app.core.startup_health import enrich_with_mcp_status, run_startup_checks
from app.version import VERSION

configure_logging()
logger = logging.getLogger(__name__)

# WebSocket connection manager for real-time notifications
_ws_connections: list[WebSocket] = []
_ws_lock = Lock()

# ── Request ID context ─────────────────────────────────────────────────────
# Populated by RequestIDMiddleware on every HTTP request so structured logs
# can correlate all log lines within a single request.
request_id_var: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    """Return the current request id (empty string outside a request)."""
    return request_id_var.get()


# ── Auth middleware ──────────────────────────────────────────────────────────

SKIP_AUTH_PATHS = frozenset({"/", "/api/system/health", "/api/system/live", "/docs", "/redoc", "/openapi.json"})


def _path_requires_auth(path: str) -> bool:
    """Return True if the request path should go through auth middleware.

    Uses prefix matching so that new paths under /docs/ (e.g. /docs/css/style.css)
    and /api/system/health* variants are also skipped.
    The root path "/" is matched exactly (otherwise it would match everything).
    """
    for prefix in SKIP_AUTH_PATHS:
        if prefix == "/":
            if path == "/":
                return False
            continue
        if path == prefix or path.startswith(prefix.rstrip("/") + "/"):
            return False
    return True
WS_AUTH_PREFIX = "auth."
WS_AUTH_OK = "auth.ok"
_LOCALHOST_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def _is_localhost_bind(host: str) -> bool:
    """Return True only for loopback binds (127.0.0.1, ::1, localhost).

    Everything else — wildcard binds, LAN IPs, public IPs — counts as exposed
    and requires AUTH_TOKEN unless explicitly overridden.
    """
    return host in _LOCALHOST_HOSTS or host.startswith("127.")


def _tokens_match(provided: str, expected: str) -> bool:
    if not provided or not expected:
        return False
    return secrets.compare_digest(provided, expected)


def _extract_ws_token(websocket: WebSocket) -> str:
    header = websocket.headers.get("sec-websocket-protocol", "")
    for part in header.split(","):
        part = part.strip()
        if part.startswith(WS_AUTH_PREFIX):
            return part[len(WS_AUTH_PREFIX) :]
    return ""


class AuthMiddleware:
    """Pure ASGI Bearer Token middleware for local-first API protection.

    Implemented as a raw ASGI middleware (not BaseHTTPMiddleware) so that
    streaming responses — notably the chat SSE endpoint — pass through
    unbuffered. BaseHTTPMiddleware buffers the full response body, which
    breaks token-level streaming.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            # WebSocket and other non-HTTP scopes pass through untouched;
            # WebSocket auth is handled in the websocket_endpoint directly.
            await self.app(scope, receive, send)
            return

        path = scope["path"]
        if not _path_requires_auth(path):
            await self.app(scope, receive, send)
            return

        expected = settings.auth_token
        if not expected:
            await self.app(scope, receive, send)
            return

        # Rate limiting for sensitive endpoints (only when auth is enabled)
        from app.core.rate_limit import check_rate_limit
        if not check_rate_limit(path):
            await self._too_many_requests(send)
            return

        token = self._extract_bearer(scope)
        if not _tokens_match(token, expected):
            await self._unauthorized(send)
            return

        await self.app(scope, receive, send)

    @staticmethod
    def _extract_bearer(scope: Scope) -> str:
        for header_name, header_value in scope.get("headers", []):
            if header_name == b"authorization":
                value = header_value.decode("latin-1")
                if value.startswith("Bearer "):
                    return value[7:]
        return ""

    @staticmethod
    async def _unauthorized(send: Send) -> None:
        # Minimal ASGI 401 response without touching the downstream app.
        body = json.dumps(
            {"detail": "Unauthorized: missing or invalid Bearer token"}
        ).encode("utf-8")
        await send({
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        })
        await send({"type": "http.response.body", "body": body})

    @staticmethod
    async def _too_many_requests(send: Send) -> None:
        body = json.dumps(
            {"detail": "Too many requests. Please slow down."}
        ).encode("utf-8")
        await send({
            "type": "http.response.start",
            "status": 429,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        })
        await send({"type": "http.response.body", "body": body})


class RequestIDMiddleware:
    """Assigns/generates an X-Request-ID and stores it in a ContextVar.

    Reads the inbound ``X-Request-ID`` header if present (so upstream
    proxies can propagate their own id), otherwise generates a uuid4.
    The value is exposed via ``request_id_var`` so any logger processor
    can attach it to structured log lines.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        rid = ""
        for name, value in scope.get("headers", []):
            if name == b"x-request-id":
                rid = value.decode("latin-1")
                break
        if not rid:
            rid = uuid.uuid4().hex[:16]

        token = request_id_var.set(rid)
        scope.setdefault("request_id", rid)

        async def _send(message: "MutableMapping[str, Any]") -> None:
            if message.get("type") == "http.response.start":
                headers = list(message.get("headers") or [])
                headers.append((b"x-request-id", rid.encode("latin-1")))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, _send)
        finally:
            request_id_var.reset(token)


# ── Lifespan ─────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    app.state.startup_health = run_startup_checks()

    app.state._auth_warning_interval = 600  # seconds between repeated warnings

    if not settings.auth_token:
        if not _is_localhost_bind(settings.host):
            if not settings.allow_no_auth_on_exposed:
                import sys
                logger.critical(
                    "REJECTED: AUTH_TOKEN is not set while listening on %s. "
                    "Set AUTH_TOKEN in .env or ALLOW_NO_AUTH_ON_EXPOSED=true to override.",
                    settings.host,
                )
                sys.exit(1)
            logger.warning(
                "AUTH_TOKEN is not set while listening on %s — ALLOW_NO_AUTH_ON_EXPOSED is enabled. "
                "Set AUTH_TOKEN in .env for production security.",
                settings.host,
            )
            # Periodic warning to prevent one-time messages from being buried
            app.state._auth_exposed_no_token = True
            app.state._last_auth_warning_at = 0.0
        else:
            logger.warning(
                "AUTH_TOKEN is not set — API authentication disabled (localhost bind)."
            )
    else:
        logger.info("API authentication enabled (Bearer token)")

    init_scheduler()

    # Seed governance events from capability_policy.json (v0.4.0: unified governance)
    try:
        from app.core.runtime.capability_governance import capability_governance
        from app.core.runtime.kernel_instance import kernel
        capability_governance.seed_from_json(kernel)
    except Exception:
        logger.debug("Governance seed skipped (test context)")

    # Surface fragment registration health on startup. Registration runs in
    # the ContextPipeline constructor (lazy via RuntimeContainer); we trigger
    # a build here so failures show up in /api/system/health instead of
    # silently degrading chat quality on the first request.
    try:
        from app.core.runtime.runtime_container import runtime
        ctx_health = runtime.context_pipeline.health_check()
        if ctx_health.get("fragment_registration") != "ok":
            logger.warning(
                "Context fragment registration is degraded: %s",
                ctx_health.get("error", "(no detail)"),
            )
        # Stash on startup_health so /api/system/health can report it.
        if isinstance(app.state.startup_health, dict):
            app.state.startup_health["context_pipeline"] = ctx_health
    except Exception:
        logger.debug("ContextPipeline health check skipped (test context)")

    # Start unified runtime loop (replaces background_worker + scheduler + timer_engine)
    try:
        await runtime_loop.start()
    except Exception:
        logger.debug("RuntimeLoop skipped (test context)")

    try:
        from app.core.harness.mcp_lifecycle import start_mcp_mesh

        startup_tools = await start_mcp_mesh()
        if startup_tools:
            logger.info("MCP mesh: %d tools ready at startup (lazy servers connect in background)", startup_tools)
    except Exception:
        logger.exception("MCP mesh startup failed — continuing with builtin tools only")

    app.state.startup_health = enrich_with_mcp_status(app.state.startup_health)

    # Start periodic auth warning if exposed without token
    _auth_warn_task = None
    if getattr(app.state, "_auth_exposed_no_token", False):
        async def _auth_warning_loop():
            while True:
                await asyncio.sleep(app.state._auth_warning_interval)
                logger.warning(
                    "SECURITY: API running on %s with no AUTH_TOKEN (ALLOW_NO_AUTH_ON_EXPOSED=true). "
                    "All data is accessible without authentication.",
                    settings.host,
                )
        _auth_warn_task = asyncio.create_task(_auth_warning_loop())

    yield

    from app.core.harness.mcp_lifecycle import stop_mcp_mesh

    await stop_mcp_mesh()

    if _auth_warn_task is not None:
        _auth_warn_task.cancel()
        try:
            await _auth_warn_task
        except asyncio.CancelledError:
            pass

    await runtime_loop.stop()

    async with _ws_lock:
        for ws in _ws_connections:
            try:
                await ws.close()
            except Exception:
                logging.getLogger(__name__).warning("Error during WebSocket shutdown", exc_info=True)
        _ws_connections.clear()


# ── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Personal AI Runtime",
    description="""Personal AI Runtime — a local-first, single-user AI runtime.

**Core Capabilities:**
- **Chat** — conversational AI with tool calling and streaming
- **Goals & Tasks** — goal tracking with progress and subtasks
- **Memory** — automated memory extraction and semantic search
- **Inbox** — email polling, reading, and sending (Gmail)
- **Approvals** — human-in-the-loop confirmation for high-risk actions
- **Knowledge Base** — document upload and RAG search
- **Telemetry** — cost, token usage, and tool call statistics
- **System** — health, data export/import/destroy, and settings

**Architecture:** Event Sourcing with append-only Event Log as single source of truth.
All data stored locally (SQLite + ChromaDB), never leaves your machine.

See [USER_GUIDE.md](https://github.com/yyyyyyyy/personal-ai-runtime/blob/main/docs/USER_GUIDE.md)
for setup and usage instructions.""",
    version=VERSION,
    lifespan=lifespan,
)

app.add_middleware(AuthMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)

# RequestIDMiddleware is added last so it wraps everything else (outermost):
# the request id must be available before AuthMiddleware logs anything.
app.add_middleware(RequestIDMiddleware)

# Register routers
app.include_router(chat.router, prefix="/api/chat")
app.include_router(dashboard.router, prefix="/api/dashboard")
app.include_router(system.router, prefix="/api/system")
app.include_router(settings_api.router, prefix="/api/settings")
app.include_router(memory.router, prefix="/api/memory")
app.include_router(goals.router, prefix="/api/goals")
app.include_router(notifications.router, prefix="/api/notifications")
app.include_router(tasks.router, prefix="/api/tasks")
app.include_router(telemetry_api.router, prefix="/api/telemetry")
app.include_router(approvals.router, prefix="/api/approvals")
app.include_router(background_tasks.router, prefix="/api/tasks/background")
app.include_router(triggers.router, prefix="/api/triggers")
app.include_router(inbox.router, prefix="/api/inbox")
app.include_router(connectors.router, prefix="/api/connectors")
app.include_router(timeline.router, prefix="/api/timeline")
app.include_router(knowledge.router, prefix="/api/knowledge")
app.include_router(work_items.router, prefix="/api/work-items")


@app.get("/")
async def root():
    response_body: dict = {
        "message": "Personal AI Runtime is running",
        "docs": "/docs",
    }
    if getattr(app.state, "_auth_exposed_no_token", False):
        response_body["SECURITY_WARNING"] = (
            "API is running on an exposed host without authentication. "
            "Set AUTH_TOKEN in .env to enable Bearer token protection."
        )
    return response_body


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket for real-time notification pushing."""
    expected = settings.auth_token
    if expected:
        token = _extract_ws_token(websocket)
        if not _tokens_match(token, expected):
            await websocket.close(code=4401, reason="Unauthorized")
            return
        # Echo a fixed subprotocol — never return the raw token to the client.
        await websocket.accept(subprotocol=WS_AUTH_OK)
    else:
        await websocket.accept()
    async with _ws_lock:
        _ws_connections.append(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        async with _ws_lock:
            if websocket in _ws_connections:
                _ws_connections.remove(websocket)


async def broadcast_notification(event: dict) -> None:
    """Broadcast a notification event to all connected WebSocket clients.

    Cleanly removes disconnected clients so a single stale connection
    does not block the entire broadcast.
    """
    message = json.dumps(event)
    disconnected: list[WebSocket] = []
    async with _ws_lock:
        connections = list(_ws_connections)
    for ws in connections:
        try:
            await ws.send_text(message)
        except WebSocketDisconnect:
            disconnected.append(ws)
        except Exception as exc:
            logger.warning("WebSocket broadcast failed: %s", exc)
            disconnected.append(ws)

    if disconnected:
        async with _ws_lock:
            for ws in disconnected:
                if ws in _ws_connections:
                    _ws_connections.remove(ws)
