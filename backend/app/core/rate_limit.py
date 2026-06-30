"""Simple in-memory rate limiter for API protection.

Uses a token-bucket algorithm per endpoint pattern. Designed for
single-process local-first deployment; for distributed setups,
replace with Redis-backed limiter.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict

# ── Rate limit config ─────────────────────────────────────────────────────

# (pattern, max_requests, window_seconds)
_RATE_LIMITS: list[tuple[str, int, float]] = [
    ("/api/chat", 30, 60),
    ("/api/settings/llm/test", 5, 60),
    ("/api/settings/email/test", 5, 60),
    ("/api/inbox/poll", 10, 60),
    ("/api/system/export", 3, 60),
]

_BUCKETS: dict[tuple[str, str], list[float]] = defaultdict(list)
_BUCKETS_LOCK = threading.Lock()


def _clean_expired(bucket: list[float], window: float) -> None:
    cutoff = time.monotonic() - window
    while bucket and bucket[0] < cutoff:
        bucket.pop(0)


def check_rate_limit(path: str, token: str = "") -> bool:
    """Return True if the request is allowed, False if rate-limited."""
    for pattern, max_req, window in _RATE_LIMITS:
        if path.startswith(pattern):
            key = (pattern, token or "anonymous")
            with _BUCKETS_LOCK:
                bucket = _BUCKETS[key]
                _clean_expired(bucket, window)
                if len(bucket) >= max_req:
                    return False
                bucket.append(time.monotonic())
            return True
    return True
