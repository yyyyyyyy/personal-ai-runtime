#!/usr/bin/env python
"""Connector verification — calendar capture emits ObservationRecorded via Kernel."""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

os.environ.setdefault("LLM_API_KEY", "test-key")

from app.core.connectors.calendar_capture import capture_calendar_observations
from app.core.harness.mcp_servers.calendar import CalendarServer
from app.core.runtime.kernel import Kernel
from app.store.database import Database


def main() -> int:
    violations: list[str] = []
    db_path = _BACKEND_ROOT / "data" / "verify_connector.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = Database(db_path=str(db_path))
    k = Kernel(db=db)

    import app.core.harness.mcp_servers.calendar as cal_mod
    import app.core.runtime.kernel_instance as ki

    ki.kernel = k

    ics_dir = _BACKEND_ROOT / "data" / "verify_calendar"
    ics_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    ics_path = ics_dir / "default.ics"
    ics_path.write_text(
        f"BEGIN:VCALENDAR\nDTSTART:{today.replace('-', '')}T090000\n"
        f"X-VERIFY-DATE:{today}\n"
        f"SUMMARY:Verify Connector Meeting\nEND:VCALENDAR\n",
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
