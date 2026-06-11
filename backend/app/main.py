"""Personal AI Runtime — FastAPI Application Entry Point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

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
    system,
    tasks,
    telemetry_api,
    trajectories,
    triggers,
)
from app.config import settings
from app.core.runtime.background_worker import background_worker
from app.core.runtime.event_bus import event_bus
from app.core.runtime.kernel_event_bridge import register_kernel_event_bridge
from app.core.runtime.pattern.aggregators import pattern_aggregator
from app.core.runtime.scheduler_v2 import init_scheduler_v2, shutdown_scheduler_v2

# WebSocket connection manager for real-time notifications
_ws_connections: list[WebSocket] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Start Event Bus and wire Kernel → Bus bridge before scheduler subscriptions
    await event_bus.start()
    register_kernel_event_bridge()

    # Start Pattern Aggregator (Evidence → Pattern layer)
    pattern_aggregator.start()

    init_scheduler_v2()

    # Start background worker
    await background_worker.start()

    from app.core.runtime.trigger_engine import trigger_engine
    trigger_engine.seed_builtin_triggers()

    yield

    # Shutdown
    await background_worker.stop()
    pattern_aggregator.stop()
    shutdown_scheduler_v2()
    await event_bus.stop()

    for ws in _ws_connections:
        try:
            await ws.close()
        except Exception:
            pass


app = FastAPI(
    title="Personal AI Runtime",
    description="Your second brain and execution engine — Runtime Foundation",
    version="0.9.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(chat.router)
app.include_router(system.router)
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
if settings.experimental_trajectory_enabled:
    app.include_router(trajectories.router)


@app.get("/")
async def root():
    return {"message": "Personal AI Runtime is running", "version": "0.9.0"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket for real-time notification pushing."""
    await websocket.accept()
    _ws_connections.append(websocket)
    try:
        while True:
            # Keep connection alive, listen for pings
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in _ws_connections:
            _ws_connections.remove(websocket)


async def broadcast_notification(event: dict):
    """Broadcast a notification event to all connected WebSocket clients."""
    import json
    message = json.dumps(event)
    for ws in _ws_connections:
        try:
            await ws.send_text(message)
        except Exception:
            pass
