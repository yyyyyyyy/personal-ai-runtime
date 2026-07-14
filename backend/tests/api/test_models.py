"""Unit tests for API request model validation."""

import pytest
from pydantic import ValidationError

from app.api.models import ImportRequest, _approx_payload_bytes


class TestImportRequestSizeValidation:
    """ImportRequest.data must reject payloads over 100MB to prevent OOM."""

    def test_small_payload_accepted(self):
        req = ImportRequest(data={"key": "value"}, read_only=True)
        assert req.data == {"key": "value"}

    def test_empty_dict_accepted(self):
        req = ImportRequest(data={}, read_only=True)
        assert req.data == {}

    def test_oversized_payload_rejected(self, monkeypatch):
        # Avoid allocating a real 100MB string — stub the size estimator.
        monkeypatch.setattr(
            "app.api.models._approx_payload_bytes",
            lambda obj, **kwargs: 100 * 1024 * 1024 + 1,
        )
        with pytest.raises(ValidationError) as exc_info:
            ImportRequest(data={"blob": "x"}, read_only=False)
        errors = exc_info.value.errors()
        assert any("too large" in str(e.get("msg", "")).lower() for e in errors)

    def test_approx_size_counts_nested_strings(self):
        size = _approx_payload_bytes({"a": "hello", "b": ["world", "x" * 100]})
        assert size > 100
        assert size < 10_000
