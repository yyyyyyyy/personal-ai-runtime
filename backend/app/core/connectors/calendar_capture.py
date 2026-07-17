"""Calendar read-only connector — emits ObservationRecorded (Experience capture)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any


def capture_calendar_observations(
    kernel,
    *,
    calendar: str = "default",
    date: str | None = None,
    days: int = 7,
    actor: str = "connector:calendar",
) -> list[str]:
    """Ingest calendar events as ObservationRecorded events. Returns observation ids."""
    from app.core.harness.builtin_tools import calendar as cal_mod

    raw = cal_mod.calendar_server.list_events(
        calendar=calendar, date=date or "", days=days
    )
    data = json.loads(raw)
    ids: list[str] = []
    for item in data.get("events", []):
        obs_id = f"obs_{uuid.uuid4().hex[:12]}"
        payload: dict[str, Any] = {
            "source": "calendar",
            "calendar": item.get("calendar", calendar),
            "title": item.get("title", ""),
            "start": item.get("start"),
            "end": item.get("end"),
            "location": item.get("location") or "",
            "all_day": bool(item.get("all_day")),
            "file": item.get("file"),
            "captured_at": datetime.now(UTC).isoformat(),
        }
        kernel.emit_event(
            "ObservationRecorded",
            "observation",
            obs_id,
            payload=payload,
            actor=actor,
        )
        ids.append(obs_id)
    return ids
