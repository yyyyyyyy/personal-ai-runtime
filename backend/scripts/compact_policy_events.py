"""Compact duplicate Policy* events in event_log (INV-C6 hygiene).

Root cause (pre-fix): MCP mesh stop called ``clear_external_tools()`` which
emitted ``PolicyUpdated(revoked)`` for every external tool; the next start
re-emitted ``PolicyCreated``. On a busy personal DB this accounted for ~74%
of event_log rows.

This script:
  1. Copies the DB to a timestamped backup
  2. Replays each ``policy_*`` aggregate to its final projection state
  3. Rewrites event_log, replacing each aggregate's event burst with one
     (or two) synthetic events placed at the aggregate's ORIGINAL first
     policy-event seq, preserving global ordering and ts
  4. Rebuilds projections

Data fidelity notes:
  - Synthetic events keep the original first event's ``ts`` so time-based
    audits and timelines remain correct.
  - ``caused_by`` is preserved from the original first event when present;
    the revoke synthetic links to the create synthetic to keep the chain.
  - ``correlation_id`` is preserved from the original first event.

Dry-run by default. Pass ``--apply`` to rewrite.

Usage:
    python -m scripts.compact_policy_events
    python -m scripts.compact_policy_events --apply
    python -m scripts.compact_policy_events --db path/to.db --apply
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

from scripts._bootstrap import prepare_script_env

prepare_script_env()

_POLICY_TYPES = frozenset({"PolicyCreated", "PolicyUpdated"})


def _payload(row: dict) -> dict:
    p = row.get("payload") or {}
    if isinstance(p, str):
        return json.loads(p)
    return p


def _replay_policy(events: list[dict]) -> dict | None:
    """Reduce an ordered policy event list to final {capability, risk, status}."""
    state: dict | None = None
    for ev in events:
        payload = _payload(ev)
        etype = ev["type"]
        if etype == "PolicyCreated":
            state = {
                "capability": payload.get("capability", ""),
                "risk_level": payload.get("risk_level", "low"),
                "status": "active",
            }
        elif etype == "PolicyUpdated" and state is not None:
            status = payload.get("status")
            if status == "revoked":
                state["status"] = "revoked"
            elif status == "active":
                state["status"] = "active"
                if "risk_level" in payload:
                    state["risk_level"] = payload["risk_level"]
            elif "risk_level" in payload:
                state["risk_level"] = payload["risk_level"]
        elif etype == "PolicyUpdated" and state is None:
            state = {
                "capability": payload.get("capability", ""),
                "risk_level": payload.get("risk_level", "low"),
                "status": payload.get("status") or "active",
            }
    return state


def _synthetic_rows(
    aggregate_id: str,
    state: dict,
    *,
    template: dict,
    start_seq: int,
) -> list[dict]:
    """Emit minimal event rows that rebuild to ``state``.

    ``template`` carries the original first event's ts / caused_by /
    correlation_id / actor so the synthetic rows preserve provenance.
    """
    rows: list[dict] = []
    seq = start_seq
    created_id = f"evt_compact_{aggregate_id}_created"
    rows.append({
        "seq": seq,
        "id": created_id,
        "type": "PolicyCreated",
        "aggregate_type": "policy",
        "aggregate_id": aggregate_id,
        "actor": template.get("actor") or "compact_policy_events",
        "payload": {
            "capability": state["capability"],
            "risk_level": state["risk_level"],
            "schema_version": 1,
        },
        "caused_by": template.get("caused_by"),
        "correlation_id": template.get("correlation_id"),
        "ts": template["ts"],
    })
    if state["status"] == "revoked":
        seq += 1
        rows.append({
            "seq": seq,
            "id": f"evt_compact_{aggregate_id}_revoked",
            "type": "PolicyUpdated",
            "aggregate_type": "policy",
            "aggregate_id": aggregate_id,
            "actor": template.get("actor") or "compact_policy_events",
            "payload": {
                "capability": state["capability"],
                "status": "revoked",
                "schema_version": 1,
            },
            "caused_by": created_id,
            "correlation_id": template.get("correlation_id"),
            "ts": template["ts"],
        })
    return rows


def plan_compaction(raw: list[dict]) -> tuple[list[dict], dict]:
    """Pure function: produce the compacted event list from raw rows.

    Returns (output_rows, stats). Does not touch any database — used by both
    ``compact`` (which then persists) and tests (which assert on structure).
    """
    policy_by_agg: dict[str, list[dict]] = {}
    other: list[dict] = []
    for row in raw:
        if row["type"] in _POLICY_TYPES:
            policy_by_agg.setdefault(row["aggregate_id"], []).append(row)
        else:
            other.append(row)

    before_policy = sum(len(v) for v in policy_by_agg.values())

    replacement_at: dict[int, list[dict]] = {}
    kept_policy = 0
    for agg_id, evts in policy_by_agg.items():
        evts_sorted = sorted(evts, key=lambda r: int(r["seq"]))
        state = _replay_policy(evts_sorted)
        if state is None or not state.get("capability"):
            continue
        first = evts_sorted[0]
        syn = _synthetic_rows(
            agg_id, state,
            template={
                "ts": first["ts"],
                "caused_by": first.get("caused_by"),
                "correlation_id": first.get("correlation_id"),
                "actor": first.get("actor"),
            },
            start_seq=0,
        )
        replacement_at[int(first["seq"])] = syn
        kept_policy += len(syn)

    skip_aggs: set[str] = set()
    output: list[dict] = []
    next_seq = 1
    for row in sorted(raw, key=lambda r: int(r["seq"])):
        seq = int(row["seq"])
        agg = row["aggregate_id"]
        if row["type"] in _POLICY_TYPES:
            if agg in skip_aggs:
                continue
            syn = replacement_at.get(seq)
            if syn is None:
                skip_aggs.add(agg)
                continue
            for s in syn:
                s = dict(s)
                s["seq"] = next_seq
                next_seq += 1
                output.append(s)
            skip_aggs.add(agg)
            continue
        r = dict(row)
        r["seq"] = next_seq
        next_seq += 1
        output.append(r)

    seqs = [int(r["seq"]) for r in output]
    assert seqs == list(range(1, len(output) + 1)), "seq renumber produced gaps"

    stats = {
        "total": len(raw),
        "policy_before": before_policy,
        "non_policy": len(other),
        "aggregates": len(policy_by_agg),
        "after": len(output),
        "policy_kept": kept_policy,
        "policy_removed": before_policy - kept_policy,
    }
    return output, stats


def compact(db_path: Path, *, apply: bool) -> int:
    from app.core.runtime.kernel.kernel import Kernel
    from app.core.runtime.kernel import sovereignty_ops
    from app.store.database import Database

    if not db_path.is_file():
        print(f"ERROR: database not found: {db_path}", file=sys.stderr)
        return 2

    db = Database(db_path=str(db_path))
    kernel = Kernel(db=db)

    raw = sovereignty_ops.export_event_log_rows(kernel)
    output, stats = plan_compaction(raw)

    print(f"database:           {db_path}")
    print(f"total events:       {stats['total']}")
    print(f"policy events:      {stats['policy_before']}")
    print(f"non-policy events:  {stats['non_policy']}")
    print(f"policy aggregates:  {stats['aggregates']}")
    print(f"after compact:      {stats['after']} "
          f"(policy kept={stats['policy_kept']}, "
          f"removed={stats['policy_removed']})")

    if not apply:
        print("dry-run only; pass --apply to rewrite (backup will be created).")
        return 0

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup = db_path.with_suffix(db_path.suffix + f".bak.{stamp}")
    shutil.copy2(db_path, backup)
    print(f"backup:             {backup}")

    imported = sovereignty_ops.import_event_log_rows(
        kernel, output, rebuild_projections=True,
    )
    print(f"imported:           {imported} events; projections rebuilt")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="SQLite path (default: settings.sqlite_path)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Rewrite event_log (default is dry-run)",
    )
    args = parser.parse_args(argv)

    if args.db is None:
        from app.config import settings
        db_path = Path(settings.sqlite_path)
    else:
        db_path = args.db

    return compact(db_path, apply=args.apply)


if __name__ == "__main__":
    raise SystemExit(main())
