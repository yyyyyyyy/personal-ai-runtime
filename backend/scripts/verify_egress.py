#!/usr/bin/env python
"""LLM Egress verification — EGRESS_RFC v0.1."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

os.environ.setdefault("LLM_API_KEY", "test-key")

from app.core.runtime.egress.egress_gate import prepare_llm_egress
from app.core.runtime.kernel import Kernel
from app.store.database import Database


def main() -> int:
    violations: list[str] = []
    db_path = _BACKEND_ROOT / "data" / "verify_egress.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = Database(db_path=str(db_path))
    k = Kernel(db=db)

    import app.core.runtime.kernel_instance as ki

    ki.kernel = k

    messages = [
        {
            "role": "user",
            "content": "identity_narrative_opt_in claim_status proposed",
        }
    ]
    outbound, audit = prepare_llm_egress(messages, purpose="verify")
    if not audit.get("classification"):
        violations.append("egress: missing classification")
    if "identity_surface" not in audit["classification"]["categories"]:
        violations.append("egress: expected identity_surface classification")
    if not audit.get("identity_surface_detected"):
        violations.append("egress: expected identity_surface_detected flag")
    if outbound != messages:
        violations.append("egress: audit-only path must not mutate outbound messages")

    events = k.read_events(type="EgressApproved", order="desc", limit=1)
    if not events:
        violations.append("egress: EgressApproved event not emitted")

    general, audit2 = prepare_llm_egress(
        [{"role": "user", "content": "hello world"}], purpose="verify_general"
    )
    if audit2["classification"]["categories"] != ["general"]:
        violations.append(
            f"egress: general misclassified {audit2['classification']['categories']}"
        )
    if general[0]["content"] != "hello world":
        violations.append("egress: general content must pass through unchanged")

    if violations:
        print("EGRESS VERIFICATION FAILED", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        return 1

    print("EGRESS VERIFICATION PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
