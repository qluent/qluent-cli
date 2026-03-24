"""Date inference — ported from backend/app/infrastructure/metric_trees.py."""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, timedelta

_ISO_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_LAST_N_DAYS_RE = re.compile(r"\b(?:last|past)\s+(\d{1,3})\s+days?\b")


@dataclass
class DateWindow:
    date_from: date
    date_to: date


@dataclass
class DateWindows:
    current: DateWindow
    comparison: DateWindow


def infer_windows(period: str, today: date | None = None) -> DateWindows:
    """Infer current and comparison date windows from a period string."""
    resolved_today = today or date.today()
    normalized = period.lower().strip()

    # Explicit ISO dates
    iso_dates = [date.fromisoformat(m) for m in _ISO_DATE_RE.findall(period)]
    if len(iso_dates) >= 4:
        c_start, c_end = sorted(iso_dates[:2])
        p_start, p_end = sorted(iso_dates[2:4])
        return DateWindows(
            current=DateWindow(c_start, c_end),
            comparison=DateWindow(p_start, p_end),
        )
    if len(iso_dates) == 2:
        c_start, c_end = sorted(iso_dates)
        current = DateWindow(c_start, c_end)
        return DateWindows(current=current, comparison=_previous_same_length(current))
    if len(iso_dates) == 1:
        current = DateWindow(iso_dates[0], iso_dates[0])
        return DateWindows(current=current, comparison=_previous_same_length(current))

    # "last N days"
    last_n = _LAST_N_DAYS_RE.search(normalized)
    if last_n:
        n = max(1, min(int(last_n.group(1)), 365))
        current = DateWindow(resolved_today - timedelta(days=n - 1), resolved_today)
        return DateWindows(current=current, comparison=_previous_same_length(current))

    if "yesterday" in normalized:
        d = resolved_today - timedelta(days=1)
        current = DateWindow(d, d)
        return DateWindows(current=current, comparison=_previous_same_length(current))

    if "today" in normalized:
        current = DateWindow(resolved_today, resolved_today)
        return DateWindows(current=current, comparison=_previous_same_length(current))

    if "last week" in normalized:
        c_start = resolved_today - timedelta(days=resolved_today.weekday() + 7)
        c_end = c_start + timedelta(days=6)
        return DateWindows(
            current=DateWindow(c_start, c_end),
            comparison=DateWindow(c_start - timedelta(days=7), c_end - timedelta(days=7)),
        )

    if "this week" in normalized:
        c_start = resolved_today - timedelta(days=resolved_today.weekday())
        elapsed = (resolved_today - c_start).days
        p_start = c_start - timedelta(days=7)
        return DateWindows(
            current=DateWindow(c_start, resolved_today),
            comparison=DateWindow(p_start, p_start + timedelta(days=elapsed)),
        )

    if "last month" in normalized:
        c_start = _month_start(_shift_month(resolved_today, -1))
        c_end = _month_end(c_start)
        p_start = _month_start(_shift_month(c_start, -1))
        p_end = _month_end(p_start)
        return DateWindows(
            current=DateWindow(c_start, c_end),
            comparison=DateWindow(p_start, p_end),
        )

    if "this month" in normalized or "month over month" in normalized or re.search(r"\bmom\b", normalized):
        return _month_to_date(resolved_today)

    if "last quarter" in normalized:
        c_start = _quarter_start(_shift_month(resolved_today, -3))
        c_end = _quarter_end(c_start)
        p_start = _quarter_start(_shift_month(c_start, -3))
        p_end = _quarter_end(p_start)
        return DateWindows(
            current=DateWindow(c_start, c_end),
            comparison=DateWindow(p_start, p_end),
        )

    if "this quarter" in normalized or "quarter over quarter" in normalized or re.search(r"\bqoq\b", normalized):
        return _quarter_to_date(resolved_today)

    if "week over week" in normalized or re.search(r"\bwow\b", normalized):
        current = DateWindow(resolved_today - timedelta(days=6), resolved_today)
        return DateWindows(current=current, comparison=_previous_same_length(current))

    # Default: last 7 days vs previous 7 days
    current = DateWindow(resolved_today - timedelta(days=6), resolved_today)
    return DateWindows(current=current, comparison=_previous_same_length(current))


# -- helpers --

def _previous_same_length(w: DateWindow) -> DateWindow:
    days = (w.date_to - w.date_from).days + 1
    end = w.date_from - timedelta(days=1)
    start = end - timedelta(days=days - 1)
    return DateWindow(start, end)


def _month_start(d: date) -> date:
    return d.replace(day=1)


def _month_end(d: date) -> date:
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


def _shift_month(d: date, offset: int) -> date:
    idx = (d.year * 12 + (d.month - 1)) + offset
    y = idx // 12
    m = (idx % 12) + 1
    day = min(d.day, calendar.monthrange(y, m)[1])
    return date(y, m, day)


def _quarter_start(d: date) -> date:
    m = ((d.month - 1) // 3) * 3 + 1
    return date(d.year, m, 1)


def _quarter_end(qs: date) -> date:
    return _month_end(_shift_month(qs, 2))


def _month_to_date(today: date) -> DateWindows:
    c_start = _month_start(today)
    elapsed = (today - c_start).days
    p_start = _month_start(_shift_month(today, -1))
    p_end = min(p_start + timedelta(days=elapsed), _month_end(p_start))
    return DateWindows(
        current=DateWindow(c_start, today),
        comparison=DateWindow(p_start, p_end),
    )


def _quarter_to_date(today: date) -> DateWindows:
    c_start = _quarter_start(today)
    elapsed = (today - c_start).days
    p_start = _quarter_start(_shift_month(today, -3))
    p_end = min(p_start + timedelta(days=elapsed), _quarter_end(p_start))
    return DateWindows(
        current=DateWindow(c_start, today),
        comparison=DateWindow(p_start, p_end),
    )
