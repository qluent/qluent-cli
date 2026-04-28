"""Shared primitives for formatter submodules.

Number / date / window formatters used across multiple result kinds.
Kept here so each result-kind module stays focused on its own shape.
"""

from __future__ import annotations

from datetime import date as dt_date
from typing import Any


def fmt_num(value: float, signed: bool = False) -> str:
    """Format a number with commas and optional sign."""
    if abs(value) >= 1:
        formatted = f"{abs(value):,.0f}"
    else:
        formatted = f"{abs(value):,.2f}"
    if signed:
        prefix = "+" if value >= 0 else "-"
        return f"{prefix}{formatted}"
    if value < 0:
        return f"-{formatted}"
    return formatted


def fmt_pct(ratio: float | None) -> str:
    if ratio is None:
        return "n/a"
    return f"{ratio * 100:+.1f}%"


def fmt_share(share: float | None) -> str:
    if share is None:
        return "n/a"
    return f"{share * 100:.0f}%"


def fmt_elasticity(elasticity: float | None) -> str:
    if elasticity is None:
        return "n/a"
    return f"{elasticity:+.2f}"


def fmt_direction(direction: str | None) -> str:
    return direction or "neutral"


def fmt_share_delta(share: float | None) -> str:
    if share is None:
        return "n/a"
    return f"{share * 100:+.0f}pp"


def fmt_date(d: str) -> str:
    """Format ISO date as short form: Mar 10."""
    parsed = dt_date.fromisoformat(d)
    return f"{parsed:%b} {parsed.day}"


def fmt_window(window: dict[str, str]) -> str:
    if window["date_from"] == window["date_to"]:
        return fmt_date(window["date_from"])
    return f"{fmt_date(window['date_from'])}–{fmt_date(window['date_to'])}"


def format_period_label(c_from: str, c_to: str, p_from: str, p_to: str) -> str:
    """Format a period comparison label like 'Mar 10-Mar 16 vs Mar 3-Mar 9'."""
    return f"{fmt_date(c_from)}–{fmt_date(c_to)} vs {fmt_date(p_from)}–{fmt_date(p_to)}"


def fmt_driver_summary(contributors: list[dict[str, Any]]) -> str:
    """Format a list of contributors into a comma-separated driver summary."""
    parts = []
    for contributor in contributors:
        part = f"{contributor['label']} {fmt_num(contributor['delta_value'], signed=True)}"
        if contributor.get("delta_share") is not None:
            part += f" ({fmt_share(contributor['delta_share'])})"
        parts.append(part)
    return ", ".join(parts)
