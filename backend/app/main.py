"""Personal AI Runtime — FastAPI Application Entry Point."""

import asyncio
import json
import logging
import secrets
from asyncio import Lock
from contextlib import asynccontextmanager

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
    workflows,
)
from app.config import settings
from app.core.logging_config import configure_logging
from app.core.runtime.background_worker import background_worker
from app.core.runtime.scheduler import init_scheduler, shutdown_scheduler
from app.core.startup_health import enrich_with_mcp_status, run_startup_checks

configure_logging()
logger = logging.getLogger(__name__)

# WebSocket connection manager for real-time notifications
_ws_connections: list[WebSocket] = []
_ws_lock = Lock()

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
_EXPOSED_HOSTS = frozenset({"0.0.0.0", "::"})


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


# ── Lifespan ─────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    app.state.startup_health = run_startup_checks()

    app.state._auth_warning_interval = 600  # seconds between repeated warnings

    if not settings.auth_token:
        if settings.host in _EXPOSED_HOSTS:
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
        elif settings.host not in _LOCALHOST_HOSTS:
            logger.warning(
                "AUTH_TOKEN is not set while listening on %s — set AUTH_TOKEN for non-localhost binds.",
                settings.host,
            )
        else:
            logger.warning(
                "AUTH_TOKEN is not set — API authentication disabled (localhost bind)."
            )
    else:
        logger.info("API authentication enabled (Bearer token)")

    init_scheduler()

    # Seed governance events from capability_policy.json
    from app.core.runtime.capability_policy import capability_policy
    from app.core.runtime.kernel_instance import kernel
    capability_policy.seed_from_json(kernel)

    await background_worker.start()

    from app.core.runtime.trigger_engine import trigger_engine

    trigger_engine.seed_builtin_triggers()

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

    await background_worker.stop()
    shutdown_scheduler()

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
    version="local",
    lifespan=lifespan,
)

app.add_middleware(AuthMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["X-Request-ID"],
)

# Register routers
app.include_router(chat.router)
app.include_router(dashboard.router)
app.include_router(system.router)
app.include_router(settings_api.router)
app.include_router(memory.router)
app.include_router(goals.router)
app.include_router(notifications.router)
app.include_router(tasks.router)
app.include_router(telemetry_api.router)
app.include_router(approvals.router)
app.include_router(background_tasks.router)
app.include_router(triggers.router)
app.include_router(inbox.router)
app.include_router(connectors.router)
app.include_router(timeline.router)
app.include_router(knowledge.router)
app.include_router(workflows.router)


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
