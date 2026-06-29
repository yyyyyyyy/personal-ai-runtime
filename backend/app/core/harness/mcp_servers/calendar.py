"""Calendar MCP Server — local ICS file and Google Calendar operations."""

import json
from datetime import UTC, datetime
from pathlib import Path


class CalendarServer:
    """Calendar operations with ICS file support."""

    def __init__(self, ics_dir: str = "~/calendar"):
        self.ics_dir = Path(ics_dir).expanduser()
        self.ics_dir.mkdir(parents=True, exist_ok=True)

    def list_events(self, calendar: str = "default", date: str = "", days: int = 7) -> str:
        """List calendar events for a date range."""
        if not date:
            date = datetime.now().strftime("%Y-%m-%d")

        events = []
        for ics_file in self.ics_dir.glob("*.ics"):
            content = ics_file.read_text(encoding="utf-8")
            for line in content.splitlines():
                if line.startswith("DTSTART:") or line.startswith("DTEND:"):
                    continue
                if line.startswith("SUMMARY:"):
                    summary = line.replace("SUMMARY:", "").strip()
                    if date in content:
                        events.append({
                            "calendar": calendar,
                            "title": summary,
                            "file": ics_file.name,
                        })

        return json.dumps({
            "calendar": calendar,
            "date": date,
            "days": days,
            "count": len(events),
            "events": events[:20],
        })

    def add_event(self, title: str, date: str, time: str = "09:00", duration_minutes: int = 60,
                  calendar: str = "default", description: str = "") -> str:
        """Add an event to the calendar ICS file."""
        ics_path = self.ics_dir / f"{calendar}.ics"
        now = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        dt_start = date.replace("-", "") + "T" + time.replace(":", "") + "00"

        entry = (
            "BEGIN:VEVENT\n"
            f"DTSTART:{dt_start}\n"
            f"DTEND:{dt_start}\n"
            f"SUMMARY:{title}\n"
            f"DESCRIPTION:{description}\n"
            f"DTSTAMP:{now}\n"
            "END:VEVENT\n"
        )

        existing = ics_path.read_text(encoding="utf-8") if ics_path.exists() else (
            "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//PersonalAIRuntime//Calendar//EN\n"
        )
        if "END:VCALENDAR" not in existing:
            existing += "END:VCALENDAR\n"

        updated = existing.replace("END:VCALENDAR", entry + "END:VCALENDAR")
        ics_path.write_text(updated, encoding="utf-8")

        return json.dumps({"success": True, "title": title, "date": date, "time": time, "calendar": calendar})

    def get_upcoming(self, days: int = 7) -> str:
        """Get upcoming events within N days."""
        events = []
        today = datetime.now().date()
        for ics_file in self.ics_dir.glob("*.ics"):
            content = ics_file.read_text(encoding="utf-8")
            for block in content.split("BEGIN:VEVENT")[1:]:
                if "SUMMARY:" in block and "DTSTART:" in block:
                    dt_line = [ln for ln in block.splitlines() if ln.startswith("DTSTART:")][0]
                    dt_str = dt_line.replace("DTSTART:", "").strip()
                    try:
                        event_date = datetime.strptime(dt_str[:8], "%Y%m%d").date()
                        delta = (event_date - today).days
                        if 0 <= delta <= days:
                            summary = [ln for ln in block.splitlines() if ln.startswith("SUMMARY:")][0]
                            events.append({
                                "title": summary.replace("SUMMARY:", "").strip(),
                                "date": event_date.isoformat(),
                                "days_away": delta,
                            })
                    except (ValueError, IndexError):
                        continue

        events.sort(key=lambda e: int(str(e.get("days_away", 0))))
        return json.dumps({"upcoming_days": days, "count": len(events), "events": events[:20]})


calendar_server = CalendarServer()
