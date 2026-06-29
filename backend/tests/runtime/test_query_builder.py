"""Unit tests for the kernel query-builder helpers.

These are pure functions; no DB or Kernel fixture needed. They guard the
contracts documented in query_builder.py:
- ``safe_limit`` clamps and coerces
- ``safe_order`` rejects unknown keys (no SQL injection via order param)
- ``in_clause`` handles empty input without producing invalid SQL
- ``build_where`` returns "" for empty clause lists
"""
from __future__ import annotations

import pytest

from app.core.runtime.kernel.query_builder import (
    MAX_LIMIT,
    build_where,
    in_clause,
    safe_limit,
    safe_order,
)


class TestSafeLimit:
    def test_none_returns_empty(self):
        assert safe_limit(None) == ""

    def test_none_with_default_uses_default(self):
        assert safe_limit(None, default=50) == " LIMIT 50"

    def test_explicit_value_overrides_default(self):
        assert safe_limit(10, default=50) == " LIMIT 10"

    @pytest.mark.parametrize("bad", ["0", 0, 0.0])
    def test_zero_allowed(self, bad):
        assert safe_limit(bad) == " LIMIT 0"  # type: ignore[arg-type]

    def test_negative_clamped_to_zero(self):
        assert safe_limit(-5) == " LIMIT 0"

    def test_oversize_clamped_to_max(self):
        assert safe_limit(MAX_LIMIT + 1000) == f" LIMIT {MAX_LIMIT}"

    def test_string_coerced(self):
        assert safe_limit("42") == " LIMIT 42"  # type: ignore[arg-type]


class TestSafeOrder:
    def test_none_falls_back_to_default(self):
        allowed = {"asc": "x ASC", "desc": "x DESC"}
        assert safe_order(None, allowed, "asc") == " ORDER BY x ASC"

    def test_known_key_used(self):
        allowed = {"asc": "x ASC", "desc": "x DESC"}
        assert safe_order("desc", allowed, "asc") == " ORDER BY x DESC"

    def test_unknown_key_falls_back_to_default_not_interpolated(self):
        allowed = {"asc": "x ASC"}
        # The injection attempt must NOT appear in the output.
        out = safe_order("evil; DROP TABLE goals", allowed, "asc")
        assert out == " ORDER BY x ASC"
        assert "evil" not in out
        assert "DROP" not in out


class TestInClause:
    def test_empty_returns_empty_pair(self):
        sql, params = in_clause([])
        assert sql == ""
        assert params == []

    def test_single_value(self):
        sql, params = in_clause([1])
        assert sql == "IN (?)"
        assert params == [1]

    def test_many_values_get_one_placeholder_each(self):
        sql, params = in_clause(["a", "b", "c"])
        assert sql == "IN (?,?,?)"
        assert params == ["a", "b", "c"]


class TestBuildWhere:
    def test_empty_returns_empty_string(self):
        assert build_where([]) == ""

    def test_single_clause(self):
        assert build_where(["a = ?"]) == " WHERE a = ?"

    def test_many_clauses_joined_with_and(self):
        out = build_where(["a = ?", "b > ?", "c IS NOT NULL"])
        assert out == " WHERE a = ? AND b > ? AND c IS NOT NULL"
