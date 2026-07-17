"""Calendar MCP Server — local ICS file and Google Calendar operations."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any


def _ics_prop(block: str, name: str) -> str | None:
    """Extract a VEVENT property value, ignoring optional parameters."""
    prefix = name.upper()
    for line in block.splitlines():
        upper = line.upper()
        if upper.startswith(f"{prefix}:") or upper.startswith(f"{prefix};"):
            return line.split(":", 1)[1].strip()
    return None


def _parse_ics_dt(raw: str) -> tuple[datetime | date, bool]:
    """Parse ICS date/datetime. Returns (value, all_day)."""
    value = raw.strip()
    if value.endswith("Z"):
        value = value[:-1]
        dt = datetime.strptime(value, "%Y%m%dT%H%M%S").replace(tzinfo=UTC)
        return dt, False
    if "T" in value:
        return datetime.strptime(value, "%Y%m%dT%H%M%S"), False
    return datetime.strptime(value[:8], "%Y%m%d").date(), True


def _to_iso(value: datetime | date) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return value.isoformat()


def _event_date(value: datetime | date) -> date:
    return value.date() if isinstance(value, datetime) else value


class CalendarServer:
    """Local ICS calendar operations."""

    def __init__(self, ics_dir: str = "~/calendar"):
        self.ics_dir = Path(ics_dir).expanduser()
        self.ics_dir.mkdir(parents=True, exist_ok=True)

    def _iter_events(self, calendar: str = "default") -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for ics_file in self.ics_dir.glob("*.ics"):
            content = ics_file.read_text(encoding="utf-8")
            for block in content.split("BEGIN:VEVENT")[1:]:
                summary = _ics_prop(block, "SUMMARY")
                dt_raw = _ics_prop(block, "DTSTART")
                if not summary or not dt_raw:
                    continue
                try:
                    start_val, all_day = _parse_ics_dt(dt_raw)
                except ValueError:
                    continue

                end_iso = ""
                end_raw = _ics_prop(block, "DTEND")
                if end_raw:
                    try:
                        end_val, _ = _parse_ics_dt(end_raw)
                        end_iso = _to_iso(end_val)
                    except ValueError:
                        end_iso = ""

                events.append({
                    "calendar": calendar,
                    "title": summary,
                    "start": _to_iso(start_val),
                    "end": end_iso,
                    "location": _ics_prop(block, "LOCATION") or "",
                    "all_day": all_day,
                    "file": ics_file.name,
                    "uid": _ics_prop(block, "UID") or "",
                    "_sort_date": _event_date(start_val),
                })
        return events

    def list_events(self, calendar: str = "default", date: str = "", days: int = 7) -> str:
        """List calendar events for a date range."""
        if not date:
            date = datetime.now().strftime("%Y-%m-%d")
        start_date = datetime.strptime(date, "%Y-%m-%d").date()
        span = max(1, int(days))

        events = []
        for event in self._iter_events(calendar=calendar):
            delta = (event["_sort_date"] - start_date).days
            # Inclusive window: today (0) through day N (span), matching prior semantics.
            if 0 <= delta <= span:
                item = {k: v for k, v in event.items() if not k.startswith("_")}
                item["days_away"] = delta
                events.append(item)

        events.sort(key=lambda e: (e.get("start") or "", e.get("title") or ""))
        return json.dumps({
            "calendar": calendar,
            "date": date,
            "days": span,
            "count": len(events),
            "events": events[:20],
        })

    def add_event(
        self,
        title: str,
        date: str,
        time: str = "09:00",
        duration_minutes: int = 60,
        calendar: str = "default",
        description: str = "",
        location: str = "",
    ) -> str:
        """Add an event to the calendar ICS file."""
        ics_path = self.ics_dir / f"{calendar}.ics"
        now = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        start_dt = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
        end_dt = start_dt + timedelta(minutes=max(1, int(duration_minutes)))
        dt_start = start_dt.strftime("%Y%m%dT%H%M%S")
        dt_end = end_dt.strftime("%Y%m%dT%H%M%S")

        location_line = f"LOCATION:{location}\n" if location else ""
        entry = (
            "BEGIN:VEVENT\n"
            f"DTSTART:{dt_start}\n"
            f"DTEND:{dt_end}\n"
            f"SUMMARY:{title}\n"
            f"{location_line}"
            f"DESCRIPTION:{description}\n"
            f"DTSTAMP:{now}\n"
            "END:VEVENT\n"
        )

        existing = ics_path.read_text(encoding="utf-8") if ics_path.exists() else (
            "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//PersonalAIRuntime//Calendar//EN\n"
            "END:VCALENDAR\n"
        )
        if "END:VCALENDAR" not in existing:
            existing += "END:VCALENDAR\n"

        updated = existing.replace("END:VCALENDAR", entry + "END:VCALENDAR")
        ics_path.write_text(updated, encoding="utf-8")

        return json.dumps({
            "success": True,
            "title": title,
            "date": date,
            "time": time,
            "start": start_dt.isoformat(),
            "end": end_dt.isoformat(),
            "location": location,
            "calendar": calendar,
        })

    def get_upcoming(self, days: int = 7) -> str:
        """Get upcoming events within N days (including today)."""
        span = max(1, int(days))
        today = datetime.now().date()
        events = []
        for event in self._iter_events():
            delta = (event["_sort_date"] - today).days
            if 0 <= delta <= span:
                item = {k: v for k, v in event.items() if not k.startswith("_")}
                item["days_away"] = delta
                events.append(item)

        events.sort(key=lambda e: (int(e.get("days_away", 0)), e.get("start") or ""))
        return json.dumps({"upcoming_days": span, "count": len(events), "events": events[:20]})


calendar_server = CalendarServer()
