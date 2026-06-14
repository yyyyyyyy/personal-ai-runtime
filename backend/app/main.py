"""Personal AI Runtime — FastAPI Application Entry Point."""

import json
import logging
import secrets
from asyncio import Lock
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.api import (
    approvals,
    background_tasks,
    chat,
    events,
    goals,
    inbox,
    knowledge,
    memory,
    notifications,
    reviews,
    settings_api,
    system,
    tasks,
    telemetry_api,
    triggers,
)
from app.config import settings
from app.core.runtime.background_worker import background_worker
from app.core.runtime.event_bus import event_bus
from app.core.runtime.kernel_event_bridge import register_kernel_event_bridge
from app.core.runtime.pattern.aggregators import pattern_aggregator
from app.core.runtime.scheduler_v2 import init_scheduler_v2, shutdown_scheduler_v2
from app.core.startup_health import enrich_with_mcp_status, run_startup_checks

logger = logging.getLogger(__name__)

# WebSocket connection manager for real-time notifications
_ws_connections: list[WebSocket] = []
_ws_lock = Lock()

# ── Auth middleware ──────────────────────────────────────────────────────────

SKIP_AUTH_PATHS = frozenset({"/", "/api/system/health", "/docs", "/redoc", "/openapi.json"})
WS_AUTH_PREFIX = "auth."
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


class AuthMiddleware(BaseHTTPMiddleware):
    """Simple Bearer Token middleware for local-first API protection."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path in SKIP_AUTH_PATHS:
            return await call_next(request)

        expected = settings.auth_token
        if not expected:
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        token = ""
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

        if not _tokens_match(token, expected):
            return JSONResponse(
                status_code=401,
                content={"detail": "Unauthorized: missing or invalid Bearer token"},
            )

        return await call_next(request)


# ── Lifespan ─────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    app.state.startup_health = run_startup_checks()

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
                "AUTH_TOKEN is not set while listening on %s — ALLOW_NO_AUTH_ON_EXPOSED is enabled.",
                settings.host,
            )
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

    await event_bus.start()
    register_kernel_event_bridge()

    pattern_aggregator.start()

    init_scheduler_v2()

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

    yield

    from app.core.harness.mcp_lifecycle import stop_mcp_mesh

    await stop_mcp_mesh()

    await background_worker.stop()
    pattern_aggregator.stop()
    shutdown_scheduler_v2()
    await event_bus.stop()

    async with _ws_lock:
        for ws in _ws_connections:
            try:
                await ws.close()
            except Exception:
                pass
        _ws_connections.clear()


# ── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Personal AI Runtime",
    description="Your second brain and execution engine — Runtime Foundation",
    version="0.9.0",
    lifespan=lifespan,
)

app.add_middleware(AuthMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# Register routers
app.include_router(chat.router)
app.include_router(system.router)
app.include_router(settings_api.router)
app.include_router(memory.router)
app.include_router(events.router)
app.include_router(knowledge.router)
app.include_router(goals.router)
app.include_router(reviews.router)
app.include_router(notifications.router)
app.include_router(tasks.router)
app.include_router(telemetry_api.router)
app.include_router(approvals.router)
app.include_router(background_tasks.router)
app.include_router(triggers.router)
app.include_router(inbox.router)


@app.get("/")
async def root():
    return {
        "message": "Personal AI Runtime is running",
        "version": "0.9.0",
        "docs": "/docs",
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket for real-time notification pushing."""
    expected = settings.auth_token
    subprotocol: str | None = None
    if expected:
        token = _extract_ws_token(websocket)
        if not _tokens_match(token, expected):
            await websocket.close(code=4401, reason="Unauthorized")
            return
        subprotocol = f"{WS_AUTH_PREFIX}{token}"

    await websocket.accept(subprotocol=subprotocol)
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
