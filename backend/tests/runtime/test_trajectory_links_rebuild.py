"""Materialized trajectory_links projection."""

import os

import pytest

os.environ.setdefault("LLM_API_KEY", "test-key")

from app.core.runtime.kernel import Kernel
from app.experimental.trajectory.engine import (
    _collect_trajectory_links_materialized,
    _collect_trajectory_links_virtual,
    link_event,
    query_trajectory,
    rebuild_trajectory_links,
)
from app.store.database import Database


@pytest.fixture(autouse=True)
def _restore():
    import app.core.runtime.kernel_instance as ki
    import app.store.database as db_mod

    saved_k, saved_d = ki.kernel, db_mod.db
    yield
    ki.kernel, db_mod.db = saved_k, saved_d


def test_materialized_matches_virtual_after_rebuild(tmp_path):
    k = Kernel(db=Database(db_path=str(tmp_path / "tl.db")))
    import app.core.runtime.kernel_instance as ki
    import app.store.database as db_mod

    ki.kernel = k
    db_mod.db = k._db

    src = k.emit_event(
        "MemoryDerived", "memory", "m1",
        payload={"content": "创业"},
        actor="user",
    )
    link_event(k, "career-entrepreneurship-2026", src.seq)

    virtual = _collect_trajectory_links_virtual(k, "career-entrepreneurship-2026")
    rebuild_trajectory_links(k)
    materialized = _collect_trajectory_links_materialized(
        k, "career-entrepreneurship-2026"
    )
    assert len(materialized) == len(virtual)
    assert materialized[0]["link_id"] == virtual[0]["link_id"]

    data = query_trajectory(k, "career-entrepreneurship-2026")
    assert data and len(data["links"]) == 1
