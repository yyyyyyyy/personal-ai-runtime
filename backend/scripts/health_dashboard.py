"""Runtime Health Dashboard — trend report for Architecture Contract metrics.

Reads the architecture history file (append-only JSONL) and generates a
markdown report showing current values, 7-day trends, and all-time deltas.

Usage:
    python scripts/health_dashboard.py              # print report to stdout
    python scripts/health_dashboard.py --write      # write to data/architecture_report.md
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

HISTORY_FILE = ROOT / "backend" / "data" / "architecture_history.jsonl"
REPORT_FILE = ROOT / "backend" / "data" / "architecture_report.md"

# Display names and order for metrics
METRICS = [
    ("runtime_files", "runtime/ files"),
    ("event_types", "event types"),
    ("query_state_selectors", "query_state selectors"),
    ("fragments", "fragments"),
    ("governed_tables", "governed tables"),
    ("projector_files", "projector files"),
    ("god_object_max_loc", "God Object LOC"),
    ("dead_code_files", "dead code files"),
]

ASPIRATIONAL_TARGETS = {
    "runtime_files": 45,
    "event_types": 55,
    "query_state_selectors": 10,
    "fragments": 10,
    "governed_tables": 13,
    "projector_files": 7,
    "god_object_max_loc": 1500,
    "dead_code_files": 0,
}


def load_history() -> list[dict]:
    if not HISTORY_FILE.exists():
        return []
    snapshots = []
    with open(HISTORY_FILE) as f:
        for line in f:
            line = line.strip()
            if line:
                snapshots.append(json.loads(line))
    return snapshots


def build_report(snapshots: list[dict]) -> str:
    if not snapshots:
        return "**No architecture history yet.** Record a snapshot with `make architecture-record`.\n"

    latest = snapshots[-1]
    first = snapshots[0]
    ts = latest.get("ts", "unknown")

    # 7-day window
    cutoff = (datetime.now(UTC) - timedelta(days=7)).isoformat()
    recent = [s for s in snapshots if s.get("ts", "") >= cutoff]
    week_ago = recent[0] if recent else first

    lines = [
        "# Runtime Health Dashboard",
        "",
        f"> Last updated: `{ts}` | Snapshots recorded: {len(snapshots)}",
        "",
        "## Current Metrics",
        "",
        "| Metric | Current | 7-Day Δ | All-Time Δ | Target | Gap |",
        "|---|---:|---:|---:|---:|---:|",
    ]

    for key, name in METRICS:
        cur = latest.get(key, "?")
        target = ASPIRATIONAL_TARGETS.get(key, "—")
        week_delta = _delta(cur, week_ago.get(key, cur))
        all_delta = _delta(cur, first.get(key, cur))
        gap = f"-{cur - target}" if isinstance(cur, int) and isinstance(target, int) and cur >= target else (
            f"+{target - cur}" if isinstance(cur, int) and isinstance(target, int) else "—"
        )
        lines.append(f"| `{name}` | {cur} | {week_delta} | {all_delta} | {target} | {gap} |")

    # Trend summary
    lines.append("")
    lines.append("## Trend (since first recording)")
    lines.append("")
    improved = []
    worsened = []
    stable = []
    for key, name in METRICS:
        cur = latest.get(key, 0)
        old = first.get(key, cur)
        if not isinstance(cur, int) or not isinstance(old, int):
            continue
        if cur < old:
            improved.append(f"- **{name}**: {old} → {cur} (-{old - cur})")
        elif cur > old:
            worsened.append(f"- **{name}**: {old} → {cur} (+{cur - old})")
        else:
            stable.append(f"- {name}: {cur} (unchanged)")

    if improved:
        lines.append("### 📉 Improving")
        lines.extend(improved)
        lines.append("")
    if worsened:
        lines.append("### 📈 Worsening")
        lines.extend(worsened)
        lines.append("")
    if stable:
        lines.append("### ➡️ Stable")
        lines.extend(stable)
        lines.append("")

    # Gap to target
    lines.append("## Distance to 1-Year Target")
    lines.append("")
    for key, name in METRICS:
        cur_val: int | str = latest.get(key, 0)
        tgt: int | None = ASPIRATIONAL_TARGETS.get(key)
        if isinstance(cur_val, int) and isinstance(tgt, int) and cur_val > tgt:
            pct = round((cur_val - tgt) / tgt * 100) if tgt > 0 else 100
            lines.append(f"- **{name}**: {cur_val} → {tgt} (need -{cur_val - tgt}, {pct}% over)")
        elif isinstance(cur_val, int) and isinstance(tgt, int) and cur_val <= tgt:
            lines.append(f"- {name}: {cur_val} ≤ {tgt} ✅")

    return "\n".join(lines) + "\n"


def _delta(cur: int | str, old: int | str) -> str:
    if not isinstance(cur, int) or not isinstance(old, int):
        return "—"
    d = cur - old
    if d == 0:
        return "0"
    sign = "+" if d > 0 else ""
    return f"{sign}{d}"


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    snapshots = load_history()
    report = build_report(snapshots)
    print(report)

    if "--write" in args:
        REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
        REPORT_FILE.write_text(report)
        print(f"Report written to {REPORT_FILE}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
