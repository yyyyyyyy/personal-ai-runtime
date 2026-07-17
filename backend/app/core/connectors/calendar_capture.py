"""Calendar read-only connector — emits ObservationRecorded (Experience capture)."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


def _calendar_dedup_key(item: dict[str, Any], *, calendar: str) -> str:
    """Stable key for idempotent calendar observations."""
    cal = str(item.get("calendar") or calendar).strip() or "default"
    uid = str(item.get("uid") or "").strip()
    if uid:
        return f"calendar:{cal}:uid:{uid}"
    title = str(item.get("title") or "").strip()
    start = str(item.get("start") or "").strip()
    return f"calendar:{cal}:{start}:{title}"


def _observation_id(dedup_key: str) -> str:
    digest = hashlib.sha1(dedup_key.encode("utf-8")).hexdigest()[:16]
    return f"obs_cal_{digest}"


def _already_captured(kernel, obs_id: str) -> bool:
    existing = kernel.read_events(
        type="ObservationRecorded",
        aggregate_type="observation",
        aggregate_id=obs_id,
        limit=1,
    )
    return bool(existing)


def capture_calendar_observations(
    kernel,
    *,
    calendar: str = "default",
    date: str | None = None,
    days: int = 7,
    actor: str = "connector:calendar",
) -> list[str]:
    """Ingest calendar events as ObservationRecorded events.

    Idempotent by event identity (UID when present, else calendar+start+title).
    Returns newly emitted observation ids (duplicates are skipped).
    """
    from app.core.harness.builtin_tools import calendar as cal_mod

    try:
        raw = cal_mod.calendar_server.list_events(
            calendar=calendar, date=date or "", days=days
        )
        data = json.loads(raw)
    except Exception:
        logger.warning("calendar capture: list_events failed", exc_info=True)
        return []

    if not isinstance(data, dict):
        logger.warning("calendar capture: unexpected list_events payload type")
        return []
    if data.get("error"):
        logger.warning("calendar capture: list_events error: %s", data.get("error"))
        return []

    events = data.get("events") or []
    if not isinstance(events, list):
        logger.warning("calendar capture: events is not a list")
        return []

    ids: list[str] = []
    for item in events:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        start = item.get("start")
        if not title or not start:
            continue

        try:
            dedup_key = _calendar_dedup_key(item, calendar=calendar)
            obs_id = _observation_id(dedup_key)
            if _already_captured(kernel, obs_id):
                continue

            payload: dict[str, Any] = {
                "source": "calendar",
                "calendar": item.get("calendar", calendar),
                "title": title,
                "start": start,
                "end": item.get("end"),
                "location": item.get("location") or "",
                "all_day": bool(item.get("all_day")),
                "file": item.get("file"),
                "uid": item.get("uid") or "",
                "days_away": item.get("days_away"),
                "dedup_key": dedup_key,
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
        except Exception:
            logger.warning(
                "calendar capture: failed to emit observation for %r", title, exc_info=True
            )
            continue

    return ids
