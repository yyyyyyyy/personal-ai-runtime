"""Integration test: Trajectory API routes."""

import importlib
import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("LLM_API_KEY", "test-key")


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = str(tmp_path / "traj_api.db")
    monkeypatch.setenv("SQLITE_PATH", db_path)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("VECTOR_DIR", str(tmp_path / "vectors"))
    monkeypatch.setenv("EXPERIMENTAL_TRAJECTORY_ENABLED", "true")

    from app.store.database import Database

    Database._instance = None

    import app.config
    import app.main as main_module

    importlib.reload(app.config)
    importlib.reload(main_module)

    return TestClient(main_module.app)


def test_list_trajectories_and_pending_links(client):
    from app.core.runtime.kernel_instance import kernel
    from app.core.runtime.trajectory.engine import link_event

    src = kernel.emit_event(
        "MemoryDerived",
        "memory",
        "api-mem",
        payload={"content": "想辞职创业"},
        actor="user",
    )
    link_event(kernel, "career-entrepreneurship-2026", src.seq, actor="system")

    r = client.get("/api/trajectories")
    assert r.status_code == 200
    ids = {t["id"] for t in r.json()["trajectories"]}
    assert "career-entrepreneurship-2026" in ids

    r2 = client.get("/api/trajectories/pending-links")
    assert r2.status_code == 200
    pending = r2.json()["pending"]
    assert any(p["trajectory_id"] == "career-entrepreneurship-2026" for p in pending)


def test_ratify_trajectory_link_via_api(client):
    from app.core.runtime.kernel_instance import kernel
    from app.core.runtime.trajectory.engine import link_event

    src = kernel.emit_event(
        "MemoryDerived",
        "memory",
        "api-mem-2",
        payload={"content": "创业"},
        actor="user",
    )
    ev = link_event(kernel, "career-entrepreneurship-2026", src.seq, actor="system")
    link_id = (ev.payload or {})["link_id"]

    r = client.post(f"/api/trajectories/links/{link_id}/ratify")
    assert r.status_code == 200
    assert r.json()["claim_status"] == "ratified"

    r2 = client.get("/api/trajectories/pending-links")
    pending_ids = {p["link_id"] for p in r2.json()["pending"]}
    assert link_id not in pending_ids


def test_identity_opt_in_api(client):
    tid = "career-entrepreneurship-2026"
    r = client.post(f"/api/trajectories/{tid}/identity-opt-in")
    assert r.status_code == 200
    assert r.json()["identity_narrative_opt_in"] is True

    r2 = client.get("/api/trajectories")
    entry = next(t for t in r2.json()["trajectories"] if t["id"] == tid)
    assert entry["identity_narrative_opt_in"] is True

    r3 = client.post(f"/api/trajectories/{tid}/identity-opt-out")
    assert r3.status_code == 200
    assert r3.json()["identity_narrative_opt_in"] is False
