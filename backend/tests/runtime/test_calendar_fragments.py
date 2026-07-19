"""CalendarServer ICS parsing and fragment formatting tests."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.core.harness.builtin_tools.calendar import CalendarServer
from app.context_runtime import RuntimeContext
from app.fragments.calendar import DailyAgendaFragment, UpcomingEventsFragment


def _write_ics(path: Path, body: str) -> None:
    path.write_text(
        "BEGIN:VCALENDAR\nVERSION:2.0\n" + body + "END:VCALENDAR\n",
        encoding="utf-8",
    )


class TestCalendarServer:
    def test_list_events_parses_vevent_fields(self, tmp_path: Path):
        today = datetime.now().strftime("%Y-%m-%d")
        ymd = today.replace("-", "")
        _write_ics(
            tmp_path / "default.ics",
            "BEGIN:VEVENT\n"
            f"DTSTART:{ymd}T093000\n"
            f"DTEND:{ymd}T103000\n"
            "SUMMARY:Design sync\n"
            "LOCATION:Room B\n"
            "END:VEVENT\n",
        )
        server = CalendarServer(ics_dir=str(tmp_path))
        data = json.loads(server.list_events(date=today, days=1))

        assert data["count"] == 1
        event = data["events"][0]
        assert event["title"] == "Design sync"
        assert event["start"].startswith(f"{today}T09:30:00")
        assert event["end"].startswith(f"{today}T10:30:00")
        assert event["location"] == "Room B"
        assert event["all_day"] is False
        assert event["days_away"] == 0

    def test_list_events_supports_all_day_and_params(self, tmp_path: Path):
        today = datetime.now().strftime("%Y-%m-%d")
        ymd = today.replace("-", "")
        _write_ics(
            tmp_path / "default.ics",
            "BEGIN:VEVENT\n"
            f"DTSTART;VALUE=DATE:{ymd}\n"
            f"DTEND;VALUE=DATE:{(datetime.now().date() + timedelta(days=1)).strftime('%Y%m%d')}\n"
            "SUMMARY:Holiday\n"
            "END:VEVENT\n",
        )
        server = CalendarServer(ics_dir=str(tmp_path))
        data = json.loads(server.list_events(date=today, days=1))

        assert data["count"] == 1
        event = data["events"][0]
        assert event["title"] == "Holiday"
        assert event["start"] == today
        assert event["all_day"] is True

    def test_get_upcoming_unified_schema(self, tmp_path: Path):
        tomorrow = datetime.now().date() + timedelta(days=1)
        ymd = tomorrow.strftime("%Y%m%d")
        _write_ics(
            tmp_path / "default.ics",
            "BEGIN:VEVENT\n"
            f"DTSTART:{ymd}T140000\n"
            f"DTEND:{ymd}T150000\n"
            "SUMMARY:Review\n"
            "END:VEVENT\n",
        )
        server = CalendarServer(ics_dir=str(tmp_path))
        data = json.loads(server.get_upcoming(days=7))

        assert data["count"] == 1
        event = data["events"][0]
        assert event["title"] == "Review"
        assert "start" in event
        assert event["days_away"] == 1

    def test_add_event_writes_end_and_location(self, tmp_path: Path):
        server = CalendarServer(ics_dir=str(tmp_path))
        today = datetime.now().strftime("%Y-%m-%d")
        raw = server.add_event(
            title="Demo",
            date=today,
            time="11:00",
            duration_minutes=45,
            location="Lab",
        )
        result = json.loads(raw)
        content = (tmp_path / "default.ics").read_text(encoding="utf-8")

        assert result["success"] is True
        assert result["location"] == "Lab"
        assert result["uid"]
        assert f"UID:{result['uid']}" in content
        assert "LOCATION:Lab" in content
        assert "DTSTART:" in content and "DTEND:" in content
        listed = json.loads(server.list_events(date=today, days=1))
        assert listed["events"][0]["location"] == "Lab"

    def test_list_events_filters_by_calendar_file(self, tmp_path: Path):
        today = datetime.now().strftime("%Y-%m-%d")
        ymd = today.replace("-", "")
        _write_ics(
            tmp_path / "work.ics",
            "BEGIN:VEVENT\n"
            f"DTSTART:{ymd}T100000\n"
            "SUMMARY:Work only\n"
            "UID:work-1\n"
            "END:VEVENT\n",
        )
        _write_ics(
            tmp_path / "default.ics",
            "BEGIN:VEVENT\n"
            f"DTSTART:{ymd}T110000\n"
            "SUMMARY:Default only\n"
            "UID:default-1\n"
            "END:VEVENT\n",
        )
        server = CalendarServer(ics_dir=str(tmp_path))
        work = json.loads(server.list_events(calendar="work", date=today, days=1))
        assert work["count"] == 1
        assert work["events"][0]["title"] == "Work only"
        upcoming = json.loads(server.get_upcoming(days=1))
        titles = {e["title"] for e in upcoming["events"]}
        assert titles == {"Work only", "Default only"}

    def test_invalid_calendar_name_rejected(self, tmp_path: Path):
        server = CalendarServer(ics_dir=str(tmp_path))
        err = json.loads(server.add_event(title="x", date="2026-07-19", calendar="../evil"))
        assert "error" in err

    def test_folded_ics_lines_are_unfolded(self, tmp_path: Path):
        today = datetime.now().strftime("%Y-%m-%d")
        ymd = today.replace("-", "")
        # SUMMARY folded across two lines per RFC 5545.
        _write_ics(
            tmp_path / "default.ics",
            "BEGIN:VEVENT\n"
            f"DTSTART:{ymd}T090000\n"
            "SUMMARY:Folded \n"
            " Title\n"
            "UID:fold-1\n"
            "END:VEVENT\n",
        )
        server = CalendarServer(ics_dir=str(tmp_path))
        data = json.loads(server.list_events(date=today, days=1))
        assert data["count"] == 1
        assert data["events"][0]["title"] == "Folded Title"

    def test_init_does_not_create_calendar_dir(self, tmp_path: Path):
        missing = tmp_path / "no_such_calendar_dir"
        server = CalendarServer(ics_dir=str(missing))
        assert not missing.exists()
        listed = json.loads(server.list_events())
        assert listed["count"] == 0
        # Writing creates the directory lazily.
        today = datetime.now().strftime("%Y-%m-%d")
        result = json.loads(server.add_event(title="Lazy", date=today))
        assert result["success"] is True
        assert missing.is_dir()


class TestCalendarFragments:
    @pytest.mark.asyncio
    async def test_daily_agenda_formats_time_and_location(self, monkeypatch):
        monkeypatch.setattr(
            "app.core.runtime.read_ports.query_calendar_today_events",
            lambda: {
                "events": [
                    {
                        "title": "Standup",
                        "start": "2026-07-17T09:30:00",
                        "location": "Room A",
                        "all_day": False,
                    },
                    {
                        "title": "Offsite",
                        "start": "2026-07-17",
                        "all_day": True,
                    },
                ]
            },
        )
        r = await DailyAgendaFragment().collect(RuntimeContext())
        assert "09:30  Standup @Room A" in r.content
        assert "全天  Offsite" in r.content
        assert r.sources

    @pytest.mark.asyncio
    async def test_upcoming_formats_datetime(self, monkeypatch):
        monkeypatch.setattr(
            "app.core.runtime.read_ports.query_calendar_upcoming",
            lambda **kwargs: {
                "events": [
                    {
                        "title": "Ship review",
                        "start": "2026-07-18T14:00:00",
                        "all_day": False,
                    }
                ]
            },
        )
        r = await UpcomingEventsFragment().collect(RuntimeContext())
        assert "2026-07-18 14:00  Ship review" in r.content

    @pytest.mark.asyncio
    async def test_today_exception_keeps_identity_only(self, monkeypatch):
        def _boom():
            raise RuntimeError("calendar down")

        monkeypatch.setattr(
            "app.core.runtime.read_ports.query_calendar_today_events",
            _boom,
        )
        r = await DailyAgendaFragment().collect(RuntimeContext())
        assert "Calendar assistant" in r.content
        assert "暂无日程" not in r.content
