"""Domain constants shared by the seed generator, feature builders and services."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

SPRINT_DAYS = 14
# Sprint capacity in story points for a person working 40 hours a week.
POINTS_PER_40H_SPRINT = 8.0
OVERLOAD_THRESHOLD = 0.85
# Share of each team's throughput that goes to the launch program (the rest is BAU).
PROGRAM_ALLOCATION = 0.7


def capacity_points(capacity_hours_per_week: float) -> float:
    return capacity_hours_per_week / 40.0 * POINTS_PER_40H_SPRINT


def utc_midnight(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=UTC)


def sprint_window(sprint_starts: list[date], t: datetime) -> tuple[datetime, datetime] | None:
    """Return the [start, end) window of the sprint containing `t`, if any."""
    for s in sorted(sprint_starts, reverse=True):
        start = utc_midnight(s)
        if start <= t < start + timedelta(days=SPRINT_DAYS):
            return start, start + timedelta(days=SPRINT_DAYS)
    return None
