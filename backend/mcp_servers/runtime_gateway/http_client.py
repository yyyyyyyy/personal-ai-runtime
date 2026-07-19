"""HTTP client for the Runtime Gateway — talks to the local PAR backend only."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

_HTTP_TIMEOUT_S = 15.0
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

logger = logging.getLogger("runtime_gateway.http")

_RAW_BASE_URL = os.environ.get("PAR_BASE_URL", "http://localhost:8000")
_BASE_URL: str | None = None
AUTH_TOKEN = os.environ.get("PAR_AUTH_TOKEN", "")


def env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes"}


def validate_base_url(raw: str) -> str:
    """Reject non-local PAR_BASE_URL unless PAR_ALLOW_REMOTE=1."""
    url = raw.strip().rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(f"PAR_BASE_URL must be an absolute http(s) URL, got {raw!r}")
    host = (parsed.hostname or "").lower()
    if not env_flag("PAR_ALLOW_REMOTE") and host not in _LOCAL_HOSTS:
        raise ValueError(
            f"PAR_BASE_URL host {host!r} is not local; "
            "set PAR_ALLOW_REMOTE=1 to allow remote backends"
        )
    return url


def configure_base_url(raw: str | None = None) -> str:
    """Validate and pin the backend base URL (call from main / tests)."""
    global _RAW_BASE_URL, _BASE_URL
    if raw is not None:
        _RAW_BASE_URL = raw
    _BASE_URL = validate_base_url(_RAW_BASE_URL)
    return _BASE_URL


def get_base_url() -> str:
    """Lazy-validate on first use so import never crashes on bad env."""
    global _BASE_URL
    if _BASE_URL is None:
        _BASE_URL = validate_base_url(_RAW_BASE_URL)
    return _BASE_URL


def reset_base_url_cache() -> None:
    """Clear cached URL — for tests only."""
    global _BASE_URL
    _BASE_URL = None


@dataclass(frozen=True, slots=True)
class HttpResult:
    """Outcome of one backend HTTP call."""

    ok: bool
    status: int | None = None
    data: Any = None
    error: str | None = None


def request(method: str, path: str, body: dict | None = None) -> HttpResult:
    """Call ``BASE_URL + path`` and return a structured result (never raises).

    Client-facing ``error`` is a short status summary; full backend bodies go to stderr only.
    """
    url = f"{get_base_url()}{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if AUTH_TOKEN:
        headers["Authorization"] = f"Bearer {AUTH_TOKEN}"
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=_HTTP_TIMEOUT_S) as resp:
            raw = resp.read().decode()
            payload: Any = json.loads(raw) if raw.strip() else {}
            return HttpResult(ok=True, status=getattr(resp, "status", 200), data=payload)
    except HTTPError as e:
        detail = e.read().decode(errors="replace")[:300] if e.fp else ""
        logger.warning(
            "backend %s %s failed: HTTP %s %s",
            method,
            path,
            e.code,
            detail or e.reason,
        )
        return HttpResult(ok=False, status=e.code, error=f"HTTP {e.code}")
    except URLError as e:
        logger.warning("backend %s %s failed: connection error: %s", method, path, e.reason)
        return HttpResult(ok=False, error="connection error")
    except TimeoutError:
        logger.warning("backend %s %s failed: timeout after %.0fs", method, path, _HTTP_TIMEOUT_S)
        return HttpResult(ok=False, error=f"timeout after {_HTTP_TIMEOUT_S:.0f}s")
    except json.JSONDecodeError as e:
        logger.warning("backend %s %s failed: invalid JSON: %s", method, path, e)
        return HttpResult(ok=False, error="invalid JSON response")


# Back-compat aliases.
_http = request
_validate_base_url = validate_base_url
