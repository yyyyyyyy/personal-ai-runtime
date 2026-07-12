"""Tests for in-memory rate limiting (always active regardless of auth)."""

import pytest

from app.core.rate_limit import check_rate_limit, reset_rate_limits


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
        assert check_rate_limit("/api/system/import", key="caller") is True
        assert (
            check_rate_limit("/api/system/import/encrypted", key="caller")
            is False
        )
