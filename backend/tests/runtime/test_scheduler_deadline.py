"""Scheduler deadline alert tests."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch


def test_deadline_target_dates_use_utc():
    from app.core.runtime.scheduler import _deadline_target_dates

    utc_now = datetime(2026, 6, 10, 23, 30, 0, tzinfo=UTC)
    with patch("app.core.runtime.scheduler.datetime") as mock_dt:
        mock_dt.now.return_value = utc_now
        mock_dt.fromisoformat = datetime.fromisoformat
        targets = _deadline_target_dates()

    assert targets == {
        datetime(2026, 6, 11).date(),
        datetime(2026, 6, 13).date(),
    }


def test_deadline_target_dates_not_local_today():
    """Ensure we anchor on UTC, not local date.today()."""
    from app.core.runtime.scheduler import _deadline_target_dates

    utc_now = datetime(2026, 6, 10, 20, 0, 0, tzinfo=UTC)
    wrong_local_today = datetime(2026, 6, 11).date()

    with patch("app.core.runtime.scheduler.datetime") as mock_dt:
        mock_dt.now.return_value = utc_now
        mock_dt.fromisoformat = datetime.fromisoformat
        utc_targets = _deadline_target_dates()

    assert utc_targets == {
        datetime(2026, 6, 11).date(),
        datetime(2026, 6, 13).date(),
    }
    wrong_targets = {wrong_local_today + timedelta(days=offset) for offset in (1, 3)}
    assert utc_targets != wrong_targets
