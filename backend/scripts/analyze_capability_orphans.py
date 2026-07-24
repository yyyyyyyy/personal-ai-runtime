"""Analyze capability policy orphans (T2).

Reports:
  - active policy_events with zero CapabilityInvoked in event_log
  - CapabilityInvoked names missing from policy_events
  - seed JSON vs projection drift

Usage:
    python -m scripts.analyze_capability_orphans
    python -m scripts.analyze_capability_orphans --db path/to.db
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from scripts._bootstrap import prepare_script_env

prepare_script_env()


def analyze(db_path: Path) -> int:
    import sqlite3

    from app.config import settings

    if not db_path.is_file():
        print(f"ERROR: database not found: {db_path}", file=sys.stderr)
        return 2

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    policies = {
        r["capability"]: dict(r)
        for r in conn.execute(
            "SELECT capability, risk_level, status FROM policy_events"
        )
    }
    active = {k for k, v in policies.items() if v["status"] == "active"}

    invoked = Counter(
        r[0]
        for r in conn.execute(
            "SELECT json_extract(payload, '$.name') FROM event_log "
            "WHERE type = 'CapabilityInvoked'"
        )
        if r[0]
    )

    seed_path = Path(settings.capability_policy_path)
    seed_names: set[str] = set()
    if seed_path.is_file():
        data = json.loads(seed_path.read_text(encoding="utf-8"))
        for key in ("forbidden", "needs_user", "auto_allow"):
            seed_names.update(data.get(key, []))

    never_invoked = sorted(active - set(invoked))
    invoked_unpolicied = sorted(set(invoked) - set(policies))
    active_not_in_seed = sorted(active - seed_names)
    seed_missing_active = sorted(seed_names - active)

    print(f"database:                {db_path}")
    print(f"active policies:         {len(active)}")
    print(f"CapabilityInvoked total: {sum(invoked.values())} "
          f"across {len(invoked)} names")
    print(f"seed JSON capabilities:  {len(seed_names)}")
    print()
    print(f"=== orphans: active policy, never invoked ({len(never_invoked)}) ===")
    for name in never_invoked:
        src = "seed" if name in seed_names else "mcp/external"
        print(f"  [{policies[name]['risk_level']:9}] {name}  ({src})")
    print()
    print(f"=== invoked but no policy row ({len(invoked_unpolicied)}) ===")
    for name in invoked_unpolicied:
        print(f"  {name}  (invocations={invoked[name]})")
    print()
    print(f"=== active but not in seed JSON ({len(active_not_in_seed)}) ===")
    print("  (expected for MCP external tools)")
    for name in active_not_in_seed[:30]:
        print(f"  [{policies[name]['risk_level']:9}] {name}")
    if len(active_not_in_seed) > 30:
        print(f"  ... +{len(active_not_in_seed) - 30} more")
    print()
    print(f"=== in seed JSON but not active ({len(seed_missing_active)}) ===")
    for name in seed_missing_active:
        print(f"  {name}")
    print()
    print("=== top invoked ===")
    for name, n in invoked.most_common(15):
        print(f"  {n:4d}  {name}")

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=None)
    args = parser.parse_args(argv)
    if args.db is None:
        from app.config import settings
        db_path = Path(settings.sqlite_path)
    else:
        db_path = args.db
    return analyze(db_path)


if __name__ == "__main__":
    raise SystemExit(main())
