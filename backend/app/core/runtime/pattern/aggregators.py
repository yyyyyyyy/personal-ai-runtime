"""Pattern Aggregator — sliding-window statistical engine.

Design (per Cognitive Architecture):
  - Subscribes to ActivityNormalized events (Evidence Layer)
  - Maintains sliding-window counters (14d / 30d) in memory
  - Emits PatternDetected when a pattern crosses the significance threshold
  - Does NOT write to the patterns table directly — that's the Projector's job
  - Fully deterministic: given the same events in the same order, produces the
    same PatternDetected events (confidence formula excluded — that lives in
    the Belief Layer).

Pattern types:
  time_distribution  — activity_category × time_of_day over a window
  topic_distribution — topic frequency over a window
  trend              — daily-count slope over a window

Statistical methods are pure-SQL/pure-Python — no LLM calls.  Interpretation
belongs to the Belief Layer.
"""

from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict, deque
from collections.abc import Callable
from typing import Any

from app.core.runtime.kernel.event import Event
from app.core.runtime.kernel_instance import kernel

logger = logging.getLogger(__name__)

FOURTEEN_DAYS = 14
THIRTY_DAYS = 30

SIGNIFICANCE_THRESHOLD = 3  # minimum events per category×time_of_day bucket


def _make_pattern_id(
    pattern_type: str, metric: str, window_days: int, bucket: str
) -> str:
    """Deterministic aggregate_id: same (type, metric, window, bucket) ⇒ same id."""
    raw = f"{pattern_type}:{metric}:{window_days}:{bucket}"
    import hashlib

    return f"pat_{hashlib.sha256(raw.encode()).hexdigest()[:16]}"


def _date_key(ts: str) -> str:
    return ts[:10]


def _time_of_day(ts: str) -> str:
    try:
        hour = int(ts[11:13])
    except (ValueError, IndexError):
        return "unknown"
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 22:
        return "evening"
    return "night"


