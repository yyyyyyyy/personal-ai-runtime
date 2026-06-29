"""A2 · Cognitive layer CI tests — Pattern/Belief/Vector verification.

Complements CI scripts:
  - scripts/verify_pattern_rebuild.py
  - scripts/verify_belief_pipeline.py
  - scripts/verify_vector_consistency.py

AC4: deliberately制造 memory/Chroma 不一致时 reconcile 必须失败。
"""

import importlib.util
import os
import sqlite3
import sys
from pathlib import Path

import pytest

os.environ.setdefault("LLM_API_KEY", "test-key")

_BACKEND = Path(__file__).resolve().parents[2]


def _load_verify_vector_module():
    path = _BACKEND / "scripts" / "verify_vector_consistency.py"
    spec = importlib.util.spec_from_file_location("verify_vector_consistency", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["verify_vector_consistency"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def verify_vector():
    return _load_verify_vector_module()


def test_vector_reconcile_passes_when_consistent(tmp_path, verify_vector):
    """Self-test path: emit memories → SQLite and Chroma IDs match."""
    violations = verify_vector.run_self_test()
    assert violations == [], f"Expected no violations, got: {violations}"


def test_vector_reconcile_fails_on_sqlite_chroma_mismatch(tmp_path, verify_vector):
    """AC4: orphan Chroma ID without SQLite row must be detected."""
    db_path = tmp_path / "mismatch.db"
    vector_dir = tmp_path / "vectors"
    vector_dir.mkdir()

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """CREATE TABLE memories (
            id TEXT PRIMARY KEY,
            category TEXT,
            content TEXT,
            source TEXT,
            embedding_id TEXT,
            confidence REAL,
            derived_from_event TEXT,
            created_at TEXT,
            origin TEXT,
            claim_status TEXT
        )"""
    )
    conn.execute(
        "INSERT INTO memories (id, category, content, source, embedding_id, confidence, "
        "derived_from_event, created_at, origin, claim_status) "
        "VALUES ('m-sqlite-only', 'general', 'x', 'test', 'm-sqlite-only', 0.5, '', '', '', '')"
    )
    conn.commit()
    conn.close()

    os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
    os.environ.setdefault("CHROMA_TELEMETRY_IMPL", "none")
    os.environ.setdefault("CHROMA_TELEMETRY_ENABLED", "false")

    import chromadb
    from chromadb.config import Settings as ChromaSettings

    client = chromadb.PersistentClient(
        path=str(vector_dir),
        settings=ChromaSettings(anonymized_telemetry=False),
    )
    collection = client.get_or_create_collection(name="memories")
    collection.add(ids=["m-chroma-only"], documents=["orphan vector"])

    violations = verify_vector.reconcile(str(db_path), str(vector_dir))
    assert len(violations) > 0, "reconcile must fail when SQLite and Chroma IDs diverge"
    assert any("mismatch" in v or "Chroma" in v or "SQLite" in v for v in violations)


def test_pattern_rebuild_script_exits_zero():
    """verify_pattern_rebuild.py must pass on isolated seed data."""
    import subprocess

    result = subprocess.run(
        [sys.executable, str(_BACKEND / "scripts" / "verify_pattern_rebuild.py")],
        cwd=str(_BACKEND),
        capture_output=True,
        text=True,
        env={**os.environ, "LLM_API_KEY": "test-key"},
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"


def test_belief_pipeline_script_exits_zero():
    """verify_belief_pipeline.py must pass on isolated seed data."""
    import subprocess

    result = subprocess.run(
        [sys.executable, str(_BACKEND / "scripts" / "verify_belief_pipeline.py")],
        cwd=str(_BACKEND),
        capture_output=True,
        text=True,
        env={**os.environ, "LLM_API_KEY": "test-key"},
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
