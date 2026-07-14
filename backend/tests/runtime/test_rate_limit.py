"""Tests for in-memory rate limiting (always active regardless of auth)."""

import pytest

from app.core.rate_limit import (
    _BUCKETS,
    _MAX_BUCKETS,
    _evict_stale_buckets,
    _matches,
    check_rate_limit,
    reset_rate_limits,
)


@pytest.fixture(autouse=True)
def _clear_rate_limits():
    reset_rate_limits()
    yield
    reset_rate_limits()


class TestRateLimit:
    def test_allow_first_request(self):
        assert check_rate_limit("/api/chat/conversations") is True

    def test_allow_non_limited_path(self):
        # Unlisted paths always pass.
        for _ in range(100):
            assert check_rate_limit("/api/system/health") is True

    def test_rate_limit_chat_endpoint(self):
        # /api/chat is limited to 30 req/60s.
        # Send 30 requests — all should pass.
        for _ in range(30):
            assert check_rate_limit("/api/chat/conversations") is True
        # The 31st is denied within the 60s window.
        assert check_rate_limit("/api/chat/conversations") is False

    def test_sensitive_ops_local_item(self):
        # rate limit is per-path-pattern; /api/settings/llm/test allows 5/min.
        for _ in range(5):
            assert check_rate_limit("/api/settings/llm/test") is True
        assert check_rate_limit("/api/settings/llm/test") is False

    def test_different_paths_independent_buckets(self):
        # Max out chat …
        for _ in range(30):
            check_rate_limit("/api/chat/x")
        assert check_rate_limit("/api/chat/x") is False
        # … but export still works (separate bucket).
        assert check_rate_limit("/api/system/export") is True

    def test_anonymous_and_token_buckets_separate(self):
        # Two callers with different keys get independent rate-limit buckets.
        for _ in range(30):
            check_rate_limit("/api/chat", key="caller-a")
        assert check_rate_limit("/api/chat", key="caller-a") is False
        # Caller-b is unaffected.
        assert check_rate_limit("/api/chat", key="caller-b") is True

    def test_invalid_auth_bucket_separate(self):
        """bad-auth key is independent of anonymous key."""
        for _ in range(30):
            check_rate_limit("/api/chat", key="anonymous")
        assert check_rate_limit("/api/chat", key="anonymous") is False
        # bad-auth bucket is still fresh.
        assert check_rate_limit("/api/chat", key="bad-auth") is True

    def test_plaintext_and_encrypted_import_share_strict_bucket(self):
        # Both /import and /import/encrypted share the "system-restore" bucket
        # (1 per 5 min) so callers cannot double-dip destructive restores.
        assert check_rate_limit("/api/system/import", key="caller") is True
        assert (
            check_rate_limit("/api/system/import/encrypted", key="caller")
            is False
        )


class TestPathMatching:
    """Verify that path-prefix matching cannot be bypassed."""

    def test_exact_match_system_data(self):
        # /api/system/data is exact-match: sibling paths must NOT be limited.
        assert _matches("/api/system/data", "/api/system/data", exact=True)
        assert not _matches("/api/system/dataXXX", "/api/system/data", exact=True)
        assert not _matches("/api/system/data/extra", "/api/system/data", exact=True)

    def test_prefix_match_chat_with_boundary(self):
        # /api/chat uses prefix matching: subpaths match, siblings do not.
        assert _matches("/api/chat", "/api/chat", exact=False)
        assert _matches("/api/chat/123", "/api/chat", exact=False)
        # Critical: /api/chatXXX must not hit the /api/chat bucket.
        assert not _matches("/api/chatXXX", "/api/chat", exact=False)
        assert not _matches("/api/chatsidebar", "/api/chat", exact=False)

    def test_export_is_exact(self):
        # Export is exact to avoid /api/system/export-mirror sharing the bucket.
        assert _matches("/api/system/export", "/api/system/export", exact=True)
        assert not _matches("/api/system/export/encrypted", "/api/system/export", exact=True)


class TestBucketEviction:
    """Verify that _evict_stale_buckets bounds memory without nuking active buckets."""

    def test_eviction_triggers_when_over_cap(self):
        reset_rate_limits()
        # Populate well beyond the cap with distinct keys.
        for i in range(_MAX_BUCKETS + 500):
            check_rate_limit("/api/chat", key=f"ip{i}")
        assert len(_BUCKETS) <= _MAX_BUCKETS

    def test_eviction_preserves_recent_bucket(self):
        reset_rate_limits()
        # Fill with many IPs, then verify a freshly-used bucket survives.
        for i in range(_MAX_BUCKETS + 200):
            check_rate_limit("/api/chat", key=f"ip{i}")
        # The most recently inserted key should still be present.
        assert ("/api/chat", f"ip{_MAX_BUCKETS + 199}") in _BUCKETS

    def test_eviction_does_not_reset_active_user_window(self):
        """Regression: the old _BUCKETS.clear() reset every user's window.

        Note: under extreme IP flooding (>10k distinct IPs), LRU eviction may
        still drop an idle user's bucket. This test verifies the common case:
        a user who keeps interacting during the attack keeps their window.
        """
        reset_rate_limits()
        # Legitimate user keeps chatting throughout the attack.
        for _ in range(29):
            check_rate_limit("/api/chat", key="legit_user")
        # Attacker spins up many IPs. Interleave legit traffic so the bucket
        # stays fresh and is not evicted as stale.
        for i in range(_MAX_BUCKETS + 500):
            check_rate_limit("/api/chat", key=f"attacker_ip_{i}")
            if i % 1000 == 0:
                # legit_user pings periodically to keep the bucket recent.
                check_rate_limit("/api/chat", key="legit_user")
        # legit_user has used 29 + N periodic pings; should be at or near cap.
        # The key assertion: the bucket still exists (was not globally cleared).
        assert ("/api/chat", "legit_user") in _BUCKETS
