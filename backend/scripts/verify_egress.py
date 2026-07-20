#!/usr/bin/env python
"""LLM Egress verification."""

from __future__ import annotations

from pathlib import Path

import sys

_BACKEND = str(Path(__file__).resolve().parents[1])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from scripts._bootstrap import ephemeral_kernel


def main() -> int:
    violations: list[str] = []
    with ephemeral_kernel("verify_egress.db", install_singleton=True) as (_db, k):
        from app.core.runtime.egress.egress_gate import audit_llm_egress

        messages = [
            {
                "role": "user",
                "content": "identity_narrative_opt_in claim_status proposed",
            }
        ]
        outbound, audit = audit_llm_egress(messages, purpose="verify")
        if not audit.get("classification"):
            violations.append("egress: missing classification")
        if "identity_surface" not in audit["classification"]["categories"]:
            violations.append("egress: expected identity_surface classification")
        if not audit.get("identity_surface_detected"):
            violations.append("egress: expected identity_surface_detected flag")
        if outbound != messages:
            violations.append("egress: audit-only path must not mutate outbound messages")

        events = k.read_events(type="EgressAudited", order="desc", limit=1)
        if not events:
            violations.append("egress: EgressAudited event not emitted")

        general, audit2 = audit_llm_egress(
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
