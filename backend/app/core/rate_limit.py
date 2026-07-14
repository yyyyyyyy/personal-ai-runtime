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

# (pattern, max_requests, window_seconds, exact, bucket_id)
# exact=True means only match path == pattern (no prefix matching).
# exact=False means match path == pattern OR path.startswith(pattern + "/")
# bucket_id: optional shared bucket name so related paths share one quota
# (e.g. plaintext + encrypted import both use "system-restore").
_RATE_LIMITS: list[tuple[str, int, float, bool, str | None]] = [
    ("/api/chat", 30, 60, False, None),
    ("/api/settings/llm/test", 5, 60, True, None),
    ("/api/settings/email/test", 5, 60, True, None),
    ("/api/inbox/poll", 10, 60, True, None),
    ("/api/system/export", 3, 60, True, "system-export"),
    ("/api/system/export/encrypted", 3, 60, True, "system-export"),
    # Destructive restores share one quota so callers cannot double-dip via
    # plaintext then encrypted (or vice versa) within the same window.
    ("/api/system/import", 1, 300, True, "system-restore"),
    ("/api/system/import/encrypted", 1, 300, True, "system-restore"),
    ("/api/system/data", 1, 300, True, None),
]

_BUCKETS: dict[tuple[str, str], list[float]] = defaultdict(list)
_BUCKETS_LOCK = threading.Lock()
_MAX_BUCKETS = 10_000
# Default window for stale-bucket eviction (seconds). Buckets whose newest
# timestamp is older than this are eligible for eviction regardless of their
# pattern's own window.
_STALE_EVICT_SECONDS = 300


def _matches(path: str, pattern: str, exact: bool) -> bool:
    """Match a request path against a rate-limit pattern.

    exact=True: only path == pattern matches.
    exact=False: path == pattern OR path starts with pattern + "/" (boundary-safe).
    This prevents /api/chatXXX from bypassing /api/chat limits.

    Note: ASGI ``scope["path"]`` never includes the query string, so we only
    check the ``/`` boundary (not ``?``).
    """
    if path == pattern:
        return True
    if exact:
        return False
    return path.startswith(pattern + "/")


def _clean_expired(bucket: list[float], window: float) -> None:
    cutoff = time.monotonic() - window
    while bucket and bucket[0] < cutoff:
        bucket.pop(0)


def _evict_stale_buckets() -> None:
    """Drop empty or stale buckets to bound memory.

    Avoids the all-or-nothing ``_BUCKETS.clear()`` that would have reset every
    legitimate user's window whenever an attacker spun up many distinct IPs.
    Must be called under ``_BUCKETS_LOCK``.
    """
    if len(_BUCKETS) <= _MAX_BUCKETS:
        return
    now = time.monotonic()
    stale_cutoff = now - _STALE_EVICT_SECONDS
    # First pass: drop empty or stale buckets (no recent activity).
    stale_keys = [
        k for k, bucket in _BUCKETS.items()
        if not bucket or bucket[-1] < stale_cutoff
    ]
    for k in stale_keys:
        del _BUCKETS[k]
    # Second pass: if still over the cap, evict the oldest quarter by last-seen.
    if len(_BUCKETS) > _MAX_BUCKETS:
        sorted_keys = sorted(
            _BUCKETS.keys(),
            key=lambda k: _BUCKETS[k][-1] if _BUCKETS[k] else 0.0,
        )
        for k in sorted_keys[: max(1, len(_BUCKETS) // 4)]:
            del _BUCKETS[k]


def check_rate_limit(path: str, key: str = "anonymous") -> bool:
    """Return True if the request is allowed, False if rate-limited."""
    for pattern, max_req, window, exact, bucket_id in _RATE_LIMITS:
        if _matches(path, pattern, exact):
            bucket_key = (bucket_id or pattern, key)
            with _BUCKETS_LOCK:
                _evict_stale_buckets()
                bucket = _BUCKETS[bucket_key]
                _clean_expired(bucket, window)
                if len(bucket) >= max_req:
                    return False
                bucket.append(time.monotonic())
            return True
    return True


def reset_rate_limits() -> None:
    """Clear all in-memory rate-limit state. For test use only."""
    with _BUCKETS_LOCK:
        _BUCKETS.clear()
