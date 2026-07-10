"""Global pytest configuration."""

import os

import pytest

os.environ.setdefault("LLM_API_KEY", "test-key")
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
os.environ.setdefault("CHROMA_TELEMETRY_IMPL", "none")
os.environ.setdefault("CHROMA_TELEMETRY_ENABLED", "false")
os.environ.setdefault("MCP_EXTERNAL_ENABLED", "false")

# Re-read settings after env defaults so tests see MCP_EXTERNAL_ENABLED=false.
from app.config import reset_settings

reset_settings()


@pytest.fixture(autouse=True)
def _reset_runtime():
    """Reset Runtime subsystems between tests for isolation.

    Without this, global singletons (capability_policy,
    taint_registry, source_registry) can leak state between tests.

    Fixtures that need a fresh start can rely on this
    baseline cleanup.
    """
    from app.core.runtime.runtime_container import runtime
    runtime.reset()
    yield

@pytest.fixture
def isolated_kernel(tmp_path, monkeypatch):
    """Fresh Kernel + Database fully isolated from the global runtime.

    Swaps the RuntimeContainer's cached ``db`` and ``kernel`` singletons for
    throwaway instances backed by a temp-path SQLite file. Because the
    ``kernel_instance.kernel`` lazy proxy forwards every access to
    ``runtime.kernel``, this isolates *every* caller — including modules that
    did ``from app.core.runtime.kernel_instance import kernel`` at import time
    (read_ports, agents, fragments) — without per-module monkeypatching.

    On teardown monkeypatch restores the originals so subsequent tests see a
    clean container that ``_reset_runtime`` will rebuild lazily.
    """
    from app.core.runtime.kernel.kernel import Kernel
    from app.core.runtime.runtime_container import runtime
    from app.store.database import Database

    db_path = str(tmp_path / "test.db")
    db = Database(db_path=db_path)
    k = Kernel(db=db)

    # Patch the container's cached singletons in place. monkeypatch records
    # the original values and restores them on teardown.
    monkeypatch.setattr(runtime, "_db", db)
    monkeypatch.setattr(runtime, "_kernel", k)
    # Legacy aliases kept for code that imports these names directly.
    monkeypatch.setattr("app.core.runtime.kernel_instance.kernel", k)
    monkeypatch.setattr("app.store.database.db", db)
    return k, db
