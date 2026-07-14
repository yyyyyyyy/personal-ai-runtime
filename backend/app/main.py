"""Personal AI Runtime — FastAPI Application Entry Point."""

import asyncio
import json
import logging
import secrets
import time
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
    inbox,
    knowledge,
    memory,
    notifications,
    settings_api,
    system,
    telemetry_api,
    timeline,
    triggers,
    work_items,
)
from app.config import settings
from app.core.logging_config import configure_logging
from app.core.runtime.cron_registry import init_scheduler
from app.core.runtime.runtime_loop import runtime_loop
from app.core.startup_health import (
    enrich_with_mcp_status,
    record_startup_failure,
    run_startup_checks,
)
from app.version import VERSION

configure_logging()
logger = logging.getLogger(__name__)

# WebSocket connection manager for real-time notifications
_ws_connections: list[WebSocket] = []
_ws_reserved_slots = 0  # pending accept + accepted; caps concurrency
_ws_lock = Lock()
_WS_MAX_GLOBAL_CONNECTIONS = 64  # hard cap for all authenticated / loopback clients
_WS_MAX_NOAUTH_CONNECTIONS = 8  # burst rate when exposed without auth token
_WS_MAX_NOAUTH_CONCURRENT = 16  # concurrent limit when exposed without auth
_WS_NOAUTH_CONNECTION_WINDOW = 10.0  # seconds — burst window for exposed WS
_WS_NOAUTH_CONNECTION_TIMESTAMPS: list[float] = []  # under _ws_lock

# ── Request ID context ─────────────────────────────────────────────────────
# Populated by RequestIDMiddleware on every HTTP request so structured logs
# can correlate all log lines within a single request.
request_id_var: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    """Return the current request id (empty string outside a request)."""
    return request_id_var.get()


# ── Auth middleware ──────────────────────────────────────────────────────────

SKIP_AUTH_EXACT = frozenset({
    "/",
    "/api/system/health",
    "/api/system/live",
    "/docs",
    "/redoc",
    "/openapi.json",
})
# Swagger UI static assets only — never use bare "/docs" as a prefix (would
# skip auth for "/docsanything/...").
SKIP_AUTH_PREFIXES = ("/docs/", "/redoc/")


def _path_requires_auth(path: str) -> bool:
    """Return True if the request path should go through auth middleware."""
    if path in SKIP_AUTH_EXACT:
        return False
    return not any(path.startswith(prefix) for prefix in SKIP_AUTH_PREFIXES)


WS_AUTH_PREFIX = "auth."
WS_AUTH_OK = "auth.ok"
_LOCALHOST_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def _is_localhost_bind(host: str) -> bool:
    """Return True only for loopback binds (127.0.0.1, ::1, localhost).

    Everything else — wildcard binds, LAN IPs, public IPs — counts as exposed
    and requires AUTH_TOKEN unless explicitly overridden.
    """
    return host in _LOCALHOST_HOSTS or host.startswith("127.")


def _extract_client_ip(scope: Scope) -> str:
    """Return the client IP for rate-limiting, honouring X-Forwarded-For only
    when ``settings.trust_proxy_headers`` is enabled.

    Without the proxy-trust flag we use the raw socket peer. This prevents
    spoofing via a client-supplied ``X-Forwarded-For`` header. When deploying
    behind a trusted reverse proxy, set TRUST_PROXY_HEADERS=true so that
    rate-limit buckets are keyed by the real upstream client.
    """
    if settings.trust_proxy_headers:
        for name, value in scope.get("headers", []):
            if name == b"x-forwarded-for":
                # First entry is the original client; subsequent are proxy chain.
                xff = value.decode("latin-1").split(",")
                if xff:
                    ip = xff[0].strip()
                    if ip:
                        return ip
    client = scope.get("client", ("", 0))[0]
    return client or "unknown"


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


def _ws_connection_allowed() -> bool:
    """Return False when exposed-noauth WebSocket connection rate is exceeded."""
    now = time.monotonic()
    # Prune timestamps outside the window.
    cutoff = now - _WS_NOAUTH_CONNECTION_WINDOW
    while _WS_NOAUTH_CONNECTION_TIMESTAMPS and _WS_NOAUTH_CONNECTION_TIMESTAMPS[0] < cutoff:
        _WS_NOAUTH_CONNECTION_TIMESTAMPS.pop(0)
    if len(_WS_NOAUTH_CONNECTION_TIMESTAMPS) >= _WS_MAX_NOAUTH_CONNECTIONS:
        return False
    _WS_NOAUTH_CONNECTION_TIMESTAMPS.append(now)
    return True


