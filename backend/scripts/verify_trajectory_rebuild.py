#!/usr/bin/env python
"""Trajectory links rebuild verification — materialized vs virtual parity.

See docs/rfc/TRAJECTORY_RFC.md §1.3.2.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

os.environ.setdefault("LLM_API_KEY", "test-key")

from app.core.runtime.kernel import Kernel
from app.experimental.trajectory.engine import (
    _collect_trajectory_links_materialized,
    _collect_trajectory_links_virtual,
    link_event,
    rebuild_trajectory_links,
)
from app.store.database import Database


def main() -> int:
    violations: list[str] = []

    db_path = _BACKEND_ROOT / "data" / "verify_trajectory_rebuild.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = Database(db_path=str(db_path))
    k = Kernel(db=db)

    import app.core.runtime.kernel_instance as ki
    import app.store.database as db_mod

    ki.kernel = k
    db_mod.db = db

    src = k.emit_event(
        "MemoryDerived", "memory", "rebuild-mem",
        payload={"content": "创业冲动"},
        actor="user",
    )
    assert src.seq is not None
    ev = link_event(k, "career-entrepreneurship-2026", src.seq, actor="system")
    link_id = (ev.payload or {}).get("link_id")

    virtual = _collect_trajectory_links_virtual(k, "career-entrepreneurship-2026")
    materialized_live = _collect_trajectory_links_materialized(
        k, "career-entrepreneurship-2026"
    )
    if len(materialized_live) != len(virtual):
        violations.append("live materialized row count != virtual replay")

    count = rebuild_trajectory_links(k)
    if count < 1:
        violations.append(f"rebuild replayed too few events: {count}")

    after = _collect_trajectory_links_materialized(k, "career-entrepreneurship-2026")
    if len(after) != len(virtual):
        violations.append("post-rebuild materialized count != virtual")

    if virtual and after:
        v0, m0 = virtual[0], after[0]
        for key in ("link_id", "trajectory_id", "event_seq", "claim_status"):
            if v0.get(key) != m0.get(key):
                violations.append(f"parity mismatch on {key}: {v0.get(key)!r} vs {m0.get(key)!r}")

    if link_id:
        from app.core.runtime.trajectory import link_authority

        link_authority.ratify(link_id)
        rebuild_trajectory_links(k)
        post = _collect_trajectory_links_materialized(k, "career-entrepreneurship-2026")
        if not post or post[0].get("claim_status") != "ratified":
            violations.append("ratified link status not projected after rebuild")

    if violations:
        print("TRAJECTORY REBUILD VERIFICATION FAILED", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        return 1

    print("TRAJECTORY REBUILD VERIFICATION PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
