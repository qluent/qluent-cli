"""Tests for the framework-neutral period/window resolver.

Today every adapter (Click commands in `trees.py`, MCP tools in
`mcp_server.py`) re-implements the period -> 4 ISO strings dance, plus the
`--resume` / `--last` cache lookup is Click-specific and re-implemented
informally elsewhere.  This module owns the lifecycle as a single seam.
"""

from __future__ import annotations

from datetime import date

import pytest

from qluent_cli.window_resolver import (
    PeriodResolutionError,
    ResolvedPeriod,
    resolve_period,
)
from qluent_cli.dates import DateWindows


# -- iso_tuple helper ---------------------------------------------------------


def test_date_windows_iso_tuple_returns_four_strings():
    windows = resolve_period(period="last week", today=date(2026, 4, 29)).windows
    iso = windows.iso_tuple()
    assert iso == (
        windows.current.iso_from,
        windows.current.iso_to,
        windows.comparison.iso_from,
        windows.comparison.iso_to,
    )
    assert all(isinstance(s, str) for s in iso)


# -- period resolution --------------------------------------------------------


def test_resolve_period_uses_natural_language_period():
    rp = resolve_period(period="last week", today=date(2026, 4, 29))
    assert isinstance(rp, ResolvedPeriod)
    assert rp.cached_run is None
    # Last full week before Wednesday 2026-04-29 is Mon 2026-04-20 to Sun 2026-04-26
    assert rp.windows.current.iso_from == "2026-04-20"
    assert rp.windows.current.iso_to == "2026-04-26"


def test_resolve_period_uses_explicit_ranges_verbatim():
    rp = resolve_period(
        current_range="2026-03-01:2026-03-31",
        compare_range="2026-02-01:2026-02-28",
    )
    assert rp.cached_run is None
    assert rp.windows.iso_tuple() == (
        "2026-03-01",
        "2026-03-31",
        "2026-02-01",
        "2026-02-28",
    )


def test_resolve_period_defaults_to_last_seven_days_when_nothing_given():
    rp = resolve_period(today=date(2026, 4, 29))
    assert rp.windows.current.iso_to == "2026-04-29"


# -- resume/last lookup -------------------------------------------------------


def test_resolve_period_with_resume_returns_cached_run(monkeypatch):
    fake_record = _fake_run_record(
        run_id="01234567ABCDEFGH",
        command="trees investigate",
        tree_id="growth",
        period_start="2026-03-01",
        period_end="2026-03-07",
        comparison_start="2026-02-22",
        comparison_end="2026-02-28",
    )
    _patch_session_lookup(monkeypatch, get_run=fake_record)

    rp = resolve_period(
        resume="01234567ABCDEFGH",
        command="trees investigate",
        tree_id="growth",
    )
    assert rp.cached_run is fake_record
    assert rp.windows.iso_tuple() == (
        "2026-03-01",
        "2026-03-07",
        "2026-02-22",
        "2026-02-28",
    )


def test_resolve_period_resume_missing_raises_neutral_error(monkeypatch):
    _patch_session_lookup(monkeypatch, get_run=None)
    with pytest.raises(PeriodResolutionError, match="No run found"):
        resolve_period(resume="DEADBEEFDEADBEEF", command="trees investigate")


def test_resolve_period_resume_with_wrong_command_raises(monkeypatch):
    fake_record = _fake_run_record(command="trees deep-dive")
    _patch_session_lookup(monkeypatch, get_run=fake_record)
    with pytest.raises(PeriodResolutionError, match="not 'trees investigate'"):
        resolve_period(resume="any", command="trees investigate")


def test_resolve_period_resume_with_wrong_tree_raises(monkeypatch):
    fake_record = _fake_run_record(tree_id="growth", command="trees investigate")
    _patch_session_lookup(monkeypatch, get_run=fake_record)
    with pytest.raises(PeriodResolutionError, match="not 'revenue'"):
        resolve_period(
            resume="any",
            command="trees investigate",
            tree_id="revenue",
        )


def test_resolve_period_use_last_returns_most_recent(monkeypatch):
    fake_record = _fake_run_record(
        run_id="LASTRUN1234567XX",
        command="trees investigate",
        tree_id="growth",
        period_start="2026-03-01",
        period_end="2026-03-07",
        comparison_start="2026-02-22",
        comparison_end="2026-02-28",
    )
    _patch_session_lookup(monkeypatch, find_last_run=fake_record)

    rp = resolve_period(
        use_last=True,
        command="trees investigate",
        tree_id="growth",
    )
    assert rp.cached_run is fake_record


def test_resolve_period_use_last_missing_raises_neutral_error(monkeypatch):
    _patch_session_lookup(monkeypatch, find_last_run=None)
    with pytest.raises(PeriodResolutionError, match="No prior"):
        resolve_period(use_last=True, command="trees investigate", tree_id="growth")


def test_resolve_period_resume_and_use_last_are_mutually_exclusive():
    with pytest.raises(PeriodResolutionError, match="not both"):
        resolve_period(resume="abc", use_last=True, command="trees investigate")


# -- helpers ------------------------------------------------------------------


def _fake_run_record(
    *,
    run_id: str = "01234567ABCDEFGH",
    command: str = "trees investigate",
    tree_id: str | None = "growth",
    period_start: str | None = "2026-03-01",
    period_end: str | None = "2026-03-07",
    comparison_start: str | None = "2026-02-22",
    comparison_end: str | None = "2026-02-28",
):
    from pathlib import Path

    from qluent_cli.sessions import RunRecord

    return RunRecord(
        run_id=run_id,
        command=command,
        tree_id=tree_id,
        period_start=period_start,
        period_end=period_end,
        comparison_start=comparison_start,
        comparison_end=comparison_end,
        started_at="2026-03-01T00:00:00Z",
        profile=None,
        client_safe=False,
        path=Path("/tmp/run.json"),
    )


def _patch_session_lookup(monkeypatch, *, get_run=..., find_last_run=...):
    from qluent_cli import window_resolver

    if get_run is not ...:
        monkeypatch.setattr(window_resolver.sessions, "get_run", lambda _id: get_run)
    if find_last_run is not ...:
        monkeypatch.setattr(
            window_resolver.sessions,
            "find_last_run",
            lambda **_kwargs: find_last_run,
        )
