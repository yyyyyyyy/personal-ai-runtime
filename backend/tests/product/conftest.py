"""Shared fixtures for product-layer tests.

Product modules bind ``kernel`` / ``default_kernel`` at import time, so
``isolated_kernel`` alone is not enough — this fixture also rebinds those names.

Tests that call APIs accepting ``kernel=`` should still pass it explicitly;
the module patches cover call sites that only use the import-time binding.
"""

import pytest


@pytest.fixture
def product_kernel(isolated_kernel, monkeypatch):
    """Isolated Kernel with product module bindings patched."""
    k, _db = isolated_kernel
    monkeypatch.setattr("app.product.personal_dashboard.kernel", k)
    monkeypatch.setattr("app.product.inbox.kernel", k)
    return k
