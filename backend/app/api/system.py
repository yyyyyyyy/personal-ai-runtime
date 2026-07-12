"""System API — health checks, LLM providers, data sovereignty, and system info."""

import asyncio
import secrets
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.api.models import (
    EncryptedExportRequest,
    EncryptedImportRequest,
    ExportRequest,
    ImportRequest,
)
from app.config import settings
from app.core.agents.llm_failover import llm_router
from app.core.runtime.kernel_instance import kernel
from app.core.startup_health import sanitize_startup_for_public
from app.version import VERSION

router = APIRouter(tags=["system"])


def _request_has_valid_auth(request: Request) -> bool:
    expected = settings.auth_token
    if not expected:
        return False
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return False
    return secrets.compare_digest(auth_header[7:], expected)

EXPORT_CONFIRM = "EXPORT_ALL_DATA"
DESTROY_CONFIRM = "DESTROY_ALL_DATA"
IMPORT_CONFIRM = "DESTROY_AND_IMPORT"


@router.get("/health")
async def health_check(request: Request):
    """Health check endpoint with startup diagnostics.

    Use /live for liveness probes (no DB dependency).
    """
    startup = getattr(request.app.state, "startup_health", None)
    if startup and not _request_has_valid_auth(request):
        startup = sanitize_startup_for_public(startup)
    return {
        "status": startup.get("status", "ok") if startup else "ok",
        "service": "personal-ai-runtime",
        "version": VERSION,
        "auth_required": bool(settings.auth_token),
        "startup": startup,
    }


@router.get("/live")
async def liveness():
    """Liveness probe — returns 200 as long as the process is running.

    No DB or LLM dependencies. Safe for Docker healthcheck.
    """
    return {"status": "ok", "service": "personal-ai-runtime"}


@router.get("/ready")
async def readiness(request: Request):
    """Readiness probe — checks DB is initialised and writable.

    Safe for k8s readiness probes; Docker healthcheck can use /live instead.
    """
    from app.core.runtime.kernel_instance import kernel
    try:
        kernel.table_counts(("event_log",))
    except Exception:
        raise HTTPException(status_code=503, detail="Database not ready")
    return {"status": "ok", "service": "personal-ai-runtime"}


@router.get("/llm-providers")
async def list_llm_providers():
    """List all configured LLM providers."""
    return {
        "providers": llm_router.list_providers(),
        "default": llm_router.get_default_model(),
    }


@router.get("/info")
async def system_info():
    """Get system information."""
    from app.core.runtime.kernel_instance import kernel

    counts = kernel.table_counts(
        ("conversations", "messages", "event_log", "memories")
    )

    # goals table was dropped in v06; goal count comes from work_items now.
    from app.core.runtime import read_ports
    goal_count = len(read_ports.query_goals(limit=10000))

    # Count legacy app events (aggregate_type='event') via kernel
    legacy_event_count = kernel.count_events("event")

    return {
        "conversations": counts["conversations"],
        "messages": counts["messages"],
        "goals": goal_count,
        "event_log": counts["event_log"],
        "events": legacy_event_count,
        "memories": counts["memories"],
        "llm_providers": len(llm_router.list_providers()),
    }


@router.get("/mcp-status")
async def mcp_status():
    """Return external MCP server connection status."""
    from app.core.harness.mcp_mesh import mcp_mesh

    return mcp_mesh.get_server_status()


@router.post("/export")
async def export_all_data(body: ExportRequest | None = None):
    """Export complete personal data snapshot as streamed JSON.

    Body is identical to ``kernel.snapshot()`` wire format so import/restore
    stay compatible. Streaming avoids buffering the full serialized document
    in the ASGI response layer.
    """
    payload = body or ExportRequest()
    if payload.confirm != EXPORT_CONFIRM:
        raise HTTPException(
            status_code=400,
            detail=f"Set confirm='{EXPORT_CONFIRM}' to export",
        )
    filename = f"personal-ai-backup-{datetime.now(UTC).strftime('%Y-%m-%d')}.json"
    return StreamingResponse(
        kernel.iter_snapshot_json_chunks(),
        media_type="application/json; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )

@router.post("/import")
async def import_all_data(body: ImportRequest):
    """Import personal data snapshot. Requires confirm code when not read_only."""
    read_only = body.read_only
    if not read_only and body.confirm != IMPORT_CONFIRM:
        raise HTTPException(
            status_code=400,
            detail=f"Set confirm='{IMPORT_CONFIRM}' for write import",
        )
    return await asyncio.to_thread(
        kernel.restore,
        body.data,
        read_only=read_only,
    )


@router.delete("/data")
async def destroy_all_data(confirm: str = ""):
    """Destroy all local data. Requires confirm code via query parameter.
    Usage: DELETE /api/system/data?confirm=DESTROY_ALL_DATA
    """
    if confirm != DESTROY_CONFIRM:
        raise HTTPException(
            status_code=400,
            detail=f"Query parameter confirm must be '{DESTROY_CONFIRM}'",
        )
    return await asyncio.to_thread(kernel.erase)


# --- Encrypted Sync (Phase 2) ---

@router.post("/export/encrypted")
async def export_encrypted(body: EncryptedExportRequest):
    """Export with AES-GCM encryption using a user-provided passphrase.

    Password is read from the request body (not query) to keep it out of
    access logs and shell history. Returns a base64-encoded encrypted blob
    suitable for cross-device transfer. Use /api/system/import/encrypted to
    restore.
    """
    if body.confirm != EXPORT_CONFIRM:
        raise HTTPException(
            status_code=400,
            detail=f"Set confirm='{EXPORT_CONFIRM}' to export",
        )

    from app.product.encrypted_sync import (
        BLOB_FORMAT,
        EncryptedSyncError,
        encrypt_snapshot,
    )

    snapshot = kernel.snapshot()

    try:
        blob = await encrypt_snapshot(snapshot, body.password)
    except EncryptedSyncError:
        raise HTTPException(status_code=400, detail="Encryption failed — check password and data integrity")

    return {"format": BLOB_FORMAT, "data": blob, "size_bytes": len(blob)}


@router.post("/import/encrypted")
async def import_encrypted(body: EncryptedImportRequest):
    """Import previously encrypted export blob.

    Requires the same confirm code as plaintext write import, because the
    underlying path rewrites event_log (drops append-only triggers, clears,
    reinserts). Password is read from the request body.
    """
    if body.confirm != IMPORT_CONFIRM:
        raise HTTPException(
            status_code=400,
            detail=f"Set confirm='{IMPORT_CONFIRM}' for encrypted write import",
        )

    from app.product.encrypted_sync import EncryptedSyncError, decrypt_snapshot

    try:
        snapshot = await decrypt_snapshot(body.data, body.password)
    except EncryptedSyncError:
        raise HTTPException(status_code=400, detail="Decryption failed — check password and data integrity")

    result = await asyncio.to_thread(kernel.restore, snapshot, read_only=False)
    return {"status": "ok", "events_imported": result.get("events_imported", 0)}


# --- Demo endpoint (Phase 1: Model Continuity Demo) ---

@router.get("/demo/model-continuity")
async def model_continuity_demo():
    """Return current model & memory stats for the Phase 1 model-switch demo."""
    from app.core.runtime.kernel_instance import kernel
    counts = kernel.table_counts(("memories", "event_log"))
    return {
        "model": settings.llm_model,
        "base_url": settings.llm_base_url,
        "total_memories": counts.get("memories", 0),
        "total_events": counts.get("event_log", 0),
        "message": "你的记忆已安全存储。切换到任何模型，记忆都不会丢失。",
    }