class PatternAggregator:
    """Maintains sliding windows and emits PatternDetected on significance."""

    def __init__(self):
        self._events_14d: deque[dict[str, Any]] = deque()
        self._events_30d: deque[dict[str, Any]] = deque()
        self._unsub: Callable[[], None] | None = None

    def start(self) -> None:
        if self._unsub is not None:
            return
        self._unsub = kernel.subscribe_events(
            self._on_event,
            type="ActivityNormalized",
        )
        logger.info("PatternAggregator started — listening for ActivityNormalized")

    def stop(self) -> None:
        if self._unsub is not None:
            self._unsub()
            self._unsub = None
        logger.info("PatternAggregator stopped")

    def _on_event(self, event: Event) -> None:
        p = event.payload
        entry = {
            "category": p.get("activity_category", ""),
            "topic": p.get("topic", ""),
            "time_of_day": p.get("time_of_day", _time_of_day(event.ts)),
            "duration_minutes": p.get("duration_minutes", 0),
            "ts": event.ts,
            "event_id": event.id,
        }
        if not entry["category"]:
            return

        self._events_14d.append(entry)
        self._events_30d.append(entry)
        self._prune()

        if len(self._events_14d) >= 5:
            self._check_time_distribution(FOURTEEN_DAYS)
        if len(self._events_30d) >= 5:
            self._check_time_distribution(THIRTY_DAYS)
        if len(self._events_14d) >= 10:
            self._check_topic_distribution(FOURTEEN_DAYS)
            self._check_trend(FOURTEEN_DAYS)
        if len(self._events_30d) >= 10:
            self._check_trend(THIRTY_DAYS)

    def _prune(self) -> None:
        """Remove entries outside the sliding windows (based on ts)."""
        now = self._events_14d[-1]["ts"] if self._events_14d else None
        if now is None:
            return

        def _window_cutoff(days: int) -> str:
            try:
                from datetime import datetime, timedelta

                dt = datetime.fromisoformat(now)
                return (dt - timedelta(days=days)).isoformat()
            except ValueError:
                return now

        cutoff_14 = _window_cutoff(FOURTEEN_DAYS)
        cutoff_30 = _window_cutoff(THIRTY_DAYS)

        while self._events_14d and self._events_14d[0]["ts"] < cutoff_14:
            self._events_14d.popleft()
        while self._events_30d and self._events_30d[0]["ts"] < cutoff_30:
            self._events_30d.popleft()

    # --- Pattern detectors --------------------------------------------------

    def _check_time_distribution(self, window_days: int) -> None:
        """Detect time-of-day distribution patterns per activity category."""
        events = self._events_14d if window_days == FOURTEEN_DAYS else self._events_30d

        # Group by (category, time_of_day)
        cat_tod = defaultdict(list)
        for e in events:
            cat_tod[(e["category"], e["time_of_day"])].append(e)

        for (category, tod), entries in cat_tod.items():
            if len(entries) < SIGNIFICANCE_THRESHOLD:
                continue

            total = sum(entry["duration_minutes"] for entry in events)
            if total == 0:
                continue

            # Recompute total for just this category across all time_of_day
            category_total = sum(
                sum(e["duration_minutes"] for e in es)
                for (c, _), es in cat_tod.items()
                if c == category
            )
            if category_total == 0:
                continue

            tod_duration = sum(e["duration_minutes"] for e in entries)
            proportion = round(tod_duration / category_total, 4)
            if proportion < 0.15:
                continue

            statistics = json.dumps(
                {
                    "time_of_day": tod,
                    "proportion": proportion,
                    "duration_minutes": tod_duration,
                    "total_duration_minutes": category_total,
                    "sample_count": len(entries),
                }
            )
            evidence_chain = json.dumps([e["event_id"] for e in entries])

            pattern_id = _make_pattern_id(
                "time_distribution", category, window_days, tod
            )
            kernel.emit_event(
                type="PatternDetected",
                aggregate_type="pattern",
                aggregate_id=pattern_id,
                payload={
                    "pattern_type": "time_distribution",
                    "metric": category,
                    "window_days": window_days,
                    "statistics": statistics,
                    "evidence_chain": evidence_chain,
                },
                actor="pattern_aggregator",
            )

    def _check_topic_distribution(self, window_days: int) -> None:
        """Detect topic frequency patterns."""
        events = self._events_14d if window_days == FOURTEEN_DAYS else self._events_30d
        topic_counter: Counter[str] = Counter()
        topic_evidence: dict[str, list[str]] = defaultdict(list)
        for e in events:
            topic = e["topic"]
            if not topic:
                continue
            topic_counter[topic] += 1
            topic_evidence[topic].append(e["event_id"])

        total = sum(topic_counter.values())
        if total < SIGNIFICANCE_THRESHOLD:
            return

        for topic, count in topic_counter.most_common():
            proportion = round(count / total, 4)
            if proportion < 0.10:
                continue

            statistics = json.dumps(
                {
                    "topic": topic,
                    "count": count,
                    "proportion": proportion,
                    "total_activities": total,
                }
            )
            evidence_chain = json.dumps(topic_evidence[topic])

            pattern_id = _make_pattern_id(
                "topic_distribution", "activity", window_days, topic
            )
            kernel.emit_event(
                type="PatternDetected",
                aggregate_type="pattern",
                aggregate_id=pattern_id,
                payload={
                    "pattern_type": "topic_distribution",
                    "metric": "activity",
                    "window_days": window_days,
                    "statistics": statistics,
                    "evidence_chain": evidence_chain,
                },
                actor="pattern_aggregator",
            )

    def _check_trend(self, window_days: int) -> None:
        """Detect daily-count trends per activity category (simple slope)."""
        events = self._events_14d if window_days == FOURTEEN_DAYS else self._events_30d
        # Group by (category, date)
        cat_date: dict[str, Counter[str]] = defaultdict(Counter)
        cat_evidence: dict[tuple[str, str], list[str]] = defaultdict(list)
        for e in events:
            cat = e["category"]
            date = _date_key(e["ts"])
            key = (cat, date)
            cat_date[cat][date] += 1
            cat_evidence[key].append(e["event_id"])

        for category, date_counts in cat_date.items():
            dates = sorted(date_counts.keys())
            if len(dates) < 5:
                continue

            counts = [date_counts[d] for d in dates]
            # Simple linear trend: slope via least-squares
            n = len(counts)
            x_mean = (n - 1) / 2
            y_mean = sum(counts) / n
            num = sum((i - x_mean) * (counts[i] - y_mean) for i in range(n))
            den = sum((i - x_mean) ** 2 for i in range(n))
            if den == 0:
                continue
            slope = num / den
            avg = y_mean
            if avg == 0:
                continue
            normalized_slope = round(slope / avg, 4)  # per-day % change

            if abs(normalized_slope) < 0.02:
                continue  # not significant

            direction = "increasing" if slope > 0 else "decreasing"
            first_half_avg = sum(counts[: n // 2]) / max(n // 2, 1)
            second_half_avg = sum(counts[n // 2 :]) / max(n - n // 2, 1)

            statistics = json.dumps(
                {
                    "category": category,
                    "direction": direction,
                    "normalized_slope": normalized_slope,
                    "first_half_avg_daily_count": round(first_half_avg, 2),
                    "second_half_avg_daily_count": round(second_half_avg, 2),
                    "sample_count": n,
                    "total_events": sum(counts),
                }
            )
            evidence_chain = json.dumps(
                [eid for (c, d), eids in cat_evidence.items() if c == category for eid in eids]
            )

            pattern_id = _make_pattern_id(
                "trend", category, window_days, direction
            )
            kernel.emit_event(
                type="PatternDetected",
                aggregate_type="pattern",
                aggregate_id=pattern_id,
                payload={
                    "pattern_type": "trend",
                    "metric": category,
                    "window_days": window_days,
                    "statistics": statistics,
                    "evidence_chain": evidence_chain,
                },
                actor="pattern_aggregator",
            )


pattern_aggregator = PatternAggregator()
