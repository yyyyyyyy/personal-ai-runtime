"""Calendar connector tests."""

from datetime import datetime
from pathlib import Path

from app.core.connectors.calendar_capture import (
    _calendar_dedup_key,
    _observation_id,
    capture_calendar_observations,
)
from app.core.harness.builtin_tools.calendar import CalendarServer
from app.core.runtime.kernel import Kernel
from app.store.database import Database


def _write_ics(tmp_path: Path, *, today: str, summary: str = "Unit Test Event", uid: str = "") -> None:
    uid_line = f"UID:{uid}\n" if uid else ""
    (tmp_path / "default.ics").write_text(
        "BEGIN:VCALENDAR\nVERSION:2.0\n"
        "BEGIN:VEVENT\n"
        f"{uid_line}"
        f"DTSTART:{today.replace('-', '')}T090000\n"
        f"DTEND:{today.replace('-', '')}T100000\n"
        f"SUMMARY:{summary}\n"
        "END:VEVENT\nEND:VCALENDAR\n",
        encoding="utf-8",
    )


def test_capture_emits_observation(tmp_path: Path):
    db = Database(db_path=str(tmp_path / "connector.db"))
    k = Kernel(db=db)
    today = datetime.now().strftime("%Y-%m-%d")
    _write_ics(tmp_path, today=today)

    import app.core.harness.builtin_tools.calendar as cal_mod

    cal_mod.calendar_server = CalendarServer(ics_dir=str(tmp_path))
    ids = capture_calendar_observations(k, date=today)
    assert ids
    events = k.read_events(type="ObservationRecorded")
    assert events[0].type == "ObservationRecorded"
    payload = events[0].payload
    assert payload["source"] == "calendar"
    assert payload["title"] == "Unit Test Event"
    assert payload["dedup_key"]
    assert payload["days_away"] == 0


def test_capture_is_idempotent(tmp_path: Path):
    db = Database(db_path=str(tmp_path / "connector_dedup.db"))
    k = Kernel(db=db)
    today = datetime.now().strftime("%Y-%m-%d")
    _write_ics(tmp_path, today=today, uid="evt-stable-1")

    import app.core.harness.builtin_tools.calendar as cal_mod

    cal_mod.calendar_server = CalendarServer(ics_dir=str(tmp_path))
    first = capture_calendar_observations(k, date=today)
    second = capture_calendar_observations(k, date=today)
    assert len(first) == 1
    assert second == []
    assert len(k.read_events(type="ObservationRecorded")) == 1


def test_capture_handles_list_events_failure(tmp_path: Path, monkeypatch):
    db = Database(db_path=str(tmp_path / "connector_err.db"))
    k = Kernel(db=db)

    import app.core.harness.builtin_tools.calendar as cal_mod

    class _Boom:
        def list_events(self, **kwargs):
            raise RuntimeError("ics broken")

    monkeypatch.setattr(cal_mod, "calendar_server", _Boom())
    assert capture_calendar_observations(k, date="2026-07-17") == []


def test_capture_handles_error_payload(tmp_path: Path, monkeypatch):
    db = Database(db_path=str(tmp_path / "connector_err_json.db"))
    k = Kernel(db=db)

    import app.core.harness.builtin_tools.calendar as cal_mod

    class _Err:
        def list_events(self, **kwargs):
            return '{"error": "no calendar"}'

    monkeypatch.setattr(cal_mod, "calendar_server", _Err())
    assert capture_calendar_observations(k, date="2026-07-17") == []


def test_dedup_key_prefers_uid():
    key = _calendar_dedup_key(
        {"calendar": "default", "uid": "abc", "title": "T", "start": "2026-01-01"},
        calendar="default",
    )
    assert key == "calendar:default:uid:abc"
    assert _observation_id(key).startswith("obs_cal_")
