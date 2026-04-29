"""Framework-neutral period/window resolution.

The CLI (`trees`, `rca`, `elasticity`) and the MCP server both need to turn
a mix of `--period`, `--current`/`--compare`, `--resume`, and `--last` into
a `DateWindows` plus an optional cached run.  Putting the lifecycle here
keeps the logic in one place; adapters map any `PeriodResolutionError` to
their own error shape (Click raises `ClickException`; MCP returns an error
envelope).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as _date
from typing import Any

from qluent_cli import sessions
from qluent_cli.dates import DateWindows, infer_windows, resolve_windows


class PeriodResolutionError(Exception):
    """Raised by `resolve_period` for any user-facing resolution failure."""


@dataclass
class ResolvedPeriod:
    """The result of resolving a period.

    `windows` is always populated.  `cached_run` is set only when `resume`
    or `use_last` produced a hit; callers may choose to short-circuit and
    re-emit the cached payload instead of re-running.
    """

    windows: DateWindows
    cached_run: sessions.RunRecord | None = None


def resolve_period(
    *,
    period: str | None = None,
    current_range: str | None = None,
    compare_range: str | None = None,
    resume: str | None = None,
    use_last: bool = False,
    command: str | None = None,
    tree_id: str | None = None,
    today: _date | None = None,
) -> ResolvedPeriod:
    """Single entry point for window resolution across CLI and MCP."""
    if resume and use_last:
        raise PeriodResolutionError("Use either --resume or --last, not both.")
    if resume:
        record = _lookup_resume(resume, command=command, tree_id=tree_id)
        return ResolvedPeriod(windows=_windows_from_record(record), cached_run=record)
    if use_last:
        record = _lookup_last(command=command, tree_id=tree_id)
        return ResolvedPeriod(windows=_windows_from_record(record), cached_run=record)

    return ResolvedPeriod(
        windows=_resolve_windows_with_today(period, current_range, compare_range, today),
    )


def _lookup_resume(
    run_id: str, *, command: str | None, tree_id: str | None
) -> sessions.RunRecord:
    record = sessions.get_run(run_id)
    if record is None:
        raise PeriodResolutionError(f"No run found for run_id={run_id}")
    if command and record.command != command:
        raise PeriodResolutionError(
            f"Run {run_id} is a {record.command!r} run, not {command!r}."
        )
    if tree_id and record.tree_id and record.tree_id != tree_id:
        raise PeriodResolutionError(
            f"Run {run_id} is for tree {record.tree_id!r}, not {tree_id!r}."
        )
    return record


def _lookup_last(*, command: str | None, tree_id: str | None) -> sessions.RunRecord:
    record = sessions.find_last_run(command=command, tree_id=tree_id)
    if record is None:
        target = f" for {tree_id}" if tree_id else ""
        cmd = command or "investigate"
        raise PeriodResolutionError(
            f"No prior {cmd!r} run{target} found. Run it once to populate the cache."
        )
    return record


def _windows_from_record(record: sessions.RunRecord) -> DateWindows:
    """Reconstruct a `DateWindows` from a stored run."""
    payload: dict[str, Any] = record.load() if record.path.exists() else {}
    args = (payload.get("args") or {}) if isinstance(payload, dict) else {}
    explicit_current = args.get("current") if isinstance(args, dict) else None
    explicit_compare = args.get("compare") if isinstance(args, dict) else None
    explicit_period = args.get("period") if isinstance(args, dict) else None

    if record.period_start and record.period_end and record.comparison_start and record.comparison_end:
        return resolve_windows(
            None,
            f"{record.period_start}:{record.period_end}",
            f"{record.comparison_start}:{record.comparison_end}",
        )
    if explicit_current and explicit_compare:
        return resolve_windows(None, explicit_current, explicit_compare)
    return infer_windows(explicit_period or "last 7 days")


def _resolve_windows_with_today(
    period: str | None,
    current_range: str | None,
    compare_range: str | None,
    today: _date | None,
) -> DateWindows:
    """Same as `dates.resolve_windows`, but accepts a frozen `today` for tests."""
    if today is None:
        return resolve_windows(period, current_range, compare_range)
    if current_range and compare_range:
        return resolve_windows(period, current_range, compare_range)
    if current_range:
        return resolve_windows(period, current_range, compare_range)
    return infer_windows(period or "last 7 days", today=today)
