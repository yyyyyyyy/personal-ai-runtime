"""Calendar connector tests."""

from datetime import datetime
from pathlib import Path

from app.core.connectors.calendar_capture import capture_calendar_observations
from app.core.harness.builtin_tools.calendar import CalendarServer
from app.core.runtime.kernel import Kernel
from app.store.database import Database


def test_capture_emits_observation(tmp_path: Path):
    db = Database(db_path=str(tmp_path / "connector.db"))
    k = Kernel(db=db)
    today = datetime.now().strftime("%Y-%m-%d")
    ics = tmp_path / "default.ics"
    ics.write_text(
        "BEGIN:VCALENDAR\nVERSION:2.0\n"
        "BEGIN:VEVENT\n"
        f"DTSTART:{today.replace('-', '')}T090000\n"
        f"DTEND:{today.replace('-', '')}T100000\n"
        "SUMMARY:Unit Test Event\n"
        "END:VEVENT\nEND:VCALENDAR\n",
        encoding="utf-8",
    )
    import app.core.harness.builtin_tools.calendar as cal_mod

    cal_mod.calendar_server = CalendarServer(ics_dir=str(tmp_path))
    ids = capture_calendar_observations(k, date=today)
    assert ids
    events = k.read_events(type="ObservationRecorded")
    assert events[0].type == "ObservationRecorded"
