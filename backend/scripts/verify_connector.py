#!/usr/bin/env python
"""Connector verification — calendar capture emits ObservationRecorded via Kernel."""

from __future__ import annotations

from pathlib import Path

import sys
from datetime import datetime

_BACKEND = str(Path(__file__).resolve().parents[1])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from scripts._bootstrap import BACKEND_ROOT, ephemeral_kernel


def main() -> int:
    violations: list[str] = []
    with ephemeral_kernel("verify_connector.db", install_singleton=True) as (_db, k):
        from app.core.connectors.calendar_capture import capture_calendar_observations
        from app.core.harness.builtin_tools.calendar import CalendarServer

        import app.core.harness.builtin_tools.calendar as cal_mod

        ics_dir = BACKEND_ROOT / "data" / "verify_calendar"
        ics_dir.mkdir(parents=True, exist_ok=True)
        today = datetime.now().strftime("%Y-%m-%d")
        ics_path = ics_dir / "default.ics"
        ics_path.write_text(
            "BEGIN:VCALENDAR\nVERSION:2.0\n"
            "BEGIN:VEVENT\n"
            f"DTSTART:{today.replace('-', '')}T090000\n"
            f"DTEND:{today.replace('-', '')}T100000\n"
            "SUMMARY:Verify Connector Meeting\n"
            "END:VEVENT\nEND:VCALENDAR\n",
            encoding="utf-8",
        )

        cal_mod.calendar_server = CalendarServer(ics_dir=str(ics_dir))

        ids = capture_calendar_observations(k, calendar="default", date=today)
        if not ids:
            violations.append("connector: no ObservationRecorded emitted")

        obs_events = k.read_events(type="ObservationRecorded", order="asc")
        if len(obs_events) < 1:
            violations.append("connector: ObservationRecorded missing from event_log")
        else:
            actor = obs_events[0].actor
            if not str(actor).startswith("connector:"):
                violations.append(f"connector: unexpected actor {actor!r}")

    if violations:
        print("CONNECTOR VERIFICATION FAILED", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        return 1

    print("CONNECTOR VERIFICATION PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
