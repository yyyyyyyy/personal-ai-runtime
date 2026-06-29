"""Shadow compare — persist_work_item (Truth A) vs Execution projection (Truth B).

ADR-0007 Step 2: after each dual-write, verify that the row implied by
WorkItem.to_row() matches handler_executions as updated by Execution projectors.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from app.core.runtime.kernel.constants import AGGREGATE_EXECUTION

logger = logging.getLogger(__name__)

# Fields compared between persist intent and projection materialisation.
COMPARE_FIELDS: tuple[str, ...] = (
    "id",
    "status",
    "retry_count",
    "created_at",
    "started_at",
    "completed_at",
    "error",
    "policy_json",
    "event_seq",
    "event_id",
    "event_type",
    "handler_name",
    "instance_id",
    "correlation_id",
)


@dataclass
class ShadowCompareStats:
    """Cumulative shadow-compare results (tests and optional runtime telemetry)."""

    checkpoints_checked: int = 0
    executions_checked: int = 0
    mismatches: int = 0
    details: list[str] = field(default_factory=list)

    def record(self, execution_id: str, diffs: list[str]) -> None:
        self.checkpoints_checked += 1
        if diffs:
            self.mismatches += len(diffs)
            for diff in diffs:
                self.details.append(f"{execution_id}: {diff}")


_stats = ShadowCompareStats()


def get_shadow_compare_stats() -> ShadowCompareStats:
    return _stats


def reset_shadow_compare_stats() -> None:
    global _stats
    _stats = ShadowCompareStats()


def normalize_row(row: dict) -> dict:
    """Normalize a handler_executions row for stable comparison."""
    out = {k: row.get(k) for k in COMPARE_FIELDS if k in row}
    pj = out.get("policy_json")
    if isinstance(pj, str) and pj:
        out["policy_json"] = json.dumps(
            json.loads(pj), sort_keys=True,
        )
    for key in ("started_at", "completed_at", "error"):
        if out.get(key) is None:
            out[key] = ""
    return out


def _read_row(kernel, execution_id: str) -> dict | None:
    with kernel._db.get_db() as conn:
        row = conn.execute(
            "SELECT * FROM handler_executions WHERE id = ?",
            (execution_id,),
        ).fetchone()
    return dict(row) if row else None


def diff_rows(expected: dict, actual: dict) -> list[str]:
    """Return human-readable diffs for COMPARE_FIELDS."""
    exp = normalize_row(expected)
    act = normalize_row(actual)
    diffs: list[str] = []
    for key in COMPARE_FIELDS:
        if exp.get(key) != act.get(key):
            diffs.append(f"{key}: persist={exp.get(key)!r} projection={act.get(key)!r}")
    return diffs


def verify_persist_matches_projection(kernel, item) -> list[str]:
    """Compare WorkItem.to_row() (persist) to current handler_executions row."""
    persist_row = item.to_row()
    stored = _read_row(kernel, item.id)
    if stored is None:
        diffs = ["handler_executions row missing after dual-write"]
    else:
        diffs = diff_rows(persist_row, stored)

    _stats.record(item.id, diffs)
    if diffs:
        logger.warning(
            "Execution shadow compare mismatch for %s: %s",
            item.id,
            "; ".join(diffs),
        )
    return diffs


def replay_execution_row(kernel, execution_id: str) -> dict | None:
    """Rebuild one execution row by replaying its events (projection-only)."""
    from app.core.runtime.kernel import projectors

    events = kernel.read_events(
        aggregate_type=AGGREGATE_EXECUTION,
        aggregate_id=execution_id,
    )
    if not events:
        return None

    with kernel._db.get_db() as conn:
        conn.execute(
            "DELETE FROM handler_executions WHERE id = ?",
            (execution_id,),
        )
        for event in events:
            projectors.apply(event, conn)
        row = conn.execute(
            "SELECT * FROM handler_executions WHERE id = ?",
            (execution_id,),
        ).fetchone()
    return dict(row) if row else None


def verify_stored_matches_event_replay(kernel, execution_id: str) -> list[str]:
    """Compare live row to row produced by replaying execution events only."""
    stored = _read_row(kernel, execution_id)
    if stored is None:
        diffs = ["handler_executions row missing"]
        _stats.record(execution_id, diffs)
        return diffs

    snapshot = normalize_row(stored)
    replayed = replay_execution_row(kernel, execution_id)
    if replayed is None:
        diffs = ["no execution events to replay"]
    else:
        diffs = diff_rows(snapshot, replayed)

    _stats.executions_checked += 1
    _stats.record(execution_id, diffs)
    return diffs


def assert_zero_mismatches(stats: ShadowCompareStats | None = None) -> None:
    """Raise AssertionError if any shadow compare mismatches were recorded."""
    stats = stats or _stats
    if stats.mismatches:
        raise AssertionError(
            f"shadow compare: {stats.mismatches} mismatch(es) in "
            f"{stats.checkpoints_checked} checkpoint(s): {stats.details}"
        )
