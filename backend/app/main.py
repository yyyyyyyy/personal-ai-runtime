"""Personal AI OS — FastAPI Application Entry Point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api import chat, system, memory, events, knowledge, goals, reviews, notifications
from app.core.scheduler import init_scheduler, shutdown_scheduler

# WebSocket connection manager for real-time notifications
_ws_connections: list[WebSocket] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    init_scheduler()
    yield
    shutdown_scheduler()
    for ws in _ws_connections:
        try:
            await ws.close()
        except Exception:
            pass


app = FastAPI(
    title="Personal AI OS",
    description="Your second brain and execution engine",
    version="0.4.0",
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


@app.get("/")
async def root():
    return {"message": "Personal AI OS is running", "version": "0.4.0"}


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
