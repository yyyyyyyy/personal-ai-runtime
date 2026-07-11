"""Startup health checks — validate paths, dependencies, and config at boot."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from app.config import settings, validate_storage_paths
from app.core.runtime.runtime_config import runtime_config

logger = logging.getLogger(__name__)

_MCP_FAILURE_STATUSES = frozenset({"disconnected", "unavailable"})


def _mcp_server_failed(server: dict[str, Any]) -> bool:
    """True when a server expected at startup did not connect."""
    if server.get("status") == "lazy":
        return False
    if not server.get("startup_connect", True):
        return False
    return server.get("status") in _MCP_FAILURE_STATUSES


def run_startup_checks() -> dict[str, Any]:
    """Run synchronous startup health checks. Logs warnings; never blocks boot."""
    checks: dict[str, Any] = {}
    warnings: list[str] = list(
        validate_storage_paths(settings.data_dir, settings.sqlite_path, settings.vector_dir)
    )

    data_path = Path(settings.data_dir)
    sqlite_path = Path(settings.sqlite_path)
    vector_path = Path(settings.vector_dir)

    checks["storage"] = {
        "data_dir": str(data_path),
        "sqlite_path": str(sqlite_path),
        "vector_dir": str(vector_path),
        "data_dir_exists": data_path.exists(),
        "data_dir_writable": os.access(data_path, os.W_OK) if data_path.exists() else False,
        "sqlite_exists": sqlite_path.exists(),
    }

    default_provider = next(
        (p for p in runtime_config.get_llm_config(masked=False).get("providers", []) if p.get("enabled")),
        None,
    )
    llm_configured = False
    if default_provider:
        if default_provider.get("type") == "ollama":
            llm_configured = bool(default_provider.get("base_url"))
        else:
            llm_configured = bool(default_provider.get("api_key"))
    checks["llm"] = {
        "configured": llm_configured,
        "model": default_provider.get("model", settings.llm_model) if default_provider else settings.llm_model,
        "base_url": default_provider.get("base_url", settings.llm_base_url) if default_provider else settings.llm_base_url,
    }
    if not checks["llm"]["configured"]:
        warnings.append("LLM API Key 未配置 — 对话将失败直至配置完成")

    checks["auth"] = {
        "enabled": bool(settings.auth_token),
        "host": settings.host,
    }

    email_creds = runtime_config.get_email_credentials()
    checks["email"] = {
        "configured": bool(email_creds.get("user") and email_creds.get("password")),
    }

    for warning in warnings:
        logger.warning("Startup health: %s", warning)

    status = "degraded" if warnings else "ok"
    logger.info("Startup health status=%s checks=%d warnings=%d", status, len(checks), len(warnings))
    return {"status": status, "checks": checks, "warnings": warnings}


def record_startup_failure(
    snapshot: dict[str, Any] | None,
    key: str,
    exc: BaseException,
) -> dict[str, Any]:
    """Mark a startup step as failed on the health snapshot (never raises).

    Used by lifespan so critical boot failures are visible via
    ``/api/system/health`` instead of being swallowed as DEBUG logs.
    """
    if not isinstance(snapshot, dict):
        snapshot = {"status": "degraded", "checks": {}, "warnings": []}
    snapshot.setdefault("checks", {})[key] = {
        "status": "failed",
        "error": str(exc),
    }
    snapshot.setdefault("warnings", []).append(f"{key} failed: {exc}")
    if snapshot.get("status") == "ok":
        snapshot["status"] = "degraded"
    return snapshot


def enrich_with_mcp_status(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Attach MCP mesh status after async startup connect."""
    try:
        from app.core.harness.mcp_mesh import mcp_mesh

        mcp_status = mcp_mesh.get_server_status()
        snapshot.setdefault("checks", {})["mcp"] = mcp_status
        failed = [
            s["name"]
            for s in mcp_status.get("servers", [])
            if _mcp_server_failed(s)
        ]
        if failed:
            snapshot.setdefault("warnings", []).append(
                f"MCP servers failed to connect: {', '.join(failed)}"
            )
            if snapshot.get("status") == "ok":
                snapshot["status"] = "degraded"
    except Exception as exc:
        logger.warning("Startup health: MCP status unavailable: %s", exc)
        snapshot.setdefault("checks", {})["mcp"] = {"error": str(exc)}
    return snapshot


def _summarize_mcp_for_public(mcp_status: dict[str, Any]) -> dict[str, Any]:
    """Strip MCP status down to connection counts for unauthenticated callers."""
    servers = mcp_status.get("servers", [])
    return {
        "total": len(servers),
        "connected": sum(1 for s in servers if s.get("status") == "connected"),
        "failed": sum(1 for s in servers if _mcp_server_failed(s)),
    }


def sanitize_startup_for_public(snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return a public-safe view of startup diagnostics (no paths or secrets)."""
    if not snapshot:
        return snapshot

    checks = snapshot.get("checks", {})
    storage = checks.get("storage", {})
    llm = checks.get("llm", {})
    auth_check = checks.get("auth", {})

    public_checks: dict[str, Any] = {
        "storage": {
            "data_dir_exists": storage.get("data_dir_exists"),
            "data_dir_writable": storage.get("data_dir_writable"),
            "sqlite_exists": storage.get("sqlite_exists"),
        },
        "llm": {
            "configured": llm.get("configured"),
            "model": llm.get("model"),
        },
        "auth": {"enabled": auth_check.get("enabled")},
        "email": checks.get("email", {}),
    }
    if "mcp" in checks:
        mcp = checks["mcp"]
        if isinstance(mcp, dict) and "servers" in mcp:
            public_checks["mcp"] = _summarize_mcp_for_public(mcp)
        elif isinstance(mcp, dict) and "error" in mcp:
            public_checks["mcp"] = {"error": True}

    # Status-only view of lifespan step results (no exception text).
    for key in ("governance_seed", "runtime_loop", "context_pipeline"):
        entry = checks.get(key)
        if not isinstance(entry, dict):
            continue
        status = entry.get("status") or entry.get("fragment_registration")
        if status is not None:
            public_checks[key] = {"status": status}

    return {
        "status": snapshot.get("status"),
        "warning_count": len(snapshot.get("warnings", [])),
        "checks": public_checks,
    }
