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


@pytest.fixture
def isolated_kernel(tmp_path, monkeypatch):
    """Fresh Kernel + Database with monkeypatched singleton for integration tests.

    User-space code that imports ``kernel_instance.kernel`` or ``database.db``
    will resolve to this isolated instance, keeping tests independent.
    """
    from app.core.runtime.kernel import Kernel
    from app.store.database import Database

    db_path = str(tmp_path / "test.db")
    db = Database(db_path=db_path)
    k = Kernel(db=db)
    monkeypatch.setattr("app.core.runtime.kernel_instance.kernel", k)
    monkeypatch.setattr("app.store.database.db", db)
    return k, db
