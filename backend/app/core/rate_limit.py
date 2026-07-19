"""Simple in-memory rate limiter for API protection.

Uses a sliding-window counter per endpoint pattern. Designed for
single-process local-first deployment; for distributed setups,
replace with Redis-backed limiter.
"""

from __future__ import annotations

import hashlib
import math
import threading
import time
from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RateLimitRule:
    """One path pattern and its quota."""

    pattern: str
    max_requests: int
    window_seconds: float
    exact: bool = False
    bucket_id: str | None = None


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    """Outcome of a rate-limit check.

    Truthy when the request is allowed so existing ``if not check_rate_limit``
    call sites keep working.
    """

    allowed: bool
    retry_after: int | None = None

    def __bool__(self) -> bool:
        return self.allowed


# exact=True: only path == pattern.
# exact=False: path == pattern OR path.startswith(pattern + "/").
# bucket_id: optional shared bucket so related paths share one quota.
_RATE_LIMITS: tuple[RateLimitRule, ...] = (
    RateLimitRule("/api/chat", 30, 60),
    RateLimitRule("/api/settings/llm/test", 5, 60, exact=True),
    RateLimitRule("/api/settings/email/test", 5, 60, exact=True),
    RateLimitRule("/api/inbox/poll", 10, 60, exact=True),
    RateLimitRule("/api/system/export", 3, 60, exact=True, bucket_id="system-export"),
    RateLimitRule(
        "/api/system/export/encrypted", 3, 60, exact=True, bucket_id="system-export"
    ),
    # Destructive restores share one quota so callers cannot double-dip via
    # plaintext then encrypted (or vice versa) within the same window.
    RateLimitRule("/api/system/import", 1, 300, exact=True, bucket_id="system-restore"),
    RateLimitRule(
        "/api/system/import/encrypted", 1, 300, exact=True, bucket_id="system-restore"
    ),
    RateLimitRule("/api/system/data", 1, 300, exact=True),
    # High-cost write paths: approvals + connector mutations.
    RateLimitRule("/api/approvals", 20, 60),
    RateLimitRule(
        "/api/connectors/install", 5, 60, exact=True, bucket_id="connector-mutate"
    ),
    RateLimitRule(
        "/api/connectors/uninstall", 5, 60, exact=True, bucket_id="connector-mutate"
    ),
    RateLimitRule("/api/connectors", 15, 60),
)

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


def _retry_after_seconds(bucket: list[float], window: float, now: float) -> int:
    """Seconds until the oldest request in the window falls out."""
    if not bucket:
        return 1
    remaining = window - (now - bucket[0])
    return max(1, int(math.ceil(remaining)))


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
        k for k, bucket in _BUCKETS.items() if not bucket or bucket[-1] < stale_cutoff
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


def check_rate_limit(path: str, key: str = "anonymous") -> RateLimitDecision:
    """Return whether the request is allowed, plus Retry-After when denied."""
    for rule in _RATE_LIMITS:
        if not _matches(path, rule.pattern, rule.exact):
            continue
        bucket_key = (rule.bucket_id or rule.pattern, key)
        with _BUCKETS_LOCK:
            _evict_stale_buckets()
            bucket = _BUCKETS[bucket_key]
            _clean_expired(bucket, rule.window_seconds)
            now = time.monotonic()
            if len(bucket) >= rule.max_requests:
                return RateLimitDecision(
                    allowed=False,
                    retry_after=_retry_after_seconds(
                        bucket, rule.window_seconds, now
                    ),
                )
            bucket.append(now)
        return RateLimitDecision(allowed=True)
    return RateLimitDecision(allowed=True)


def hash_caller_key(raw: str) -> str:
    """Stable short hash for secret-like rate-limit keys (e.g. bearer tokens).

    Keeps full tokens out of the in-memory bucket map.
    """
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def reset_rate_limits() -> None:
    """Clear all in-memory rate-limit state. For test use only."""
    with _BUCKETS_LOCK:
        _BUCKETS.clear()
