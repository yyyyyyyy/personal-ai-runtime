"""Calendar MCP Server — local ICS file operations under ``~/calendar``."""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

_CALENDAR_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _ics_escape(value: str) -> str:
    """Escape text for ICS property values (RFC 5545)."""
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _ics_unescape(value: str) -> str:
    return (
        value.replace("\\n", "\n")
        .replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\\\", "\\")
    )


def _safe_calendar_name(name: str) -> str | None:
    cleaned = (name or "default").strip() or "default"
    if not _CALENDAR_NAME_RE.fullmatch(cleaned):
        return None
    return cleaned


def _unfold_ics(content: str) -> str:
    """Join RFC 5545 folded lines (continuation lines start with space/tab)."""
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    out: list[str] = []
    for line in normalized.split("\n"):
        if out and line[:1] in (" ", "\t"):
            out[-1] += line[1:]
        else:
            out.append(line)
    return "\n".join(out)


def _ics_prop(block: str, name: str) -> str | None:
    """Extract a VEVENT property value, ignoring optional parameters."""
    prefix = name.upper()
    for line in block.splitlines():
        upper = line.upper()
        if upper.startswith(f"{prefix}:") or upper.startswith(f"{prefix};"):
            return _ics_unescape(line.split(":", 1)[1].strip())
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
    """Local ICS calendar operations (one ``.ics`` file per calendar name)."""

    def __init__(self, ics_dir: str = "~/calendar"):
        self.ics_dir = Path(ics_dir).expanduser()

    def _ensure_dir(self) -> None:
        self.ics_dir.mkdir(parents=True, exist_ok=True)

    def _ics_files(self, calendar: str | None) -> list[tuple[str, Path]]:
        """Return ``(calendar_name, path)`` pairs to scan.

        ``calendar=None`` aggregates every ``*.ics`` in the directory.
        """
        if not self.ics_dir.is_dir():
            return []
        if calendar is None:
            pairs: list[tuple[str, Path]] = []
            for path in sorted(self.ics_dir.glob("*.ics")):
                pairs.append((path.stem, path))
            return pairs
        safe = _safe_calendar_name(calendar)
        if safe is None:
            return []
        path = self.ics_dir / f"{safe}.ics"
        if path.is_file():
            return [(safe, path)]
        return []

    def _iter_events(self, calendar: str | None = "default") -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        seen_uids: set[str] = set()
        for cal_name, ics_file in self._ics_files(calendar):
            content = _unfold_ics(ics_file.read_text(encoding="utf-8"))
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

                uid = _ics_prop(block, "UID") or ""
                if uid and uid in seen_uids:
                    continue
                if uid:
                    seen_uids.add(uid)

                events.append({
                    "calendar": cal_name,
                    "title": summary,
                    "start": _to_iso(start_val),
                    "end": end_iso,
                    "location": _ics_prop(block, "LOCATION") or "",
                    "all_day": all_day,
                    "file": ics_file.name,
                    "uid": uid,
                    "_sort_date": _event_date(start_val),
                })
        return events

    @staticmethod
    def _filter_window(
        events: list[dict[str, Any]],
        start_date: date,
        days: int,
    ) -> list[dict[str, Any]]:
        span = max(1, int(days))
        filtered: list[dict[str, Any]] = []
        for event in events:
            delta = (event["_sort_date"] - start_date).days
            # Inclusive window: day 0 through day N.
            if 0 <= delta <= span:
                item = {k: v for k, v in event.items() if not k.startswith("_")}
                item["days_away"] = delta
                filtered.append(item)
        return filtered

    def list_events(self, calendar: str = "default", date: str = "", days: int = 7) -> str:
        """List events from one calendar file for a date range."""
        safe = _safe_calendar_name(calendar)
        if safe is None:
            return json.dumps({"error": f"Invalid calendar name: {calendar!r}"})

        if not date:
            date = datetime.now().strftime("%Y-%m-%d")
        start_date = datetime.strptime(date, "%Y-%m-%d").date()
        span = max(1, int(days))

        events = self._filter_window(self._iter_events(calendar=safe), start_date, span)
        events.sort(key=lambda e: (e.get("start") or "", e.get("title") or ""))
        return json.dumps({
            "calendar": safe,
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
        safe = _safe_calendar_name(calendar)
        if safe is None:
            return json.dumps({"error": f"Invalid calendar name: {calendar!r}"})

        self._ensure_dir()
        ics_path = self.ics_dir / f"{safe}.ics"
        now = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        start_dt = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
        end_dt = start_dt + timedelta(minutes=max(1, int(duration_minutes)))
        dt_start = start_dt.strftime("%Y%m%dT%H%M%S")
        dt_end = end_dt.strftime("%Y%m%dT%H%M%S")
        uid = f"{uuid.uuid4()}@personal-ai-runtime"

        location_line = f"LOCATION:{_ics_escape(location)}\n" if location else ""
        description_line = f"DESCRIPTION:{_ics_escape(description)}\n" if description else ""
        entry = (
            "BEGIN:VEVENT\n"
            f"UID:{uid}\n"
            f"DTSTART:{dt_start}\n"
            f"DTEND:{dt_end}\n"
            f"SUMMARY:{_ics_escape(title)}\n"
            f"{location_line}"
            f"{description_line}"
            f"DTSTAMP:{now}\n"
            "END:VEVENT\n"
        )

        existing = ics_path.read_text(encoding="utf-8") if ics_path.exists() else (
            "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//PersonalAIRuntime//Calendar//EN\n"
            "END:VCALENDAR\n"
        )
        if "END:VCALENDAR" not in existing:
            existing += "END:VCALENDAR\n"

        updated = existing.replace("END:VCALENDAR", entry + "END:VCALENDAR", 1)
        ics_path.write_text(updated, encoding="utf-8")

        return json.dumps({
            "success": True,
            "title": title,
            "date": date,
            "time": time,
            "start": start_dt.isoformat(),
            "end": end_dt.isoformat(),
            "location": location,
            "calendar": safe,
            "uid": uid,
        })

    def get_upcoming(self, days: int = 7) -> str:
        """Get upcoming events across all local calendars within N days."""
        span = max(1, int(days))
        today = datetime.now().date()
        events = self._filter_window(self._iter_events(calendar=None), today, span)
        events.sort(key=lambda e: (int(e.get("days_away", 0)), e.get("start") or ""))
        return json.dumps({"upcoming_days": span, "count": len(events), "events": events[:20]})


calendar_server = CalendarServer()
