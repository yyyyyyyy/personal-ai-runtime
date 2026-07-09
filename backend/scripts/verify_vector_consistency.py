#!/usr/bin/env python
"""Read-only reconciliation: SQLite memories projection vs Chroma index."""

from __future__ import annotations

import argparse
import importlib
import os
import shutil
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

os.environ.setdefault("LLM_API_KEY", "test-key")


def sqlite_memory_ids(db_path: str) -> set[str]:
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT id FROM memories").fetchall()
    except sqlite3.OperationalError:
        return set()
    finally:
        conn.close()
    return {str(r["id"]) for r in rows}


def chroma_memory_ids(vector_dir: str) -> set[str]:
    os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
    os.environ.setdefault("CHROMA_TELEMETRY_IMPL", "none")
    os.environ.setdefault("CHROMA_TELEMETRY_ENABLED", "false")

    import chromadb
    from chromadb.config import Settings as ChromaSettings

    client = chromadb.PersistentClient(
        path=vector_dir,
        settings=ChromaSettings(anonymized_telemetry=False),
    )
    collection = client.get_or_create_collection(name="memories")
    result = collection.get()
    return set(result.get("ids") or [])


def reconcile(db_path: str, vector_dir: str) -> list[str]:
    violations: list[str] = []
    sqlite_ids = sqlite_memory_ids(db_path)
    chroma_ids = chroma_memory_ids(vector_dir)

    if len(sqlite_ids) != len(chroma_ids):
        violations.append(
            f"count mismatch: sqlite={len(sqlite_ids)} chroma={len(chroma_ids)}"
        )

    only_sqlite = sorted(sqlite_ids - chroma_ids)
    only_chroma = sorted(chroma_ids - sqlite_ids)
    if only_sqlite:
        preview = ", ".join(only_sqlite[:5])
        suffix = "..." if len(only_sqlite) > 5 else ""
        violations.append(f"in SQLite not Chroma ({len(only_sqlite)}): {preview}{suffix}")
    if only_chroma:
        preview = ", ".join(only_chroma[:5])
        suffix = "..." if len(only_chroma) > 5 else ""
        violations.append(f"in Chroma not SQLite ({len(only_chroma)}): {preview}{suffix}")

    return violations


def _reload_app_paths() -> None:
    """Reload settings + vector singleton after VECTOR_DIR / DATA_DIR change."""
    import app.config

    importlib.reload(app.config)
    if "app.store.vector" in sys.modules:
        import app.store.vector as vector_module

        importlib.reload(vector_module)


def run_self_test() -> list[str]:
    """Create isolated DB + vector dir, emit memories, expect consistency."""
    base = _BACKEND_ROOT / "data" / "verify_vector_consistency"
    db_path = base / "test.db"
    vector_dir = base / "vectors"

    if base.exists():
        shutil.rmtree(base, ignore_errors=True)
    base.mkdir(parents=True, exist_ok=True)

    os.environ["DATA_DIR"] = str(base)
    os.environ["VECTOR_DIR"] = str(vector_dir)
    _reload_app_paths()

    from app.core.runtime.kernel import Kernel
    from app.store.database import Database
    from app.store.vector import vector_store

    db = Database(db_path=str(db_path))
    kernel = Kernel(db=db, memory_index=vector_store)

    for mid, content in (("m1", "alpha memory"), ("m2", "beta memory")):
        kernel.emit_event(
            "MemoryDerived",
            "memory",
            mid,
            payload={"content": content, "category": "general", "source": "verify"},
            actor="verify",
        )

    return reconcile(str(db_path), str(vector_dir))


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile SQLite memories vs Chroma index")
    parser.add_argument("--db", help="SQLite database path to check")
    parser.add_argument("--vector-dir", help="Chroma vector directory to check")
    parser.add_argument(
        "--check-default",
        action="store_true",
        help="Also check default settings.data_dir / vector_dir",
    )
    args = parser.parse_args()

    violations = run_self_test()
    if violations:
        print("VECTOR CONSISTENCY SELF-TEST FAILED", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        return 1

    targets: list[tuple[str, str, str]] = []
    if args.db and args.vector_dir:
        targets.append(("custom", args.db, args.vector_dir))
    if args.check_default:
        from app.config import settings

        default_db = Path(settings.data_dir) / "personal_ai.db"
        if default_db.exists():
            targets.append(("default", str(default_db), settings.vector_dir))

    for label, db_path, vector_dir in targets:
        check_violations = reconcile(db_path, vector_dir)
        if check_violations:
            print(f"VECTOR CONSISTENCY FAILED ({label})", file=sys.stderr)
            for v in check_violations:
                print(f"  {v}", file=sys.stderr)
            return 1
        print(f"VECTOR CONSISTENCY OK ({label}) — {len(sqlite_memory_ids(db_path))} memories")

    print("VECTOR CONSISTENCY PASSED — self-test ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
