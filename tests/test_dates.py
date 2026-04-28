from __future__ import annotations

from datetime import date

import pytest

from qluent_cli.dates import DateWindow, DateWindows, resolve_windows


def test_date_window_rejects_inverted_range():
    with pytest.raises(ValueError, match="after date_to"):
        DateWindow(date(2026, 4, 30), date(2026, 4, 1))


def test_date_window_iso_strings():
    w = DateWindow(date(2026, 3, 1), date(2026, 3, 31))
    assert w.iso_from == "2026-03-01"
    assert w.iso_to == "2026-03-31"


def test_resolve_windows_explicit_current_and_compare():
    windows = resolve_windows(None, "2026-03-01:2026-03-31", "2026-02-01:2026-02-28")
    assert isinstance(windows, DateWindows)
    assert windows.current.iso_from == "2026-03-01"
    assert windows.current.iso_to == "2026-03-31"
    assert windows.comparison.iso_from == "2026-02-01"
    assert windows.comparison.iso_to == "2026-02-28"


def test_resolve_windows_only_current_infers_comparison():
    windows = resolve_windows(None, "2026-03-09:2026-03-15", None)
    assert windows.current.iso_from == "2026-03-09"
    assert windows.current.iso_to == "2026-03-15"
    assert windows.comparison.iso_from == "2026-03-02"
    assert windows.comparison.iso_to == "2026-03-08"


def test_resolve_windows_invalid_range_format():
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        resolve_windows(None, "2026-03-01", "2026-02-01:2026-02-28")


def test_resolve_windows_inverted_explicit_range_raises():
    with pytest.raises(ValueError, match="after date_to"):
        resolve_windows(None, "2026-03-31:2026-03-01", "2026-02-01:2026-02-28")
