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

# Fields allowed on the unauthenticated /health startup payload.
_PUBLIC_STORAGE_FIELDS = frozenset({
    "data_dir_exists",
    "data_dir_writable",
    "sqlite_exists",
})
_PUBLIC_LLM_FIELDS = frozenset({"configured"})
_PUBLIC_AUTH_FIELDS = frozenset({"enabled"})
_PUBLIC_EMAIL_FIELDS = frozenset({"configured"})
# Named checks handled explicitly below; everything else with a status field
# is projected as status-only so new lifespan keys need no whitelist update.
_NAMED_PUBLIC_CHECKS = frozenset({"storage", "llm", "auth", "email", "mcp"})


def _mcp_server_failed(server: dict[str, Any]) -> bool:
    """True when a server expected at startup did not connect."""
    if server.get("status") == "lazy":
        return False
    if not server.get("startup_connect", True):
        return False
    return server.get("status") in _MCP_FAILURE_STATUSES


def _pick_fields(source: dict[str, Any], allowed: frozenset[str]) -> dict[str, Any]:
    return {key: source[key] for key in allowed if key in source}


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
    """Return a public-safe view of startup diagnostics (no paths, secrets, or error text)."""
    if not snapshot:
        return snapshot

    checks = snapshot.get("checks", {})
    if not isinstance(checks, dict):
        checks = {}

    public_checks: dict[str, Any] = {}

    storage = checks.get("storage")
    if isinstance(storage, dict):
        public_checks["storage"] = _pick_fields(storage, _PUBLIC_STORAGE_FIELDS)

    llm = checks.get("llm")
    if isinstance(llm, dict):
        public_checks["llm"] = _pick_fields(llm, _PUBLIC_LLM_FIELDS)

    auth_check = checks.get("auth")
    if isinstance(auth_check, dict):
        public_checks["auth"] = _pick_fields(auth_check, _PUBLIC_AUTH_FIELDS)

    email = checks.get("email")
    if isinstance(email, dict):
        public_checks["email"] = _pick_fields(email, _PUBLIC_EMAIL_FIELDS)

    mcp = checks.get("mcp")
    if isinstance(mcp, dict):
        if "servers" in mcp:
            public_checks["mcp"] = _summarize_mcp_for_public(mcp)
        elif "error" in mcp:
            # Never expose exception text to unauthenticated callers.
            public_checks["mcp"] = {"error": True}

    for key, entry in checks.items():
        if key in _NAMED_PUBLIC_CHECKS or key in public_checks:
            continue
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