async def _reserve_ws_connection(
    websocket: WebSocket,
    *,
    exposed_without_auth: bool,
) -> bool:
    """Atomically reserve one connection slot (before accept).

    The WebSocket is *not* added to the broadcast list until
    :func:`_register_ws_connection` runs after a successful accept.
    """
    del websocket  # slot only — broadcast list is separate
    global _ws_reserved_slots
    async with _ws_lock:
        if _ws_reserved_slots >= _WS_MAX_GLOBAL_CONNECTIONS:
            return False
        if exposed_without_auth:
            if _ws_reserved_slots >= _WS_MAX_NOAUTH_CONCURRENT:
                return False
            if not _ws_connection_allowed():
                return False
        _ws_reserved_slots += 1
        return True


async def _register_ws_connection(websocket: WebSocket) -> None:
    """Add an accepted WebSocket to the broadcast registry."""
    async with _ws_lock:
        _ws_connections.append(websocket)


async def _release_ws_connection(
    websocket: WebSocket | None,
    *,
    registered: bool = True,
) -> None:
    """Release a reserved slot and optionally remove from the broadcast list."""
    global _ws_reserved_slots
    async with _ws_lock:
        if registered and websocket is not None and websocket in _ws_connections:
            _ws_connections.remove(websocket)
        if _ws_reserved_slots > 0:
            _ws_reserved_slots -= 1


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

        # Rate limiting is always active for protected paths — independent of
        # whether AUTH_TOKEN is set. The loopback-default, no-token experience
        # is preserved but cannot be abused at high frequency.
        from app.core.rate_limit import check_rate_limit

        client_ip = _extract_client_ip(scope)

        expected = settings.auth_token
        if not expected:
            # No auth configured — rate-limit per client IP so one attacker
            # cannot exhaust the quota for all other users.
            if not check_rate_limit(path, key=client_ip):
                await self._too_many_requests(send)
                return
            await self.app(scope, receive, send)
            return

        token = self._extract_bearer(scope)
        if not _tokens_match(token, expected):
            # Invalid token — rate-limit per IP under a separate "bad-auth"
            # namespace so attackers cannot exhaust the legitimate bucket.
            if not check_rate_limit(path, key=f"bad-auth:{client_ip}"):
                await self._too_many_requests(send)
                return
            await self._unauthorized(send)
            return

        if not check_rate_limit(path, key=token):
            await self._too_many_requests(send)
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

    # Seed governance events from capability_policy.json
    try:
        from app.core.runtime.capability_governance import capability_governance
        from app.core.runtime.kernel_instance import kernel
        capability_governance.seed_from_json(kernel)
        if isinstance(app.state.startup_health, dict):
            app.state.startup_health.setdefault("checks", {})["governance_seed"] = {
                "status": "ok",
            }
    except Exception as exc:
        logger.exception("Governance seed failed")
        app.state.startup_health = record_startup_failure(
            app.state.startup_health, "governance_seed", exc
        )

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
            if isinstance(app.state.startup_health, dict):
                app.state.startup_health.setdefault("warnings", []).append(
                    f"context_pipeline degraded: {ctx_health.get('error', '(no detail)')}"
                )
                if app.state.startup_health.get("status") == "ok":
                    app.state.startup_health["status"] = "degraded"
        if isinstance(app.state.startup_health, dict):
            app.state.startup_health.setdefault("checks", {})["context_pipeline"] = ctx_health
    except Exception as exc:
        logger.exception("ContextPipeline health check failed")
        app.state.startup_health = record_startup_failure(
            app.state.startup_health, "context_pipeline", exc
        )

    # Start unified runtime loop (replaces background_worker + scheduler + timer_engine)
    try:
        await runtime_loop.start()
        if isinstance(app.state.startup_health, dict):
            app.state.startup_health.setdefault("checks", {})["runtime_loop"] = {
                "status": "ok",
            }
    except Exception as exc:
        logger.exception("RuntimeLoop failed to start — timers/reactions/background jobs inactive")
        app.state.startup_health = record_startup_failure(
            app.state.startup_health, "runtime_loop", exc
        )

    try:
        from app.core.harness.mcp_lifecycle import start_mcp_mesh

        startup_tools = await start_mcp_mesh()
        if startup_tools:
            logger.info("MCP mesh: %d tools ready at startup (lazy servers connect in background)", startup_tools)
        if isinstance(app.state.startup_health, dict):
            app.state.startup_health.setdefault("checks", {})["mcp_mesh"] = {
                "status": "ok",
                "tools": startup_tools or 0,
            }
    except Exception as exc:
        logger.exception("MCP mesh startup failed — continuing with builtin tools only")
        app.state.startup_health = record_startup_failure(
            app.state.startup_health, "mcp_mesh", exc
        )

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

    global _ws_reserved_slots
    async with _ws_lock:
        for ws in _ws_connections:
            try:
                await ws.close()
            except Exception:
                logging.getLogger(__name__).warning("Error during WebSocket shutdown", exc_info=True)
        _ws_connections.clear()
        _ws_reserved_slots = 0


# ── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Personal AI Runtime",
    description="""Personal AI Runtime — a local-first, single-user AI runtime.

**Core Capabilities:**
- **Chat** — conversational AI with tool calling and streaming
- **Work Items** — unified goals / tasks / actions tracking
- **Memory** — automated memory extraction and semantic search
- **Inbox** — email polling, reading, and sending (Gmail)
- **Approvals** — human-in-the-loop confirmation for high-risk actions
- **Knowledge Base** — document upload and RAG search
- **Telemetry** — cost, token usage, and tool call statistics
- **System** — health, data export/import/destroy, and settings

**Architecture:** Event Sourcing with append-only Event Log as single source of truth.
All data stored locally (SQLite + ChromaDB), never leaves your machine.

See [docs/README.md](https://github.com/yyyyyyyy/personal-ai-runtime/blob/main/docs/README.md)
for setup and usage instructions.""",
    version=VERSION,
    lifespan=lifespan,
)

app.add_middleware(AuthMiddleware)


class SafeErrorMiddleware:
    """Catch-all ASGI middleware — converts unhandled exceptions to JSON 500.

    Must be placed *inside* RequestIDMiddleware so request_id is still set when
    an error is logged.  This is the outermost *inner* middleware.

    Only sends an error response when the downstream app has NOT yet started
    sending a response.  If the response has already begun (e.g. a streaming
    SSE endpoint that raises mid-stream), the middleware closes the connection
    and logs — a second ``http.response.start`` would violate the ASGI spec.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        started = False

        async def _send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, _send)
        except Exception:  # exc_info=True in the logger call below uses sys.exc_info()
            if scope["type"] != "http":
                raise
            rid = scope.get("request_id") or get_request_id() or ""
            logger.error(
                "Unhandled exception in request path=%s method=%s request_id=%s started=%s",
                scope.get("path", "?"),
                scope.get("method", "?"),
                rid,
                started,
                exc_info=True,
            )
            if started:
                # Response already streaming — cannot safely inject a JSON 500.
                # Best-effort terminate the body so clients are not left hanging.
                try:
                    await send({
                        "type": "http.response.body",
                        "body": b"",
                        "more_body": False,
                    })
                except Exception:
                    pass
                return
            body = json.dumps({
                "detail": "Internal server error",
                "request_id": rid or None,
            }).encode("utf-8")
            await send({
                "type": "http.response.start",
                "status": 500,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            })
            await send({"type": "http.response.body", "body": body})


app.add_middleware(SafeErrorMiddleware)

# Starlette's latest-added middleware is outermost. Keep request IDs and CORS
# outside SafeError so generated 500 responses receive both response wrappers.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)
app.add_middleware(RequestIDMiddleware)


# Register routers
app.include_router(chat.router, prefix="/api/chat")
app.include_router(dashboard.router, prefix="/api/dashboard")
app.include_router(system.router, prefix="/api/system")
app.include_router(settings_api.router, prefix="/api/settings")
app.include_router(memory.router, prefix="/api/memory")
app.include_router(notifications.router, prefix="/api/notifications")
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
    exposed_without_auth = not expected and not _is_localhost_bind(settings.host)
    if not await _reserve_ws_connection(
        websocket,
        exposed_without_auth=exposed_without_auth,
    ):
        await websocket.close(code=4403, reason="Connection limit reached")
        return

    registered = False
    try:
        if expected:
            # Echo a fixed subprotocol — never return the raw token to the client.
            await websocket.accept(subprotocol=WS_AUTH_OK)
        else:
            if exposed_without_auth:
                logger.warning(
                    "WebSocket accepted on exposed bind (%s) without AUTH_TOKEN. "
                    "Set AUTH_TOKEN in .env for production security.",
                    settings.host,
                )
            await websocket.accept()
        await _register_ws_connection(websocket)
        registered = True

        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        await _release_ws_connection(websocket, registered=registered)


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
